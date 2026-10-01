#!/usr/bin/env python3
"""
cdc_places_feature_builder.py
------------------------------
Fetch CDC PLACES county-level data, build a feature matrix, select geographies
by rule, and export an Amadeus-ready location manifest plus the full output bundle.

Example MVP command
-------------------
python cdc_places_feature_builder.py \\
  --geo-level county \\
  --states AZ \\
  --measures DIABETES OBESITY CSMOKING \\
  --estimate-type crude_prevalence \\
  --release-year latest \\
  --selection-measure DIABETES \\
  --selection-method top_n \\
  --top-n 5 \\
  --output-mode both \\
  --outdir /output
"""

import argparse
import ast
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone

# cdc_places_fetch.py lives in the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdc_places_fetch as _fetch

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ESTIMATE_TYPE_MAP = {
    "crude_prevalence":        "CrdPrv",
    "age_adjusted_prevalence": "AgeAdjPrv",
}

# GIS Friendly Format uses compound column names instead of a measureid column.
GIS_ESTIMATE_SUFFIX = {
    "crude_prevalence":        "crudeprev",
    "age_adjusted_prevalence": "adjprev",
}

MEASURE_NAMES = {
    "DIABETES": "Diagnosed diabetes among adults",
    "OBESITY":  "Obesity among adults",
    "CSMOKING": "Current smoking among adults",
}

WORKFLOW_VERSION = "0.1.0"
FALLBACK_DATASET_ID = "swc5-untb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dirs(outdir):
    paths = {
        "raw":      os.path.join(outdir, "raw"),
        "derived":  os.path.join(outdir, "derived"),
        "selected": os.path.join(outdir, "selected"),
        "metadata": os.path.join(outdir, "metadata"),
        "qa":       os.path.join(outdir, "qa"),
        "logs":     os.path.join(outdir, "logs"),
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths


def _setup_logger(log_path):
    logger = logging.getLogger("feature_builder")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _df_to_rows(df):
    """Convert pandas DataFrame or _SimpleDataFrame to list of dicts."""
    if hasattr(df, "to_dict_records"):
        return df.to_dict_records()
    return df.to_dict("records")


def _parse_geolocation(geo):
    """Extract (lon, lat) from a Socrata geolocation dict or string."""
    if isinstance(geo, str):
        try:
            geo = ast.literal_eval(geo)
        except Exception:
            return None, None
    if isinstance(geo, dict):
        coords = geo.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            return float(coords[0]), float(coords[1])
    return None, None


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------

def _find_county_dataset(app_token=None, log=None):
    """Discover the latest county-level PLACES dataset; fall back to known ID."""
    if log:
        log.info("Discovering county-level CDC PLACES dataset ...")
    try:
        datasets = _fetch.discover_datasets(query="PLACES county", limit=30)
        for ds in datasets:
            name = (ds.get("name") or "").lower()
            if "county" in name and "places" in name:
                if log:
                    log.info(f"Discovered: {ds['name']} (id={ds['id']})")
                return ds["id"]
    except Exception as exc:
        if log:
            log.warning(f"Discovery failed ({exc}), falling back to {FALLBACK_DATASET_ID}")
    if log:
        log.info(f"Using fallback dataset id={FALLBACK_DATASET_ID}")
    return FALLBACK_DATASET_ID


def _probe_format(dataset_id, state, app_token=None):
    """
    Fetch one row to detect dataset layout.
    Returns 'gis_friendly' (pre-pivoted columns like diabetes_crudeprev)
    or 'long' (one row per measure with a measureid column).
    """
    probe = _fetch.fetch_places_data(
        dataset_id=dataset_id,
        where=f"stateabbr = '{state.upper()}'",
        limit=1,
        app_token=app_token,
        verbose=False,
    )
    rows = _df_to_rows(probe)
    if rows and "measureid" not in rows[0]:
        return "gis_friendly"
    return "long"


# ---------------------------------------------------------------------------
# Feature matrix
# ---------------------------------------------------------------------------

def _build_wide_matrix(rows, measures, estimate_type_id):
    """
    Collapse flat CDC PLACES rows into one dict per county (wide format).
    Returns {locationid: county_dict} with one column per measure.
    """
    measures_upper = [m.upper() for m in measures]
    counties = {}

    for row in rows:
        if (row.get("datavaluetypeid") or "").strip() != estimate_type_id:
            continue
        measure_id = (row.get("measureid") or "").upper()
        if measure_id not in measures_upper:
            continue
        locationid = row.get("locationid") or row.get("countyfips")
        if not locationid:
            continue

        if locationid not in counties:
            lon, lat = _parse_geolocation(row.get("geolocation"))
            counties[locationid] = {
                "geoid":      locationid,
                "place_name": row.get("locationname", ""),
                "state":      (row.get("stateabbr") or "").upper(),
                "lon":        lon,
                "lat":        lat,
                "year":       row.get("year", ""),
            }

        col = f"places_{measure_id.lower()}_crude_prevalence"
        val = row.get("data_value")
        if val is not None:
            counties[locationid][col] = val

    return counties


def _build_wide_matrix_gis(rows, measures, estimate_type):
    """
    Build county dict from a GIS Friendly Format dataset.
    Columns are pre-pivoted: e.g. diabetes_crudeprev, obesity_crudeprev.
    """
    suffix = GIS_ESTIMATE_SUFFIX.get(estimate_type, "crudeprev")
    measures_upper = [m.upper() for m in measures]
    counties = {}

    for row in rows:
        locationid = row.get("countyfips") or row.get("locationid")
        if not locationid:
            continue
        if locationid not in counties:
            lon, lat = _parse_geolocation(row.get("geolocation"))
            counties[locationid] = {
                "geoid":      locationid,
                "place_name": row.get("countyname") or row.get("locationname", ""),
                "state":      (row.get("stateabbr") or "").upper(),
                "lon":        lon,
                "lat":        lat,
                "year":       row.get("year", ""),
            }
        for m in measures_upper:
            src_col = f"{m.lower()}_{suffix}"
            dst_col = f"places_{m.lower()}_crude_prevalence"
            val = row.get(src_col)
            if val is not None:
                counties[locationid][dst_col] = val

    return counties


def _gis_to_long_rows(rows, measures, estimate_type, provenance_id, retrieved_at):
    """Synthesize long-format rows from GIS Friendly Format for _write_long."""
    suffix    = GIS_ESTIMATE_SUFFIX.get(estimate_type, "crudeprev")
    type_id   = ESTIMATE_TYPE_MAP.get(estimate_type, "CrdPrv")
    long_rows = []
    for row in rows:
        locationid = row.get("countyfips") or row.get("locationid", "")
        for m in [m.upper() for m in measures]:
            src_col = f"{m.lower()}_{suffix}"
            val = row.get(src_col)
            if val is None:
                continue
            ci_col = f"{m.lower()}_crude95ci" if "crude" in suffix else f"{m.lower()}_adj95ci"
            ci = row.get(ci_col, "")
            long_rows.append({
                "datavaluetypeid":      type_id,
                "measureid":            m,
                "locationid":           locationid,
                "locationname":         row.get("countyname") or row.get("locationname", ""),
                "stateabbr":            (row.get("stateabbr") or "").upper(),
                "data_value":           val,
                "data_value_unit":      "%",
                "low_confidence_limit": ci,
                "high_confidence_limit": "",
                "year":                 row.get("year", ""),
                "geolocation":          row.get("geolocation"),
            })
    return long_rows


def _select_geographies(counties, selection_measure, method, top_n, threshold):
    """Apply selection rule and return a ranked list of county dicts."""
    col = f"places_{selection_measure.lower()}_crude_prevalence"
    candidates = [c for c in counties.values() if c.get(col) is not None]

    def _key(c):
        try:
            return float(c[col])
        except (TypeError, ValueError):
            return 0.0

    candidates.sort(key=_key, reverse=True)

    if method == "top_n":
        selected = candidates[:top_n]
    elif method == "threshold_gte":
        selected = [c for c in candidates if _key(c) >= (threshold or 0.0)]
    else:
        selected = candidates

    for rank, c in enumerate(selected, 1):
        c["_rank"]    = rank
        c["_sel_val"] = c[col]
        c["_reason"]  = f"{method}: {selection_measure.upper()} rank {rank}"

    return selected


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _write_raw(rows, path):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_long(rows, measures, estimate_type_id, estimate_label,
                provenance_id, retrieved_at, path):
    measures_upper = [m.upper() for m in measures]
    fieldnames = [
        "geo_level", "geoid", "state", "place_name",
        "measure_id", "measure_name", "estimate_type",
        "estimate_value", "estimate_unit",
        "low_confidence_limit", "high_confidence_limit",
        "release_year", "source_name", "retrieved_at", "provenance_id",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if (row.get("datavaluetypeid") or "").strip() != estimate_type_id:
                continue
            mid = (row.get("measureid") or "").upper()
            if mid not in measures_upper:
                continue
            writer.writerow({
                "geo_level":             "county",
                "geoid":                 row.get("locationid", ""),
                "state":                 (row.get("stateabbr") or "").upper(),
                "place_name":            row.get("locationname", ""),
                "measure_id":            mid,
                "measure_name":          MEASURE_NAMES.get(mid, mid),
                "estimate_type":         estimate_label,
                "estimate_value":        row.get("data_value", ""),
                "estimate_unit":         row.get("data_value_unit", "%"),
                "low_confidence_limit":  row.get("low_confidence_limit", ""),
                "high_confidence_limit": row.get("high_confidence_limit", ""),
                "release_year":          row.get("year", ""),
                "source_name":           "CDC PLACES",
                "retrieved_at":          retrieved_at,
                "provenance_id":         provenance_id,
            })


def _write_wide(counties, measures, path):
    measure_cols = [f"places_{m.lower()}_crude_prevalence" for m in measures]
    fieldnames = ["geo_level", "geoid", "state", "place_name"] + measure_cols
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for c in sorted(counties.values(), key=lambda x: x["geoid"]):
            row = {
                "geo_level":  "county",
                "geoid":      c["geoid"],
                "state":      c["state"],
                "place_name": c["place_name"],
            }
            for col in measure_cols:
                row[col] = c.get(col, "")
            writer.writerow(row)


def _write_feature_dict(measures, estimate_label, path):
    rows = [
        {
            "column_name":   f"places_{m.lower()}_crude_prevalence",
            "measure_id":    m,
            "measure_name":  MEASURE_NAMES.get(m, m),
            "estimate_type": estimate_label,
            "unit":          "%",
            "source":        "CDC PLACES",
        }
        for m in measures
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_selected(selected, selection_measure, selection_method, estimate_label, path):
    fieldnames = [
        "site_id", "geo_level", "geoid", "state", "place_name",
        "selection_measure", "selection_estimate_type",
        "selection_value", "selection_method", "selection_rank", "selection_reason",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in selected:
            writer.writerow({
                "site_id":                 f"county_{c['geoid']}",
                "geo_level":               "county",
                "geoid":                   c["geoid"],
                "state":                   c["state"],
                "place_name":              c["place_name"],
                "selection_measure":       selection_measure.upper(),
                "selection_estimate_type": estimate_label,
                "selection_value":         c["_sel_val"],
                "selection_method":        selection_method,
                "selection_rank":          c["_rank"],
                "selection_reason":        c["_reason"],
            })


def _write_manifest(selected, selection_measure, path):
    """Write the Amadeus-ready location manifest with lon/lat for each site."""
    fieldnames = [
        "site_id", "geo_level", "geoid", "state", "lon", "lat",
        "selection_measure", "selection_value", "selection_reason",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in selected:
            writer.writerow({
                "site_id":           f"county_{c['geoid']}",
                "geo_level":         "county",
                "geoid":             c["geoid"],
                "state":             c["state"],
                "lon":               c.get("lon", ""),
                "lat":               c.get("lat", ""),
                "selection_measure": selection_measure.upper(),
                "selection_value":   c["_sel_val"],
                "selection_reason":  c["_reason"],
            })


def _write_metadata(args, dataset_id, provenance_id, retrieved_at, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "geo_level":          args.geo_level,
            "states":             args.states,
            "measures":           [m.upper() for m in args.measures],
            "estimate_type":      args.estimate_type,
            "release_year":       args.release_year,
            "dataset_id":         dataset_id,
            "selection_measure":  args.selection_measure.upper(),
            "selection_method":   args.selection_method,
            "top_n":              args.top_n,
            "retrieved_at":       retrieved_at,
            "provenance_id":      provenance_id,
        }, f, indent=2)


def _write_provenance(args, dataset_id, provenance_id, retrieved_at, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "provenance_id":    provenance_id,
            "workflow_name":    "cdc-places-geography-selector",
            "workflow_version": WORKFLOW_VERSION,
            "container_image":  f"geonexus-cdc-places-geography-selector:{WORKFLOW_VERSION}",
            "command":          " ".join(sys.argv),
            "status":           "success",
            "outputs": [
                "raw/cdc_places_raw_extract.csv",
                "derived/cdc_places_features_long.csv",
                "derived/cdc_places_features_wide.csv",
                "derived/cdc_places_feature_dictionary.csv",
                "selected/selected_geographies.csv",
                "selected/amadeus_location_manifest.csv",
                "metadata/metadata.json",
                "metadata/provenance.json",
                "qa/qa_summary.md",
                "logs/cdc_places_run.log",
            ],
            "retrieved_at": retrieved_at,
            "dataset_id":   dataset_id,
        }, f, indent=2)


def _write_qa(counties, selected, measures, measure_cols, path):
    missing_any = [
        c for c in counties.values()
        if any(c.get(col) is None for col in measure_cols)
    ]
    missing_coords = [c for c in selected if not c.get("lon") or not c.get("lat")]

    lines = [
        "# QA Summary",
        "",
        f"- Counties retrieved: {len(counties)}",
        f"- Counties with all measures: {len(counties) - len(missing_any)}",
        f"- Counties missing ≥1 measure: {len(missing_any)}",
        f"- Selected geographies: {len(selected)}",
        f"- Selected missing lon/lat: {len(missing_coords)}",
        "",
        "## Selected geographies",
    ]
    for c in selected:
        col = f"places_{measures[0].lower()}_crude_prevalence"
        lines.append(
            f"  - {c['place_name']} ({c['geoid']}): "
            f"{c.get(col, 'N/A')}%  lon={c.get('lon')}  lat={c.get('lat')}"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build CDC PLACES geography selector output bundle for Amadeus handoff.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--geo-level", default="county", choices=["county"])
    parser.add_argument("--states", nargs="+", default=["AZ"],
                        help="State abbreviations (default: AZ)")
    parser.add_argument("--measures", nargs="+",
                        default=["DIABETES", "OBESITY", "CSMOKING"],
                        help="MeasureIds to fetch (default: DIABETES OBESITY CSMOKING)")
    parser.add_argument("--estimate-type", default="crude_prevalence",
                        choices=list(ESTIMATE_TYPE_MAP))
    parser.add_argument("--release-year", default="latest")
    parser.add_argument("--selection-measure", default="DIABETES",
                        help="Measure used to rank geographies (default: DIABETES)")
    parser.add_argument("--selection-method", default="top_n",
                        choices=["top_n", "threshold_gte"])
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--threshold-value", type=float, default=None)
    parser.add_argument("--output-mode", default="both",
                        choices=["long", "wide", "both"])
    parser.add_argument("--output-prefix", default="cdc_places_to_amadeus_demo")
    parser.add_argument("--outdir", default="cdc_places_to_amadeus_output",
                        help="Output directory (default: cdc_places_to_amadeus_output)")
    parser.add_argument("--dataset-id", default=None,
                        help="Socrata dataset ID (auto-discovered if omitted)")
    parser.add_argument("--token", default=os.environ.get("SODA_APP_TOKEN"),
                        help="Socrata app token (or set SODA_APP_TOKEN env var)")

    args, _ = parser.parse_known_args()

    # CyVerse DE passes multi-value args as a single quoted string
    # (e.g. --measures "DIABETES OBESITY CSMOKING"). Flatten by splitting on
    # commas and whitespace so both CyVerse and CLI invocations work correctly.
    def _split_tokens(values):
        tokens = []
        for v in values:
            tokens.extend(t.strip() for t in v.replace(",", " ").split() if t.strip())
        return tokens

    args.measures = _split_tokens(args.measures)
    args.states   = _split_tokens(args.states)

    # ── Setup ─────────────────────────────────────────────────────────────────
    dirs = _make_dirs(args.outdir)
    log  = _setup_logger(os.path.join(dirs["logs"], "cdc_places_run.log"))

    retrieved_at     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provenance_id    = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    estimate_type_id = ESTIMATE_TYPE_MAP[args.estimate_type]

    log.info(f"provenance_id={provenance_id}")
    log.info(f"states={args.states}  measures={args.measures}  "
             f"estimate_type={args.estimate_type} ({estimate_type_id})")

    # ── Dataset ───────────────────────────────────────────────────────────────
    dataset_id = args.dataset_id or _find_county_dataset(app_token=args.token, log=log)
    log.info(f"dataset_id={dataset_id}")

    # ── Probe dataset format ──────────────────────────────────────────────────
    measures_upper = [m.upper() for m in args.measures]
    state_clauses  = " OR ".join(f"stateabbr = '{s.upper()}'" for s in args.states)

    fmt = _probe_format(dataset_id, args.states[0], app_token=args.token)
    log.info(f"Dataset format: {fmt}")

    if fmt == "long":
        measures_in = "','".join(measures_upper)
        where = f"({state_clauses}) AND measureid IN ('{measures_in}')"
    else:
        where = f"({state_clauses})"
    log.info(f"WHERE: {where}")

    # ── Fetch ─────────────────────────────────────────────────────────────────
    log.info("Fetching from data.cdc.gov ...")
    df   = _fetch.fetch_places_data(dataset_id=dataset_id, where=where,
                                     app_token=args.token)
    rows = _df_to_rows(df)
    log.info(f"Fetched {len(rows):,} rows")

    # ── Raw ───────────────────────────────────────────────────────────────────
    raw_path = os.path.join(dirs["raw"], "cdc_places_raw_extract.csv")
    _write_raw(rows, raw_path)
    log.info(f"Wrote raw: {raw_path}")

    # ── Feature matrix ────────────────────────────────────────────────────────
    if fmt == "gis_friendly":
        counties  = _build_wide_matrix_gis(rows, measures_upper, args.estimate_type)
        long_rows = _gis_to_long_rows(rows, measures_upper, args.estimate_type,
                                      provenance_id, retrieved_at)
    else:
        counties  = _build_wide_matrix(rows, measures_upper, estimate_type_id)
        long_rows = rows

    measure_cols = [f"places_{m.lower()}_crude_prevalence" for m in measures_upper]
    log.info(f"Counties in matrix: {len(counties)}")

    if args.output_mode in ("long", "both"):
        long_path = os.path.join(dirs["derived"], "cdc_places_features_long.csv")
        _write_long(long_rows, measures_upper, estimate_type_id, args.estimate_type,
                    provenance_id, retrieved_at, long_path)
        log.info(f"Wrote long: {long_path}")

    if args.output_mode in ("wide", "both"):
        wide_path = os.path.join(dirs["derived"], "cdc_places_features_wide.csv")
        _write_wide(counties, measures_upper, wide_path)
        log.info(f"Wrote wide: {wide_path}")

    dict_path = os.path.join(dirs["derived"], "cdc_places_feature_dictionary.csv")
    _write_feature_dict(measures_upper, args.estimate_type, dict_path)

    # ── Selection ─────────────────────────────────────────────────────────────
    selected = _select_geographies(
        counties, args.selection_measure,
        args.selection_method, args.top_n, args.threshold_value,
    )
    log.info(f"Selected {len(selected)} geographies by {args.selection_method}")

    sel_path = os.path.join(dirs["selected"], "selected_geographies.csv")
    _write_selected(selected, args.selection_measure, args.selection_method,
                    args.estimate_type, sel_path)
    log.info(f"Wrote selected: {sel_path}")

    manifest_path = os.path.join(dirs["selected"], "amadeus_location_manifest.csv")
    _write_manifest(selected, args.selection_measure, manifest_path)
    log.info(f"Wrote Amadeus manifest: {manifest_path}")

    # Also write manifest to the output root so CyVerse DE workflow can reference
    # it directly as /work/amadeus_location_manifest.csv in the Amadeus step.
    root_manifest_path = os.path.join(args.outdir, "amadeus_location_manifest.csv")
    _write_manifest(selected, args.selection_measure, root_manifest_path)
    log.info(f"Wrote root-level manifest: {root_manifest_path}")

    # ── Metadata + provenance + QA ────────────────────────────────────────────
    _write_metadata(args, dataset_id, provenance_id, retrieved_at,
                    os.path.join(dirs["metadata"], "metadata.json"))
    _write_provenance(args, dataset_id, provenance_id, retrieved_at,
                      os.path.join(dirs["metadata"], "provenance.json"))
    _write_qa(counties, selected, measures_upper, measure_cols,
              os.path.join(dirs["qa"], "qa_summary.md"))

    log.info("Done.")
    print(f"\nOutput bundle:    {os.path.abspath(args.outdir)}")
    print(f"Amadeus manifest: {os.path.abspath(manifest_path)}")


if __name__ == "__main__":
    main()
