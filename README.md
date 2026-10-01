# MVP: Build CDC PLACES Geography Selector for Amadeus Handoff in CyVerse DE

## Objective

Build a CyVerse Discovery Environment app that retrieves selected CDC PLACES measures, creates an analysis-ready public-health context feature matrix, selects geographies of interest using a simple rule, and exports an Amadeus-ready location manifest with GEOIDs and representative points.

This revised MVP replaces the earlier generic CDC PLACES Feature Builder task. The main purpose is to make the CDC PLACES app directly useful as the upstream task for the Amadeus Covariate Builder DE app.

## Core demonstration pattern

```text
CDC PLACES public-health context features
  → selected geographies of interest
  → representative point manifest
  → Amadeus environmental covariate generation
  → joined contextual + environmental feature matrix
```

## Why this matters

The CDC PLACES app should not only retrieve public-health data. It should identify geographies that are analytically interesting and prepare them for downstream environmental covariate generation.

This app demonstrates the first half of a two-app Geo Workbench vignette:

```text
Issue 1: CDC PLACES Geography Selector
  output: selected/amadeus_location_manifest.csv

Issue 2: Amadeus Covariate Builder
  input: selected/amadeus_location_manifest.csv
  output: environmental covariate matrix

Combined result:
  CDC PLACES health context + Amadeus environmental covariates
```

The app should answer:

> Which public-health geographies are interesting enough to send forward for environmental covariate generation?

The Amadeus app then answers:

> What environmental covariates characterize those same geographies or representative locations?

---
locations
## MVP vignette

### Vignette: Identify Arizona counties with elevated health-context measures, then generate environmental covariates

1. User runs the CDC PLACES Geography Selector app in CyVerse DE.
2. User selects:
   - geography level: `county`
   - state: `AZ`
   - measures: `DIABETES`, `OBESITY`, `CSMOKING`
   - estimate type: `crude_prevalence`
   - selection rule: top N counties by diabetes prevalence
3. App retrieves CDC PLACES data.
4. App produces a wide health-context feature matrix.
5. App applies the selection rule.
6. App exports selected geographies.
7. App creates an Amadeus-ready centroid/location manifest.
8. User passes the manifest to the Amadeus DE app.
9. Amadeus generates environmental covariates for the selected geographies.
10. Downstream workflows can join CDC PLACES and Amadeus features by `site_id` or `geoid`.

---

## MVP scope

### In scope

- Package the existing CDC PLACES Python script as a CyVerse DE app.
- Support county-level CDC PLACES retrieval for one demo state.
- Support a curated list of CDC PLACES measures.
- Generate long-format CDC PLACES feature output.
- Generate wide-format analysis-ready CDC PLACES feature matrix.
- Select geographies using a simple rule:
  - `top_n`
  - optionally `threshold_gte`
- Use a staged centroid reference table for representative points.
- Generate `selected_geographies.csv`.
- Generate `amadeus_location_manifest.csv`.
- Generate metadata, provenance, QA, and logs.
- Demonstrate that the Amadeus app can consume the manifest directly.

### Out of scope for MVP

- All CDC PLACES geographies.
- National-scale pulls.
- Arbitrary user-authored filtering logic.
- Polygon export.
- TIGER/Line boundary download inside the app.
- Dynamic geometry processing.
- CRS transformation.
- Complex ranking algorithms.
- Interactive dashboards.
- Restricted or individual-level data.
- Full ontology mapping.
- GA4GH Passport/DUO-based authorization.
- Dockstore/TRS registration.

---

## Key MVP design decision

The CDC PLACES app should use a pre-staged centroid lookup table rather than generating centroids dynamically.

This keeps the first DE implementation realistic and avoids making the CDC PLACES app responsible for boundary downloads, polygon handling, CRS transformations, or geometry validity issues.

### Recommended reference file

```text
reference/county_centroids_az.csv
```

### Reference file schema

```csv
geo_level,geoid,state,place_name,lon,lat
county,04013,AZ,Maricopa County,-112.491,33.348
county,04019,AZ,Pima County,-111.789,32.097
```

A later follow-on issue can add dynamic centroid generation from GEOIDs and boundary files.

---

## MVP CyVerse DE user form parameters

The form should be designed around retrieval, selection, and Amadeus handoff.

| Parameter | Type | Required | MVP default | Notes |
|---|---|---:|---|---|
| `geo_level` | dropdown | yes | `county` | Start with county for reliable centroid handoff |
| `states` | multiselect | yes | `AZ` | Keep demo small |
| `measures` | multiselect | yes | `DIABETES`, `OBESITY`, `CSMOKING` | Curated measure list |
| `estimate_type` | dropdown | yes | `crude_prevalence` | MVP supports one estimate type |
| `release_year` | dropdown/text | yes | `latest` | Use latest supported release |
| `selection_measure` | dropdown | yes | `DIABETES` | Measure used to select geographies for Amadeus |
| `selection_method` | dropdown | yes | `top_n` | MVP options: `top_n`, optionally `threshold_gte` |
| `top_n` | integer | conditional | `5` | Used when `selection_method = top_n` |
| `threshold_value` | number | conditional | none | Used when `selection_method = threshold_gte` |
| `centroid_reference` | file input | yes | `reference/county_centroids_az.csv` | Pre-staged centroid lookup |
| `output_mode` | dropdown | yes | `both` | Produce long and wide outputs |
| `output_prefix` | text | no | `cdc_places_to_amadeus_demo` | Used to name output files |

---

## Example MVP command

```bash
python cdc_places_feature_builder.py \
  --geo-level county \
  --states AZ \
  --measures DIABETES OBESITY CSMOKING \
  --estimate-type crude_prevalence \
  --release-year latest \
  --selection-measure DIABETES \
  --selection-method top_n \
  --top-n 5 \
  --centroid-reference reference/county_centroids_az.csv \
  --output-mode both \
  --outdir "${OUTPUT_DIR}"
```

---

## MVP output bundle

Each successful run should produce a predictable output folder:

```text
cdc_places_to_amadeus_output/
  raw/
    cdc_places_raw_extract.csv
  derived/
    cdc_places_features_long.csv
    cdc_places_features_wide.csv
    cdc_places_feature_dictionary.csv
  selected/
    selected_geographies.csv
    amadeus_location_manifest.csv
  metadata/
    metadata.json
    provenance.json
  qa/
    qa_summary.md
  logs/
    run.log
```

The `selected/` folder is the critical bridge between the CDC PLACES task and the Amadeus task.

---

## Output schema: long-format CDC PLACES feature table

### File

```text
derived/cdc_places_features_long.csv
```

### Purpose

The long table preserves one row per geography, measure, and estimate type. It is useful for QA, provenance, filtering, and reshaping.

### Required MVP fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `geo_level` | string | yes | Geography level, initially `county` |
| `geoid` | string | yes | Standard geography identifier |
| `state` | string | yes | State abbreviation |
| `place_name` | string | no | Human-readable geography name |
| `measure_id` | string | yes | CDC PLACES measure identifier |
| `measure_name` | string | yes | Human-readable measure name |
| `estimate_type` | string | yes | Crude prevalence or supported value type |
| `estimate_value` | number | yes | Numeric estimate value |
| `estimate_unit` | string | yes | Unit, usually percent/prevalence |
| `low_confidence_limit` | number | no | Lower confidence interval bound, if available |
| `high_confidence_limit` | number | no | Upper confidence interval bound, if available |
| `release_year` | string | yes | CDC PLACES release year or version label |
| `source_name` | string | yes | `CDC PLACES` |
| `retrieved_at` | datetime | yes | Retrieval timestamp |
| `provenance_id` | string | yes | Identifier linking rows to run provenance |

---

## Output schema: wide CDC PLACES feature matrix

### File

```text
derived/cdc_places_features_wide.csv
```

### Purpose

The wide table is the main CDC PLACES health-context feature output. It should contain one row per geography and one feature column per selected CDC PLACES measure.

### Required MVP fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `geo_level` | string | yes | Geography level |
| `geoid` | string | yes | Standard geography identifier |
| `state` | string | yes | State abbreviation |
| `place_name` | string | no | Human-readable geography name |
| `places_<measure_id>_<estimate_type>` | number | yes | One generated CDC PLACES feature column per selected measure |

### Feature naming convention

```text
places_<measure_id>_<estimate_type>
```

Example feature columns:

```text
places_diabetes_crudeprev
places_obesity_crudeprev
places_csmoking_crudeprev
```

---

## Required output: selected geographies

### File

```text
selected/selected_geographies.csv
```

### Purpose

This table records which CDC PLACES geographies were selected for downstream environmental covariate generation and why.

### Required MVP fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `site_id` | string | yes | Generated site identifier |
| `geo_level` | string | yes | Geography level, initially `county` |
| `geoid` | string | yes | Standard geography identifier |
| `state` | string | yes | State abbreviation |
| `place_name` | string | no | Human-readable geography name |
| `selection_measure` | string | yes | Measure used for selection |
| `selection_estimate_type` | string | yes | Estimate type used for selection |
| `selection_value` | number | yes | Value of selected measure |
| `selection_method` | string | yes | `top_n` or `threshold_gte` |
| `selection_rank` | integer | no | Rank when using top N |
| `selection_reason` | string | yes | Human-readable explanation |

### Example

```csv
site_id,geo_level,geoid,state,place_name,selection_measure,selection_estimate_type,selection_value,selection_method,selection_rank,selection_reason
az_county_001,county,04013,AZ,Maricopa County,DIABETES,crude_prevalence,11.4,top_n,1,Selected as top county by diabetes crude prevalence
az_county_002,county,04019,AZ,Pima County,DIABETES,crude_prevalence,10.9,top_n,2,Selected as top county by diabetes crude prevalence
```

---

## Required output: Amadeus location manifest

### File

```text
selected/amadeus_location_manifest.csv
```

### Purpose

This is the direct input to the Amadeus Covariate Builder DE app.

It should be intentionally simple and compatible with the Amadeus task.

### Required MVP fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `site_id` | string | yes | Site or selected geography identifier |
| `geo_level` | string | yes | Geography level |
| `geoid` | string | yes | Standard geography identifier |
| `state` | string | yes | State abbreviation |
| `lon` | number | yes | Representative longitude |
| `lat` | number | yes | Representative latitude |
| `selection_measure` | string | yes | CDC PLACES measure used to select geography |
| `selection_value` | number | yes | Value of selected measure |
| `selection_reason` | string | yes | Why this geography was selected |

### Example

```csv
site_id,geo_level,geoid,state,lon,lat,selection_measure,selection_value,selection_reason
az_county_001,county,04013,AZ,-112.491,33.348,DIABETES,11.4,Selected as top county by diabetes crude prevalence
az_county_002,county,04019,AZ,-111.789,32.097,DIABETES,10.9,Selected as top county by diabetes crude prevalence
```

This file should be directly usable by the Amadeus app as:

```text
input_locations = selected/amadeus_location_manifest.csv
```

---

## Metadata and provenance

### Metadata file

```text
metadata/metadata.json
```

Minimum fields:

```json
{
  "source_name": "CDC PLACES",
  "workflow_name": "cdc-places-geography-selector",
  "workflow_version": "0.1.0",
  "geo_level": "county",
  "states": ["AZ"],
  "measures": ["DIABETES", "OBESITY", "CSMOKING"],
  "estimate_type": "crude_prevalence",
  "release_year": "latest",
  "selection_measure": "DIABETES",
  "selection_method": "top_n",
  "top_n": 5,
  "centroid_reference": "reference/county_centroids_az.csv",
  "retrieved_at": "2026-07-15T00:00:00Z"
}
```

### Provenance file

```text
metadata/provenance.json
```

Minimum fields:

```json
{
  "provenance_id": "run_YYYYMMDD_HHMMSS",
  "workflow_name": "cdc-places-geography-selector",
  "workflow_version": "0.1.0",
  "container_image": "cdc-places-geography-selector:0.1.0",
  "command": "python cdc_places_feature_builder.py ...",
  "status": "success",
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
    "logs/run.log"
  ]
}
```

---

## QA summary

### File

```text
qa/qa_summary.md
```

The QA summary should include:

- raw row count
- long table row count
- wide table row count
- number of selected geographies
- selected state or states
- selected CDC PLACES measures
- selected ranking or threshold rule
- missing estimate count
- duplicate `geoid + measure_id + estimate_type` count
- centroid join success count
- centroid join failure count
- Amadeus manifest row count
- output file inventory
- overall run status

Example:

```markdown
# CDC PLACES Geography Selector QA Summary

## Run summary

- Geography level: `county`
- States: `AZ`
- Measures: `DIABETES`, `OBESITY`, `CSMOKING`
- Selection measure: `DIABETES`
- Selection method: `top_n`
- Top N: `5`

## Checks

| Check | Result |
|---|---|
| Raw extract produced | PASS |
| Long feature table produced | PASS |
| Wide feature matrix produced | PASS |
| Selected geographies produced | PASS |
| Centroid join completed | PASS |
| Amadeus location manifest produced | PASS |
| Metadata file produced | PASS |
| Provenance file produced | PASS |
```

---

## Implementation tasks

- [ ] Review existing CDC PLACES Python script and document current inputs and outputs.
- [ ] Refactor script into a CLI workflow with explicit arguments.
- [ ] Define MVP CyVerse DE app parameters focused on CDC PLACES to Amadeus handoff.
- [ ] Support county-level CDC PLACES retrieval for one demo state.
- [ ] Support curated CDC PLACES measures.
- [ ] Implement long-format CDC PLACES output.
- [ ] Implement wide-format CDC PLACES feature matrix.
- [ ] Implement geography selection by `top_n`.
- [ ] Implement optional geography selection by `threshold_gte`.
- [ ] Add or stage county centroid reference table.
- [ ] Join selected GEOIDs to centroid reference.
- [ ] Generate `selected_geographies.csv`.
- [ ] Generate `amadeus_location_manifest.csv`.
- [ ] Generate CDC PLACES feature dictionary.
- [ ] Generate `metadata.json`.
- [ ] Generate `provenance.json`.
- [ ] Generate `qa_summary.md`.
- [ ] Add structured run logging.
- [ ] Create Dockerfile or container recipe.
- [ ] Test workflow locally with MVP parameters.
- [ ] Package workflow as CyVerse DE app.
- [ ] Run at least one demo job in CyVerse DE.
- [ ] Confirm Amadeus app can consume `selected/amadeus_location_manifest.csv`.
- [ ] Document CDC PLACES to Amadeus demo flow.

---

## Acceptance criteria

- [ ] User can launch the app from CyVerse DE.
- [ ] User can select geography, state, measures, estimate type, and selection rule.
- [ ] App retrieves CDC PLACES data for the requested scope.
- [ ] App produces a long CDC PLACES feature table.
- [ ] App produces a wide CDC PLACES feature matrix.
- [ ] App selects geographies using the requested rule.
- [ ] App writes `selected/selected_geographies.csv`.
- [ ] App writes `selected/amadeus_location_manifest.csv`.
- [ ] Amadeus manifest contains valid `site_id`, `geoid`, `lon`, and `lat`.
- [ ] App produces metadata, provenance, QA, and logs.
- [ ] Amadeus app can use the manifest directly as its `input_locations` file.
- [ ] Demo documentation shows the CDC PLACES to Amadeus handoff.

---

## Future enhancements

After the MVP is working, create follow-on issues for:

- support tract, ZCTA, and place geographies
- support all CDC PLACES measures
- support multiple states or national-scale runs
- derive centroids dynamically from GEOIDs
- add TIGER/Line or staged boundary support
- export selected polygons as GeoJSON or GeoPackage
- add richer selection rules
- add visualization outputs
- add ontology or ECTO mapping placeholders
- add Dockstore/TRS workflow publication
- add direct integration with downstream ExWAS workflows