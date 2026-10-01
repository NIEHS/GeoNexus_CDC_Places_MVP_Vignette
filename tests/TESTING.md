# GeoNexus CDC PLACES Testing Documentation

## Overview

Tests validate both the low-level Socrata API client (`cdc_places_fetch.py`) and the
full orchestration pipeline (`cdc_places_feature_builder.py`). The suite includes
offline unit tests and live CDC API integration tests.

```text
tests/
├── test_cdc_query.py          Tests for cdc_places_fetch.py
│   ├── TestBuildWhereClause     (unit)
│   ├── TestCountySelectionIntegration  (offline integration)
│   └── TestLiveCdcPlacesIntegration    (live CDC API)
│
└── test_feature_builder.py    Tests for cdc_places_feature_builder.py
    ├── TestParseGeolocation     (unit)
    ├── TestBuildWideMatrixLong  (unit)
    ├── TestBuildWideMatrixGIS   (unit)
    ├── TestSelectGeographies    (unit)
    ├── TestWriters              (unit — temp filesystem)
    ├── TestGisToLongRows        (unit)
    ├── TestMakeDirs             (unit — temp filesystem)
    └── TestFeatureBuilderIntegration   (live CDC API)
```

All tests run with the Python standard-library `unittest` framework — no additional
test packages are required.

---

## Prerequisites

Verify the development environment is ready:

```bash
python3 --version          # 3.9 or later
python3 -c "import requests, pandas; print('OK')"
```

Activate the virtual environment if needed:

```bash
source .venv/bin/activate
```

---

## Test types

### Unit tests

Run entirely offline using in-memory fixtures. No network access or file I/O beyond
temporary directories.

- `TestBuildWhereClause` — SoQL clause assembly
- `TestParseGeolocation` — lon/lat extraction from dict and string formats
- `TestBuildWideMatrixLong` — long-format row pivoting
- `TestBuildWideMatrixGIS` — GIS Friendly Format pivoting
- `TestSelectGeographies` — `top_n` and `threshold_gte` selection logic
- `TestWriters` — all six CSV output files (raw, long, wide, dict, selected, manifest)
- `TestGisToLongRows` — GIS-to-long format conversion
- `TestMakeDirs` — output directory creation

### Offline integration tests

Use pre-built in-memory sample data to test multi-function flows without network access.

- `TestCountySelectionIntegration` — `export_top_counties_by_measure()` end-to-end with
  sample rows including cross-state filtering and CSV round-trip validation

### Live integration tests

Hit the real CDC PLACES API on `data.cdc.gov`. Automatically skipped if the network is
unavailable.

- `TestLiveCdcPlacesIntegration` — discovers a county dataset, fetches metadata, pulls
  live AZ data, extracts centroids, and optionally writes a CSV
- `TestFeatureBuilderIntegration` — runs the complete feature builder pipeline for AZ
  top 5 DIABETES counties and validates the full output bundle

---

## Running tests

### All tests (recommended)

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

### Individual test files

```bash
# cdc_places_fetch.py tests only
python3 -m unittest tests/test_cdc_query.py -v

# cdc_places_feature_builder.py tests only
python3 -m unittest tests/test_feature_builder.py -v
```

### Individual test class

```bash
python3 -m unittest tests.test_feature_builder.TestSelectGeographies -v
```

### Individual test case

```bash
python3 -m unittest tests.test_feature_builder.TestSelectGeographies.test_top_n_returns_correct_count -v
```

---

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `SODA_APP_TOKEN` | none | Socrata app token; increases API rate limits for live tests |
| `OUTPUT_DIR` | none | If set, `TestLiveCdcPlacesIntegration` writes `az_county_diabetes_live.csv` to this path |

Set a token to avoid rate-limit errors when running the full suite repeatedly:

```bash
export SODA_APP_TOKEN=your_token_here
python3 -m unittest discover -s tests -v
```

---

## Expected output

All 49 tests passing:

```text
test_combines_all_supported_filters (test_cdc_query.TestBuildWhereClause) ... ok
test_returns_none_when_no_filters_are_provided (test_cdc_query.TestBuildWhereClause) ... ok
test_uses_state_abbreviation_for_two_letter_state (test_cdc_query.TestBuildWhereClause) ... ok
test_uses_state_name_for_long_state_values (test_cdc_query.TestBuildWhereClause) ... ok
test_zero_pads_zipcodes (test_cdc_query.TestBuildWhereClause) ... ok
test_exports_top_az_counties_by_diabetes_to_csv (test_cdc_query.TestCountySelectionIntegration) ... ok
test_fetch_metadata_and_live_az_vignette_slice_to_csv (test_cdc_query.TestLiveCdcPlacesIntegration) ... ok
test_builds_one_row_per_county (test_feature_builder.TestBuildWideMatrixGIS) ... ok
...
----------------------------------------------------------------------
Ran 49 tests in ~8s

OK
```

---

## Test file descriptions

### `test_cdc_query.py`

Tests for `cdc_places_fetch.py`.

| Class | Type | What it tests |
|---|---|---|
| `TestBuildWhereClause` | unit | SoQL filter string assembly for state, county, measure, ZIP, lat/lon |
| `TestCountySelectionIntegration` | offline integration | `export_top_counties_by_measure()` with sample rows; validates CSV round-trip |
| `TestLiveCdcPlacesIntegration` | live | Dataset discovery, metadata validation, live AZ fetch, centroid extraction |

### `test_feature_builder.py`

Tests for `cdc_places_feature_builder.py`.

| Class | Type | What it tests |
|---|---|---|
| `TestParseGeolocation` | unit | Dict geolocation, string geolocation, None, empty dict, invalid string |
| `TestBuildWideMatrixLong` | unit | Long-format pivoting, estimate type filtering, measure filtering, lon/lat, place name |
| `TestBuildWideMatrixGIS` | unit | GIS Friendly Format pivoting, countyfips as geoid, column suffix mapping, age-adjusted |
| `TestSelectGeographies` | unit | `top_n` count and ordering, `threshold_gte` filtering, rank/value/reason fields, edge cases |
| `TestWriters` | unit | All six CSV outputs: raw, wide, selected, manifest, feature dict, long |
| `TestGisToLongRows` | unit | Row count, measure IDs, skipping rows with missing values |
| `TestMakeDirs` | unit | All six subdirectories created, all paths are absolute |
| `TestFeatureBuilderIntegration` | live | Full pipeline: discover → probe → fetch → matrix → select → write bundle |

---

## Module loading

Both test files load their target modules via `importlib` so the scripts do not need to
be installed as packages. The `requests` library is stubbed before loading to allow
offline unit tests to run without a network dependency:

```python
sys.modules.setdefault("requests", types.SimpleNamespace())
```

`test_feature_builder.py` pre-loads `cdc_places_fetch` into `sys.modules` before loading
`cdc_places_feature_builder`, because the feature builder imports `cdc_places_fetch` at
module load time:

```python
sys.modules["cdc_places_fetch"] = _fetch_mod
```

---

## Test data fixtures

`test_feature_builder.py` uses two in-memory fixtures shared across unit test classes:

### `LONG_ROWS`

Simulates long-format CDC PLACES rows (one row per county × measure × estimate type):

```text
04013 Maricopa AZ — DIABETES CrdPrv 11.4, OBESITY CrdPrv 31.2, CSMOKING CrdPrv 16.1
04013 Maricopa AZ — DIABETES AgeAdjPrv 9.9  (age-adjusted; should be filtered out)
04019 Pima AZ     — DIABETES CrdPrv 10.9, OBESITY CrdPrv 29.8, CSMOKING CrdPrv 14.7
```

### `GIS_ROWS`

Simulates GIS Friendly Format rows (one row per county, all measures as columns):

```text
04013 Maricopa AZ — diabetes_crudeprev=11.4, obesity_crudeprev=31.2, csmoking_crudeprev=16.1
04019 Pima AZ     — diabetes_crudeprev=10.9, obesity_crudeprev=29.8, csmoking_crudeprev=14.7
04005 Coconino AZ — diabetes_crudeprev=8.7,  obesity_crudeprev=24.5, csmoking_crudeprev=12.2
```

Both fixtures include `geolocation` dicts with realistic Arizona county centroids so
lon/lat extraction can be validated without a live API call.

---

## Recommended workflow

Run tests in this sequence during development:

```text
1. Unit tests (offline, fast)
   python3 -m unittest tests/test_cdc_query.py -v
   python3 -m unittest tests/test_feature_builder.py -v

2. Offline integration test
   (included in the above; TestCountySelectionIntegration)

3. Live integration tests (requires network)
   python3 -m unittest tests.test_cdc_query.TestLiveCdcPlacesIntegration -v
   python3 -m unittest tests.test_feature_builder.TestFeatureBuilderIntegration -v

4. Full suite
   python3 -m unittest discover -s tests -v
```

This ordering isolates failures: unit → offline integration → live API → full pipeline.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'cdc_places_fetch'`

The feature builder is loaded via `importlib` and inserts its own directory into
`sys.path`. If the load fails, check that `_FETCH_PATH` in `test_feature_builder.py`
points to the correct location:

```python
_FETCH_PATH = Path(__file__).resolve().parents[1] / "CDC Places" / "cdc_places_fetch.py"
```

### Live tests fail with HTTP 429

The Socrata API rate-limits unauthenticated requests. Set a token:

```bash
export SODA_APP_TOKEN=your_token_here
```

### Live tests are skipped unexpectedly

Live tests call `self.skipTest()` when a network request fails. Check connectivity:

```bash
curl -s "https://api.us.socrata.com/api/catalog/v1?domains=data.cdc.gov&q=PLACES&limit=1"
```

### `OSError: [Errno 30] Read-only file system: '/output'`

The feature builder's `--outdir /output` is only valid inside the Docker container.
Use a local path when running outside Docker:

```bash
python3 "CDC Places/cdc_places_feature_builder.py" \
  --states AZ --measures DIABETES OBESITY CSMOKING \
  --selection-measure DIABETES --top-n 5 \
  --outdir ./cdc_places_to_amadeus_output
```
