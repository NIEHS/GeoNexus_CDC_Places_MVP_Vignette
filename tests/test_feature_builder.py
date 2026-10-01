import csv
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

# ── Module loading ────────────────────────────────────────────────────────────
# Stub requests before any import that depends on it.
sys.modules.setdefault("requests", types.SimpleNamespace())

# Pre-load cdc_places_fetch so feature_builder's `import cdc_places_fetch` resolves.
_FETCH_PATH = Path(__file__).resolve().parents[1] / "CDC Places" / "cdc_places_fetch.py"
_fetch_spec = importlib.util.spec_from_file_location("cdc_places_fetch", _FETCH_PATH)
_fetch_mod  = importlib.util.module_from_spec(_fetch_spec)
sys.modules["cdc_places_fetch"] = _fetch_mod
_fetch_spec.loader.exec_module(_fetch_mod)

_BUILDER_PATH = Path(__file__).resolve().parents[1] / "CDC Places" / "cdc_places_feature_builder.py"
_builder_spec = importlib.util.spec_from_file_location("cdc_places_feature_builder", _BUILDER_PATH)
fb = importlib.util.module_from_spec(_builder_spec)
sys.modules["cdc_places_feature_builder"] = fb
_builder_spec.loader.exec_module(fb)

# ── Shared fixtures ───────────────────────────────────────────────────────────

LONG_ROWS = [
    # Maricopa — crude prevalence
    {"datavaluetypeid": "CrdPrv", "measureid": "DIABETES", "locationid": "04013",
     "locationname": "Maricopa", "stateabbr": "AZ", "data_value": "11.4",
     "data_value_unit": "%", "low_confidence_limit": "10.8", "high_confidence_limit": "12.0",
     "year": "2023", "geolocation": {"type": "Point", "coordinates": [-112.491, 33.348]}},
    {"datavaluetypeid": "CrdPrv", "measureid": "OBESITY", "locationid": "04013",
     "locationname": "Maricopa", "stateabbr": "AZ", "data_value": "31.2",
     "data_value_unit": "%", "low_confidence_limit": "30.0", "high_confidence_limit": "32.4",
     "year": "2023", "geolocation": {"type": "Point", "coordinates": [-112.491, 33.348]}},
    {"datavaluetypeid": "CrdPrv", "measureid": "CSMOKING", "locationid": "04013",
     "locationname": "Maricopa", "stateabbr": "AZ", "data_value": "16.1",
     "data_value_unit": "%", "low_confidence_limit": "15.0", "high_confidence_limit": "17.2",
     "year": "2023", "geolocation": {"type": "Point", "coordinates": [-112.491, 33.348]}},
    # Pima — crude prevalence
    {"datavaluetypeid": "CrdPrv", "measureid": "DIABETES", "locationid": "04019",
     "locationname": "Pima", "stateabbr": "AZ", "data_value": "10.9",
     "data_value_unit": "%", "low_confidence_limit": "10.2", "high_confidence_limit": "11.6",
     "year": "2023", "geolocation": {"type": "Point", "coordinates": [-111.789, 32.097]}},
    {"datavaluetypeid": "CrdPrv", "measureid": "OBESITY", "locationid": "04019",
     "locationname": "Pima", "stateabbr": "AZ", "data_value": "29.8",
     "data_value_unit": "%", "low_confidence_limit": "28.5", "high_confidence_limit": "31.1",
     "year": "2023", "geolocation": {"type": "Point", "coordinates": [-111.789, 32.097]}},
    {"datavaluetypeid": "CrdPrv", "measureid": "CSMOKING", "locationid": "04019",
     "locationname": "Pima", "stateabbr": "AZ", "data_value": "14.7",
     "data_value_unit": "%", "low_confidence_limit": "13.5", "high_confidence_limit": "15.9",
     "year": "2023", "geolocation": {"type": "Point", "coordinates": [-111.789, 32.097]}},
    # Maricopa — age-adjusted (should be excluded when filtering for crude)
    {"datavaluetypeid": "AgeAdjPrv", "measureid": "DIABETES", "locationid": "04013",
     "locationname": "Maricopa", "stateabbr": "AZ", "data_value": "9.9",
     "data_value_unit": "%", "low_confidence_limit": "9.2", "high_confidence_limit": "10.6",
     "year": "2023", "geolocation": {"type": "Point", "coordinates": [-112.491, 33.348]}},
]

GIS_ROWS = [
    {"countyfips": "04013", "countyname": "Maricopa", "stateabbr": "AZ",
     "diabetes_crudeprev": "11.4", "obesity_crudeprev": "31.2", "csmoking_crudeprev": "16.1",
     "year": "2025",
     "geolocation": {"type": "Point", "coordinates": [-112.491, 33.348]}},
    {"countyfips": "04019", "countyname": "Pima", "stateabbr": "AZ",
     "diabetes_crudeprev": "10.9", "obesity_crudeprev": "29.8", "csmoking_crudeprev": "14.7",
     "year": "2025",
     "geolocation": {"type": "Point", "coordinates": [-111.789, 32.097]}},
    {"countyfips": "04005", "countyname": "Coconino", "stateabbr": "AZ",
     "diabetes_crudeprev": "8.7", "obesity_crudeprev": "24.5", "csmoking_crudeprev": "12.2",
     "year": "2025",
     "geolocation": {"type": "Point", "coordinates": [-111.774, 35.683]}},
]

MEASURES = ["DIABETES", "OBESITY", "CSMOKING"]


# ── _parse_geolocation ────────────────────────────────────────────────────────

class TestParseGeolocation(unittest.TestCase):
    def test_parses_dict_geolocation(self):
        geo = {"type": "Point", "coordinates": [-112.491, 33.348]}
        lon, lat = fb._parse_geolocation(geo)
        self.assertAlmostEqual(lon, -112.491)
        self.assertAlmostEqual(lat,   33.348)

    def test_parses_string_geolocation(self):
        geo = "{'type': 'Point', 'coordinates': [-109.489, 35.395]}"
        lon, lat = fb._parse_geolocation(geo)
        self.assertAlmostEqual(lon, -109.489)
        self.assertAlmostEqual(lat,   35.395)

    def test_returns_none_for_none_input(self):
        lon, lat = fb._parse_geolocation(None)
        self.assertIsNone(lon)
        self.assertIsNone(lat)

    def test_returns_none_for_empty_dict(self):
        lon, lat = fb._parse_geolocation({})
        self.assertIsNone(lon)
        self.assertIsNone(lat)

    def test_returns_none_for_invalid_string(self):
        lon, lat = fb._parse_geolocation("not valid json")
        self.assertIsNone(lon)
        self.assertIsNone(lat)


# ── _build_wide_matrix (long-format rows) ────────────────────────────────────

class TestBuildWideMatrixLong(unittest.TestCase):
    def test_builds_one_row_per_county(self):
        counties = fb._build_wide_matrix(LONG_ROWS, MEASURES, "CrdPrv")
        self.assertEqual(set(counties.keys()), {"04013", "04019"})

    def test_includes_all_measures_as_columns(self):
        counties = fb._build_wide_matrix(LONG_ROWS, MEASURES, "CrdPrv")
        maricopa = counties["04013"]
        self.assertEqual(maricopa["places_diabetes_crude_prevalence"], "11.4")
        self.assertEqual(maricopa["places_obesity_crude_prevalence"], "31.2")
        self.assertEqual(maricopa["places_csmoking_crude_prevalence"], "16.1")

    def test_filters_out_non_matching_estimate_type(self):
        # age-adjusted row for Maricopa exists in LONG_ROWS but should not overwrite crude
        counties = fb._build_wide_matrix(LONG_ROWS, MEASURES, "CrdPrv")
        self.assertEqual(counties["04013"]["places_diabetes_crude_prevalence"], "11.4")

    def test_extracts_lon_lat_from_geolocation(self):
        counties = fb._build_wide_matrix(LONG_ROWS, MEASURES, "CrdPrv")
        self.assertAlmostEqual(counties["04013"]["lon"], -112.491)
        self.assertAlmostEqual(counties["04013"]["lat"],   33.348)

    def test_populates_place_name_and_state(self):
        counties = fb._build_wide_matrix(LONG_ROWS, MEASURES, "CrdPrv")
        self.assertEqual(counties["04013"]["place_name"], "Maricopa")
        self.assertEqual(counties["04013"]["state"], "AZ")

    def test_ignores_rows_with_unknown_measure(self):
        extra = [{"datavaluetypeid": "CrdPrv", "measureid": "COPD", "locationid": "04013",
                  "locationname": "Maricopa", "stateabbr": "AZ", "data_value": "6.0",
                  "year": "2023", "geolocation": None}]
        counties = fb._build_wide_matrix(extra, MEASURES, "CrdPrv")
        self.assertEqual(counties, {})


# ── _build_wide_matrix_gis (GIS Friendly Format) ─────────────────────────────

class TestBuildWideMatrixGIS(unittest.TestCase):
    def test_builds_one_row_per_county(self):
        counties = fb._build_wide_matrix_gis(GIS_ROWS, MEASURES, "crude_prevalence")
        self.assertEqual(set(counties.keys()), {"04013", "04019", "04005"})

    def test_uses_countyfips_as_geoid(self):
        counties = fb._build_wide_matrix_gis(GIS_ROWS, MEASURES, "crude_prevalence")
        self.assertEqual(counties["04013"]["geoid"], "04013")

    def test_uses_countyname_as_place_name(self):
        counties = fb._build_wide_matrix_gis(GIS_ROWS, MEASURES, "crude_prevalence")
        self.assertEqual(counties["04013"]["place_name"], "Maricopa")

    def test_maps_crudeprev_suffix_correctly(self):
        counties = fb._build_wide_matrix_gis(GIS_ROWS, MEASURES, "crude_prevalence")
        self.assertEqual(counties["04013"]["places_diabetes_crude_prevalence"], "11.4")
        self.assertEqual(counties["04019"]["places_obesity_crude_prevalence"], "29.8")
        self.assertEqual(counties["04005"]["places_csmoking_crude_prevalence"], "12.2")

    def test_extracts_lon_lat_from_geolocation(self):
        counties = fb._build_wide_matrix_gis(GIS_ROWS, MEASURES, "crude_prevalence")
        self.assertAlmostEqual(counties["04013"]["lon"], -112.491)
        self.assertAlmostEqual(counties["04013"]["lat"],   33.348)

    def test_handles_age_adjusted_estimate_type(self):
        rows = [{"countyfips": "04013", "countyname": "Maricopa", "stateabbr": "AZ",
                 "diabetes_adjprev": "9.9", "obesity_adjprev": "27.1",
                 "csmoking_adjprev": "13.0", "year": "2025",
                 "geolocation": {"type": "Point", "coordinates": [-112.491, 33.348]}}]
        counties = fb._build_wide_matrix_gis(rows, MEASURES, "age_adjusted_prevalence")
        self.assertEqual(counties["04013"]["places_diabetes_crude_prevalence"], "9.9")


# ── _select_geographies ───────────────────────────────────────────────────────

class TestSelectGeographies(unittest.TestCase):
    def _counties(self):
        return fb._build_wide_matrix_gis(GIS_ROWS, MEASURES, "crude_prevalence")

    def test_top_n_returns_correct_count(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "top_n", 2, None)
        self.assertEqual(len(selected), 2)

    def test_top_n_orders_descending(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "top_n", 3, None)
        values = [float(c["places_diabetes_crude_prevalence"]) for c in selected]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_top_n_selects_highest_value_county_first(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "top_n", 1, None)
        self.assertEqual(selected[0]["geoid"], "04013")  # Maricopa has 11.4

    def test_threshold_gte_excludes_counties_below_threshold(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "threshold_gte", None, 10.0)
        geoids = {c["geoid"] for c in selected}
        self.assertIn("04013", geoids)   # 11.4 ≥ 10.0
        self.assertIn("04019", geoids)   # 10.9 ≥ 10.0
        self.assertNotIn("04005", geoids)  # 8.7 < 10.0

    def test_populates_rank_field(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "top_n", 3, None)
        for i, c in enumerate(selected, 1):
            self.assertEqual(c["_rank"], i)

    def test_populates_selection_value_field(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "top_n", 1, None)
        self.assertEqual(selected[0]["_sel_val"], "11.4")

    def test_populates_reason_field(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "top_n", 1, None)
        self.assertIn("DIABETES", selected[0]["_reason"])
        self.assertIn("top_n", selected[0]["_reason"])

    def test_top_n_larger_than_available_returns_all(self):
        selected = fb._select_geographies(self._counties(), "DIABETES", "top_n", 99, None)
        self.assertEqual(len(selected), len(GIS_ROWS))

    def test_empty_counties_returns_empty(self):
        selected = fb._select_geographies({}, "DIABETES", "top_n", 5, None)
        self.assertEqual(selected, [])


# ── CSV writers ───────────────────────────────────────────────────────────────

class TestWriters(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.counties = fb._build_wide_matrix_gis(GIS_ROWS, MEASURES, "crude_prevalence")
        self.selected = fb._select_geographies(self.counties, "DIABETES", "top_n", 2, None)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _read_csv(self, path):
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_write_raw_produces_csv_with_all_rows(self):
        path = self.tmp / "raw.csv"
        fb._write_raw(GIS_ROWS, str(path))
        rows = self._read_csv(path)
        self.assertEqual(len(rows), len(GIS_ROWS))
        self.assertIn("countyfips", rows[0])

    def test_write_wide_produces_one_row_per_county(self):
        path = self.tmp / "wide.csv"
        fb._write_wide(self.counties, MEASURES, str(path))
        rows = self._read_csv(path)
        self.assertEqual(len(rows), len(GIS_ROWS))
        self.assertIn("places_diabetes_crude_prevalence", rows[0])
        self.assertIn("places_obesity_crude_prevalence", rows[0])

    def test_write_wide_includes_required_columns(self):
        path = self.tmp / "wide.csv"
        fb._write_wide(self.counties, MEASURES, str(path))
        rows = self._read_csv(path)
        required = {"geo_level", "geoid", "state", "place_name"}
        self.assertTrue(required.issubset(rows[0].keys()))

    def test_write_selected_produces_correct_row_count(self):
        path = self.tmp / "selected.csv"
        fb._write_selected(self.selected, "DIABETES", "top_n", "crude_prevalence", str(path))
        rows = self._read_csv(path)
        self.assertEqual(len(rows), 2)

    def test_write_selected_includes_required_columns(self):
        path = self.tmp / "selected.csv"
        fb._write_selected(self.selected, "DIABETES", "top_n", "crude_prevalence", str(path))
        rows = self._read_csv(path)
        required = {"site_id", "geo_level", "geoid", "state", "place_name",
                    "selection_measure", "selection_rank", "selection_reason"}
        self.assertTrue(required.issubset(rows[0].keys()))

    def test_write_selected_site_id_format(self):
        path = self.tmp / "selected.csv"
        fb._write_selected(self.selected, "DIABETES", "top_n", "crude_prevalence", str(path))
        rows = self._read_csv(path)
        for row in rows:
            self.assertTrue(row["site_id"].startswith("county_"))

    def test_write_manifest_has_lon_lat(self):
        path = self.tmp / "manifest.csv"
        fb._write_manifest(self.selected, "DIABETES", str(path))
        rows = self._read_csv(path)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertTrue(row["lon"])
            self.assertTrue(row["lat"])

    def test_write_manifest_includes_required_columns(self):
        path = self.tmp / "manifest.csv"
        fb._write_manifest(self.selected, "DIABETES", str(path))
        rows = self._read_csv(path)
        required = {"site_id", "geo_level", "geoid", "state", "lon", "lat",
                    "selection_measure", "selection_value", "selection_reason"}
        self.assertTrue(required.issubset(rows[0].keys()))

    def test_write_feature_dict_one_row_per_measure(self):
        path = self.tmp / "dict.csv"
        fb._write_feature_dict(MEASURES, "crude_prevalence", str(path))
        rows = self._read_csv(path)
        self.assertEqual(len(rows), len(MEASURES))
        col_names = {r["column_name"] for r in rows}
        self.assertIn("places_diabetes_crude_prevalence", col_names)

    def test_write_long_produces_rows_for_each_county_and_measure(self):
        long_rows = fb._gis_to_long_rows(
            GIS_ROWS, MEASURES, "crude_prevalence",
            provenance_id="run_test", retrieved_at="2026-01-01T00:00:00Z"
        )
        path = self.tmp / "long.csv"
        fb._write_long(long_rows, MEASURES, "CrdPrv", "crude_prevalence",
                       "run_test", "2026-01-01T00:00:00Z", str(path))
        rows = self._read_csv(path)
        # 3 counties × 3 measures = 9 rows
        self.assertEqual(len(rows), 9)
        self.assertIn("measure_id", rows[0])
        self.assertIn("estimate_value", rows[0])


# ── _gis_to_long_rows ─────────────────────────────────────────────────────────

class TestGisToLongRows(unittest.TestCase):
    def test_produces_one_row_per_county_per_measure(self):
        rows = fb._gis_to_long_rows(GIS_ROWS, MEASURES, "crude_prevalence",
                                    "run_test", "2026-01-01T00:00:00Z")
        self.assertEqual(len(rows), len(GIS_ROWS) * len(MEASURES))

    def test_row_has_measureid_and_data_value(self):
        rows = fb._gis_to_long_rows(GIS_ROWS, MEASURES, "crude_prevalence",
                                    "run_test", "2026-01-01T00:00:00Z")
        measure_ids = {r["measureid"] for r in rows}
        self.assertEqual(measure_ids, set(MEASURES))

    def test_skips_rows_with_missing_measure_value(self):
        sparse = [{"countyfips": "04013", "countyname": "Maricopa", "stateabbr": "AZ",
                   "diabetes_crudeprev": "11.4",
                   # no obesity_crudeprev or csmoking_crudeprev
                   "year": "2025", "geolocation": None}]
        rows = fb._gis_to_long_rows(sparse, MEASURES, "crude_prevalence",
                                    "run_test", "2026-01-01T00:00:00Z")
        self.assertEqual(len(rows), 1)  # only DIABETES has a value


# ── _make_dirs ────────────────────────────────────────────────────────────────

class TestMakeDirs(unittest.TestCase):
    def test_creates_all_required_subdirectories(self):
        with tempfile.TemporaryDirectory() as root:
            outdir = os.path.join(root, "output")
            dirs = fb._make_dirs(outdir)
            for key in ("raw", "derived", "selected", "metadata", "qa", "logs"):
                self.assertIn(key, dirs)
                self.assertTrue(os.path.isdir(dirs[key]),
                                f"Expected {key} directory to exist")

    def test_returns_dict_of_absolute_paths(self):
        with tempfile.TemporaryDirectory() as root:
            outdir = os.path.join(root, "output")
            dirs = fb._make_dirs(outdir)
            for path in dirs.values():
                self.assertTrue(os.path.isabs(path))


# ── Full pipeline integration (live CDC API) ──────────────────────────────────

class TestFeatureBuilderIntegration(unittest.TestCase):
    """Runs the full feature builder pipeline against the live CDC API.
    Skipped automatically if the network is unavailable."""

    def test_full_pipeline_az_top5_diabetes(self):
        with tempfile.TemporaryDirectory() as outdir:
            try:
                dataset_id = fb._find_county_dataset(log=None)
            except Exception as exc:
                self.skipTest(f"CDC dataset discovery failed: {exc}")

            fmt = fb._probe_format(dataset_id, "AZ")
            self.assertIn(fmt, ("long", "gis_friendly"))

            if fmt == "gis_friendly":
                where = "stateabbr = 'AZ'"
            else:
                where = "stateabbr = 'AZ' AND measureid IN ('DIABETES','OBESITY','CSMOKING')"

            try:
                df = _fetch_mod.fetch_places_data(dataset_id=dataset_id, where=where,
                                                   verbose=False)
            except Exception as exc:
                self.skipTest(f"Live CDC data fetch failed: {exc}")

            rows = df.to_dict_records() if hasattr(df, "to_dict_records") else df.to_dict("records")
            self.assertGreater(len(rows), 0)

            if fmt == "gis_friendly":
                counties = fb._build_wide_matrix_gis(rows, MEASURES, "crude_prevalence")
            else:
                counties = fb._build_wide_matrix(rows, MEASURES, "CrdPrv")

            self.assertGreater(len(counties), 0)

            selected = fb._select_geographies(counties, "DIABETES", "top_n", 5, None)
            self.assertEqual(len(selected), 5)

            # All selected must have lon/lat
            for c in selected:
                self.assertIsNotNone(c.get("lon"), f"Missing lon for {c['geoid']}")
                self.assertIsNotNone(c.get("lat"), f"Missing lat for {c['geoid']}")

            # Write the full output bundle and verify all files exist
            dirs = fb._make_dirs(outdir)

            raw_path      = os.path.join(dirs["raw"],      "cdc_places_raw_extract.csv")
            wide_path     = os.path.join(dirs["derived"],  "cdc_places_features_wide.csv")
            sel_path      = os.path.join(dirs["selected"], "selected_geographies.csv")
            manifest_path = os.path.join(dirs["selected"], "amadeus_location_manifest.csv")

            fb._write_raw(rows, raw_path)
            fb._write_wide(counties, MEASURES, wide_path)
            fb._write_selected(selected, "DIABETES", "top_n", "crude_prevalence", sel_path)
            fb._write_manifest(selected, "DIABETES", manifest_path)

            for path in (raw_path, wide_path, sel_path, manifest_path):
                self.assertTrue(os.path.exists(path), f"Missing output file: {path}")

            # Validate manifest content
            with open(manifest_path, newline="", encoding="utf-8") as f:
                manifest_rows = list(csv.DictReader(f))
            self.assertEqual(len(manifest_rows), 5)
            self.assertTrue(all(r["lon"] and r["lat"] for r in manifest_rows))
            self.assertTrue(all(r["geoid"] for r in manifest_rows))
            self.assertTrue(all(r["site_id"].startswith("county_") for r in manifest_rows))


if __name__ == "__main__":
    unittest.main()
