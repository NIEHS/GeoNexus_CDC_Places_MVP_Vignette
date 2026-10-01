# GeoNexus CDC PLACES Developer Environment

## Overview

The GeoNexus CDC PLACES MVP fetches public health data from the CDC PLACES API and produces
an Amadeus-ready location manifest that feeds the Amadeus covariate builder container.

```text
cdc_places_fetch.py
        |
        | Low-level Socrata API client
        v
cdc_places_feature_builder.py
        |
        | Fetch → pivot → select → write manifest
        v
amadeus_location_manifest.csv
        |
        | --input-locations
        v
GeoNexus_Amadeus_MVP_Vignette container
```

The recommended local layout keeps both GeoNexus repositories under the same parent directory:

```text
geo_nexus/
├── GeoNexus_CDC_Places_MVP_Vignette/
│   ├── CDC Places/
│   │   ├── cdc_places_fetch.py
│   │   └── cdc_places_feature_builder.py
│   ├── tests/
│   ├── Dockerfile
│   ├── build_docker.sh
│   └── requirements.txt
│
└── GeoNexus_Amadeus_MVP_Vignette/
    ├── amadeus_covariate_builder.py
    ├── Dockerfile
    └── ...
```

---

## 1. Clone the repository

Create a parent directory:

```bash
mkdir -p ~/Documents/github/geo_nexus
cd ~/Documents/github/geo_nexus
```

Clone the CDC PLACES repository:

```bash
git clone https://github.com/NIEHS/GeoNexus_CDC_Places_MVP_Vignette.git
cd GeoNexus_CDC_Places_MVP_Vignette
git checkout develop
```

---

## 2. Create the Python development environment

Verify Python:

```bash
python3 --version   # 3.9 or later recommended
which python3
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Verify:

```bash
pip list | grep -E "requests|pandas"
```

---

## 3. Repository structure

```text
GeoNexus_CDC_Places_MVP_Vignette/
├── CDC Places/
│   ├── cdc_places_fetch.py           Low-level Socrata/SODA API client
│   └── cdc_places_feature_builder.py Orchestration: fetch → pivot → select → manifest
│
├── tests/
│   ├── __init__.py
│   ├── context.py                    (unused — kept for compatibility)
│   ├── test_cdc_query.py             Tests for cdc_places_fetch.py
│   └── test_feature_builder.py       Tests for cdc_places_feature_builder.py
│
├── Dockerfile                        Container image definition
├── build_docker.sh                   Build + local test run script
├── requirements.txt                  Python dependencies
├── README.md                         MVP specification
└── DEVELOPMENT.md                    This file
```

---

## 4. Script architecture

### `cdc_places_fetch.py` — Socrata API client

Standalone fetch utility. No other project files are required.

Key functions:

```text
discover_datasets()      Query Socrata Discovery API for matching datasets
fetch_places_data()      Page through a dataset; return rows as DataFrame
build_where_clause()     Assemble a SoQL $where filter string
fetch_metadata()         Retrieve column-level dataset metadata
add_centroid_columns()   Extract lon/lat from Socrata geolocation field
export_top_counties_by_measure()   Rank counties and write a wide CSV
```

### `cdc_places_feature_builder.py` — Orchestration layer

Imports `cdc_places_fetch` and produces the full GeoNexus output bundle.

Execution flow:

```text
cdc_places_feature_builder.py
        |
        v
Auto-discover county-level PLACES dataset
        |
        v
Probe dataset format (GIS Friendly or long)
        |
        v
Fetch all measures for requested states
        |
        v
Build wide county feature matrix
        |
        v
Select top N (or threshold) geographies
        |
        v
Write output bundle:
  raw/cdc_places_raw_extract.csv
  derived/cdc_places_features_long.csv
  derived/cdc_places_features_wide.csv
  derived/cdc_places_feature_dictionary.csv
  selected/selected_geographies.csv
  selected/amadeus_location_manifest.csv   ← Amadeus handoff
  metadata/metadata.json
  metadata/provenance.json
  qa/qa_summary.md
  logs/cdc_places_run.log
```

---

## 5. Run `cdc_places_fetch.py` locally

```bash
cd "CDC Places"

# Browse available datasets interactively
python cdc_places_fetch.py --browse --search "county"

# Fetch AZ county DIABETES data directly
python cdc_places_fetch.py \
  --dataset-id swc5-untb \
  --state AZ \
  --measure DIABETES \
  --out az_county_diabetes.csv

# Preview metadata before downloading
python cdc_places_fetch.py --dataset-id i46a-9kgh --meta --preview
```

Optional Socrata app token (raises rate limits):

```bash
export SODA_APP_TOKEN=your_token_here
```

---

## 6. Run `cdc_places_feature_builder.py` locally

From the `CDC Places/` directory or repo root:

```bash
python "CDC Places/cdc_places_feature_builder.py" \
  --states AZ \
  --measures DIABETES OBESITY CSMOKING \
  --estimate-type crude_prevalence \
  --selection-measure DIABETES \
  --selection-method top_n \
  --top-n 5 \
  --output-mode both \
  --outdir ./cdc_places_to_amadeus_output
```

The dataset ID is auto-discovered. To pin a specific dataset:

```bash
python "CDC Places/cdc_places_feature_builder.py" \
  --dataset-id i46a-9kgh \
  --states AZ \
  --measures DIABETES OBESITY CSMOKING \
  --selection-measure DIABETES \
  --top-n 5
```

Key output to verify:

```bash
cat cdc_places_to_amadeus_output/selected/amadeus_location_manifest.csv
cat cdc_places_to_amadeus_output/qa/qa_summary.md
```

---

## 7. Dataset formats

The CDC PLACES API offers two county-level dataset layouts. The feature builder detects the
format automatically by probing a single row.

### GIS Friendly Format (default, auto-discovered)

One row per county. Measures are pre-pivoted as columns:

```text
countyfips, countyname, stateabbr,
diabetes_crudeprev, obesity_crudeprev, csmoking_crudeprev,
geolocation, ...
```

Example dataset ID: `i46a-9kgh` (2025 release)

### Long Format

One row per county × measure × estimate type:

```text
locationid, locationname, stateabbr,
measureid, datavaluetypeid, data_value,
geolocation, ...
```

Example dataset ID: `swc5-untb`

Both formats are supported. Pass `--dataset-id` to force a specific dataset.

---

## 8. Build the Docker container

Requires Docker with `buildx` support:

```bash
docker buildx version
```

Build the image:

```bash
./build_docker.sh
```

The script builds the image and runs a local test against the live CDC API:

```bash
docker buildx build --no-cache --platform linux/amd64 \
  -t ghcr.io/niehs/geonexus-cdc-places-geography-selector:0.1.0 .

docker run --rm \
  --platform linux/amd64 \
  -v "$(pwd)/test_output:/output" \
  ghcr.io/niehs/geonexus-cdc-places-geography-selector:0.1.0 \
  --states AZ \
  --measures DIABETES OBESITY CSMOKING \
  --selection-measure DIABETES \
  --top-n 5
```

Verify the Docker output:

```bash
cat test_output/selected/amadeus_location_manifest.csv
cat test_output/qa/qa_summary.md
```

---

## 9. Two-container workflow with Amadeus

The CDC PLACES container produces `amadeus_location_manifest.csv`. The Amadeus container
reads it via `--input-locations`.

```text
CDC Places container
        |
        v
cdc_places_to_amadeus_output/selected/amadeus_location_manifest.csv
        |
        | -v selected:/input:ro
        v
Amadeus container
        |
        v
amadeus_output/joined/places_amadeus_joined_features.csv
```

Run both steps from the repo root:

```bash
# Step 1 — CDC Places → manifest
python "CDC Places/cdc_places_feature_builder.py" \
  --states AZ \
  --measures DIABETES OBESITY CSMOKING \
  --selection-measure DIABETES \
  --top-n 5 \
  --outdir ./cdc_places_to_amadeus_output

# Step 2 — Amadeus reads manifest
mkdir -p amadeus_output
docker run --rm \
  --platform linux/amd64 \
  -v "$(pwd)/cdc_places_to_amadeus_output/selected:/input:ro" \
  -v "$(pwd)/amadeus_output:/output" \
  ghcr.io/niehs/geonexus-amadeus-covariate-builder:0.1.8 \
  --input-locations /input/amadeus_location_manifest.csv \
  --covariate-dataset gridmet \
  --covariate-variable tmmx \
  --start-date 2020-07-01 \
  --end-date 2021-07-07
```

Final joined output:

```bash
cat amadeus_output/joined/places_amadeus_joined_features.csv
```

---

## 10. Amadeus manifest schema

The file that connects the two containers:

```text
selected/amadeus_location_manifest.csv
```

| Field | Type | Description |
|---|---|---|
| `site_id` | string | `county_<geoid>` |
| `geo_level` | string | `county` |
| `geoid` | string | 5-digit FIPS code |
| `state` | string | State abbreviation |
| `lon` | float | County centroid longitude (from CDC geolocation field) |
| `lat` | float | County centroid latitude (from CDC geolocation field) |
| `selection_measure` | string | Measure used for ranking |
| `selection_value` | float | Measure value for this site |
| `selection_reason` | string | Human-readable selection rule |

---

## 11. Environment variables

| Variable | Used by | Description |
|---|---|---|
| `SODA_APP_TOKEN` | `cdc_places_fetch.py` | Socrata app token; raises rate limits |
| `OUTPUT_DIR` | `tests/test_cdc_query.py` | Optional path for integration test CSV output |

---

## 12. Quick environment verification

```bash
# Python version
python3 --version

# Dependencies installed
python3 -c "import requests, pandas; print('OK')"

# Fetch script runs
python3 "CDC Places/cdc_places_fetch.py" --dataset-id i46a-9kgh --state AZ --limit 1 --preview

# Feature builder runs
python3 "CDC Places/cdc_places_feature_builder.py" \
  --states AZ --measures DIABETES OBESITY CSMOKING \
  --selection-measure DIABETES --top-n 5 \
  --outdir /tmp/cdc_verify

# Tests pass
python3 -m unittest discover -s tests -v

# Manifest exists with lon/lat
cat /tmp/cdc_verify/selected/amadeus_location_manifest.csv
```

If all checks pass, the development environment is ready.

---

## 13. Architecture summary

```text
CDC PLACES API (data.cdc.gov)
        |
        | Socrata SODA API
        v
cdc_places_fetch.py
        |
        | discover_datasets()
        | fetch_places_data()
        v
cdc_places_feature_builder.py
        |
        +---------------------------+
        |                           |
        v                           v
GIS Friendly Format           Long Format
(auto-discovered)             (--dataset-id override)
        |                           |
        +-----------+---------------+
                    |
                    v
          _build_wide_matrix_gis()
          or _build_wide_matrix()
                    |
                    v
          _select_geographies()
          top_n or threshold_gte
                    |
                    v
          Output bundle:
          selected/amadeus_location_manifest.csv
          derived/cdc_places_features_wide.csv
          derived/cdc_places_features_long.csv
          ...
                    |
                    | --input-locations
                    v
          Amadeus covariate builder
                    |
                    v
          places_amadeus_joined_features.csv
```
