#!/usr/bin/env python3
"""
cdc_places_fetch.py
--------------------
Pull data from the CDC PLACES / 500 Cities datasets hosted on data.cdc.gov
(Socrata / SODA API).

Rather than hardcoding dataset IDs (which change with every yearly release),
this script browses the live catalog and lets you pick a dataset interactively,
using Socrata's Discovery API.

No API key is required for normal use. A free Socrata app token raises your
rate limit -- get one at https://data.cdc.gov/profile/edit/developer_settings
and pass it via --token or the SODA_APP_TOKEN environment variable.

USAGE EXAMPLES
--------------
# Browse datasets and pick one interactively
python cdc_places_fetch.py --browse

# Narrow the browse list with a keyword
python cdc_places_fetch.py --browse --search "census tract"

# Fetch directly if you already know the dataset ID
python cdc_places_fetch.py --dataset-id swc5-untb --state NC --measure COPD --out nc_copd.csv

# Preview columns and sample rows before a full download
python cdc_places_fetch.py --dataset-id swc5-untb --meta --preview

# Filter by ZIP/ZCTA (use with a ZCTA-level dataset)
python cdc_places_fetch.py --browse --search "ZCTA" --zipcode 27701 --measure DIABETES

# Filter by lat/lon radius (use with a GIS-friendly dataset)
python cdc_places_fetch.py --dataset-id yjkw-uj5s --near 35.78,-78.64 --radius 10000 --out raleigh.csv
"""

import argparse
import os
import sys
import textwrap
import time
from typing import Optional

import requests

try:
    import pandas as pd
except ImportError:
    pd = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL      = "https://data.cdc.gov/resource/{dataset_id}.json"
METADATA_URL  = "https://data.cdc.gov/api/views/{dataset_id}"
DISCOVERY_URL = "https://api.us.socrata.com/api/catalog/v1"
DOMAIN        = "data.cdc.gov"
DEFAULT_QUERY = "PLACES"
PAGE_SIZE     = 50000


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------

def discover_datasets(domain: str = DOMAIN,
                      category: Optional[str] = None,
                      query: Optional[str] = None,
                      limit: int = 100) -> list:
    """
    Query Socrata's Discovery API for datasets on a given domain.
    Returns a list of dicts: {id, name, description, updated, category}.
    """
    params = {
        "domains": domain,
        "only":    "dataset",
        "limit":   limit,
    }
    if category:
        params["categories"] = category
    if query:
        params["q"] = query
    if not category and not query:
        params["q"] = DEFAULT_QUERY

    resp = requests.get(DISCOVERY_URL, params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Discovery API request failed ({resp.status_code}): {resp.text[:500]}"
        )

    results = []
    for item in resp.json().get("results", []):
        resource       = item.get("resource", {})
        classification = item.get("classification", {})
        results.append({
            "id":          resource.get("id"),
            "name":        resource.get("name"),
            "description": (resource.get("description") or "").strip().replace("\n", " "),
            "updated":     (resource.get("updatedAt") or "")[:10],
            "category":    classification.get("domain_category", ""),
        })
    return results


def browse_and_select(category: Optional[str], query: Optional[str]) -> str:
    """Print a numbered dataset list and prompt the user to pick one."""
    print(
        f"Looking up datasets on {DOMAIN}"
        + (f" matching '{query}'" if query else "")
        + (f" in category '{category}'" if category else "")
        + " ...\n",
        file=sys.stderr,
    )

    datasets = discover_datasets(category=category, query=query)
    if not datasets and category:
        print(
            f"No results for category '{category}' -- retrying as a plain text search...\n",
            file=sys.stderr,
        )
        datasets = discover_datasets(category=None, query=query or DEFAULT_QUERY)
    if not datasets:
        sys.exit("No datasets found. Try a different --search term.")

    for i, d in enumerate(datasets, 1):
        desc = (d["description"][:90] + "...") if len(d["description"]) > 90 else d["description"]
        print(f"[{i:>2}] {d['name']}  (id: {d['id']}, updated: {d['updated']})")
        if desc:
            print(f"     {desc}")

    while True:
        choice = input(f"\nPick a dataset [1-{len(datasets)}], or 'q' to quit: ").strip()
        if choice.lower() == "q":
            sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(datasets):
            selected = datasets[int(choice) - 1]
            print(f"\nSelected: {selected['name']} (id: {selected['id']})\n")
            return selected["id"]
        print("Not a valid choice, try again.")


# ---------------------------------------------------------------------------
# Column metadata
# ---------------------------------------------------------------------------

def fetch_metadata(dataset_id: str, app_token: Optional[str] = None) -> dict:
    """
    Fetch full dataset metadata from Socrata's /api/views/<id> endpoint.
    Returns the raw JSON dict which includes dataset-level info and a
    'columns' list where each entry describes one field.
    """
    url     = METADATA_URL.format(dataset_id=dataset_id)
    headers = {}
    if app_token:
        headers["X-App-Token"] = app_token

    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Metadata request failed ({resp.status_code}): {resp.text[:500]}"
        )
    return resp.json()


def print_metadata(meta: dict) -> None:
    """Print a readable summary of dataset-level info and column definitions."""
    print("=" * 70)
    print(f"NAME:        {meta.get('name', 'N/A')}")
    print(f"DATASET ID:  {meta.get('id', 'N/A')}")
    print(f"CATEGORY:    {meta.get('category', 'N/A')}")
    updated = (meta.get("rowsUpdatedAt") or meta.get("updatedAt") or "N/A")[:10]
    print(f"UPDATED:     {updated}")
    row_count = meta.get("rowCount")
    print(f"ROW COUNT:   {row_count:,}" if isinstance(row_count, int) else f"ROW COUNT:   {row_count}")
    desc = (meta.get("description") or "").strip()
    if desc:
        print(f"DESCRIPTION: {textwrap.fill(desc, width=68, subsequent_indent='             ')}")
    print()

    columns = meta.get("columns", [])
    if not columns:
        print("No column metadata available.")
        return

    user_cols = [c for c in columns if not c.get("fieldName", "").startswith(":")]
    print(f"COLUMNS ({len(user_cols)} user columns):")
    print("-" * 70)

    for col in user_cols:
        field = col.get("fieldName", "")
        name  = col.get("name", "")
        dtype = col.get("dataTypeName", "")
        desc  = (col.get("description") or "").strip().replace("\n", " ")

        print(f"  {field}")
        print(f"    Label : {name}")
        print(f"    Type  : {dtype}")
        if desc:
            print(f"    Notes : {textwrap.fill(desc, width=64, subsequent_indent='            ')}")
        print()


def save_metadata_csv(meta: dict, out_path: str) -> None:
    """Save column metadata to a CSV for easy reference."""
    if pd is None:
        raise RuntimeError("pandas is required: pip install pandas")

    user_cols = [c for c in meta.get("columns", [])
                 if not c.get("fieldName", "").startswith(":")]
    rows = [
        {
            "field_name":   col.get("fieldName", ""),
            "display_name": col.get("name", ""),
            "data_type":    col.get("dataTypeName", ""),
            "description":  (col.get("description") or "").strip().replace("\n", " "),
            "position":     col.get("position", ""),
        }
        for col in user_cols
    ]
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"Column metadata saved to {out_path}")


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def build_where_clause(state: Optional[str] = None,
                        county: Optional[str] = None,
                        measure: Optional[str] = None,
                        extra_where: Optional[str] = None,
                        zipcode: Optional[str] = None,
                        lat: Optional[float] = None,
                        lon: Optional[float] = None,
                        radius_m: int = 25000) -> Optional[str]:
    """
    Assemble a SoQL $where clause from individual filter arguments.

    ZIP/ZCTA filter : matches the `locationid` column on ZCTA-level datasets.
    Geo filter      : uses within_circle(geolocation, lat, lon, radius_m),
                      which requires a GIS-friendly dataset variant.
    """
    clauses = []

    if state:
        if len(state) > 2:
            clauses.append(f"statedesc = '{state}'")
        else:
            clauses.append(f"stateabbr = '{state.upper()}'")

    if county:
        clauses.append(f"upper(countyname) like upper('%{county}%')")

    if measure:
        clauses.append(f"measureid = '{measure.upper()}'")

    if zipcode:
        clauses.append(f"locationid = '{zipcode.zfill(5)}'")

    if lat is not None and lon is not None:
        clauses.append(f"within_circle(geolocation, {lat}, {lon}, {radius_m})")

    if extra_where:
        clauses.append(f"({extra_where})")

    return " AND ".join(clauses) if clauses else None


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_places_data(dataset_id: str,
                       where: Optional[str] = None,
                       select: Optional[str] = None,
                       limit: Optional[int] = None,
                       app_token: Optional[str] = None,
                       verbose: bool = True) -> "pd.DataFrame":
    """
    Page through a Socrata dataset and return the results as a DataFrame.
    limit=None fetches every matching row; an integer caps the total.
    """
    if pd is None:
        raise RuntimeError("pandas is required: pip install pandas requests")

    url     = BASE_URL.format(dataset_id=dataset_id)
    headers = {}
    if app_token:
        headers["X-App-Token"] = app_token

    all_rows  = []
    offset    = 0
    page_size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit)

    while True:
        params = {"$limit": page_size, "$offset": offset, "$order": ":id"}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select

        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Request failed ({resp.status_code}): {resp.text[:500]}"
            )

        batch = resp.json()
        if not batch:
            break

        all_rows.extend(batch)
        offset += len(batch)

        if verbose:
            print(f"  fetched {offset:,} rows...", file=sys.stderr)

        if limit is not None and offset >= limit:
            all_rows = all_rows[:limit]
            break
        if len(batch) < page_size:
            break

        time.sleep(0.1)

    return pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch CDC PLACES / 500 Cities data from data.cdc.gov.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--browse", action="store_true",
                        help="Browse datasets interactively and pick one")
    parser.add_argument("--search",
                        help="Free-text filter while browsing (e.g. 'census tract')")
    parser.add_argument("--category", default=None,
                        help="Exact Socrata category name to filter by (optional)")
    parser.add_argument("--dataset-id",
                        help="Exact Socrata dataset ID -- skips --browse")
    parser.add_argument("--state",
                        help="Two-letter state abbreviation or full state name")
    parser.add_argument("--county",
                        help="County name (partial match), applies to county/tract datasets")
    parser.add_argument("--measure",
                        help="MeasureId to filter on, e.g. COPD, DIABETES, OBESITY")
    parser.add_argument("--zipcode",
                        help="5-digit ZIP / ZCTA code -- best with a ZCTA-level dataset")
    parser.add_argument("--near",
                        help="Lat/lon center for radius search as 'lat,lon' (e.g. 35.78,-78.64). "
                             "Requires a GIS-friendly dataset.")
    parser.add_argument("--radius", type=int, default=25000,
                        help="Radius in metres for --near searches (default: 25000)")
    parser.add_argument("--where",
                        help="Raw SoQL $where clause, combined with filters above")
    parser.add_argument("--select",
                        help="Comma-separated columns to return (SoQL $select), default: all")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max rows to fetch (default: all matching rows)")
    parser.add_argument("--out", default="places_data.csv",
                        help="Output CSV path (default: places_data.csv)")
    parser.add_argument("--token", default=os.environ.get("SODA_APP_TOKEN"),
                        help="Socrata app token (or set env var SODA_APP_TOKEN)")
    parser.add_argument("--meta", action="store_true",
                        help="Fetch and display column-level metadata for the chosen dataset")
    parser.add_argument("--preview", action="store_true",
                        help="Print first 5 rows and column list; don't save a file")

    # parse_known_args tolerates Jupyter's injected -f kernel.json argument
    args, _unknown = parser.parse_known_args()

    # ── Resolve dataset ID ────────────────────────────────────────────────────
    if args.dataset_id:
        dataset_id = args.dataset_id
    else:
        category   = args.category or None
        dataset_id = browse_and_select(category=category, query=args.search)

    # ── Metadata ──────────────────────────────────────────────────────────────
    if args.meta:
        print("Fetching column metadata ...", file=sys.stderr)
        meta = fetch_metadata(dataset_id, app_token=args.token)
        print_metadata(meta)
        save_metadata_csv(meta, f"meta_{dataset_id}.csv")
        print()

    # ── Filters ───────────────────────────────────────────────────────────────
    lat = lon = None
    if args.near:
        try:
            lat_s, lon_s = args.near.split(",")
            lat, lon = float(lat_s.strip()), float(lon_s.strip())
        except ValueError:
            sys.exit("--near must be 'lat,lon', e.g. --near 35.78,-78.64")
        print(
            "Note: --near requires a GIS-friendly dataset (one with a geolocation column).",
            file=sys.stderr,
        )

    where = build_where_clause(
        state=args.state,
        county=args.county,
        measure=args.measure,
        extra_where=args.where,
        zipcode=args.zipcode,
        lat=lat, lon=lon,
        radius_m=args.radius,
    )

    # ── Fetch ─────────────────────────────────────────────────────────────────
    print(f"Dataset ID: {dataset_id}")
    if where:
        print(f"Filter    : {where}")
    print("Fetching from data.cdc.gov ...", file=sys.stderr)

    row_limit = args.limit if not args.preview else (args.limit or 5)
    df = fetch_places_data(
        dataset_id=dataset_id,
        where=where,
        select=args.select,
        limit=row_limit,
        app_token=args.token,
    )

    print(f"\nRetrieved {len(df):,} rows, {len(df.columns)} columns.")

    if args.preview:
        import pandas as _pd
        with _pd.option_context("display.max_columns", None, "display.width", 160):
            print(df.head())
        print("\nColumns:", list(df.columns))
        return

    df.to_csv(args.out, index=False)
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
