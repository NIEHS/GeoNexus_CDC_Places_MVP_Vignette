import importlib.util
import csv
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "CDC Places" / "cdc_places_fetch.py"
MODULE_SPEC = importlib.util.spec_from_file_location("cdc_places_fetch", MODULE_PATH)
cdc_places_fetch = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules.setdefault("requests", types.SimpleNamespace())
MODULE_SPEC.loader.exec_module(cdc_places_fetch)


class TestBuildWhereClause(unittest.TestCase):
    def test_returns_none_when_no_filters_are_provided(self):
        self.assertIsNone(cdc_places_fetch.build_where_clause())

    def test_uses_state_abbreviation_for_two_letter_state(self):
        clause = cdc_places_fetch.build_where_clause(state="nc")
        self.assertEqual(clause, "stateabbr = 'NC'")

    def test_uses_state_name_for_long_state_values(self):
        clause = cdc_places_fetch.build_where_clause(state="North Carolina")
        self.assertEqual(clause, "statedesc = 'North Carolina'")

    def test_combines_all_supported_filters(self):
        clause = cdc_places_fetch.build_where_clause(
            state="AZ",
            county="Pima",
            measure="diabetes",
            extra_where="datavaluetypeid = 'CrudePrev'",
            zipcode="85701",
            lat=32.22,
            lon=-110.97,
            radius_m=5000,
        )

        self.assertEqual(
            clause,
            " AND ".join(
                [
                    "stateabbr = 'AZ'",
                    "upper(countyname) like upper('%Pima%')",
                    "measureid = 'DIABETES'",
                    "locationid = '85701'",
                    "within_circle(geolocation, 32.22, -110.97, 5000)",
                    "(datavaluetypeid = 'CrudePrev')",
                ]
            ),
        )

    def test_zero_pads_zipcodes(self):
        clause = cdc_places_fetch.build_where_clause(zipcode="2701")
        self.assertEqual(clause, "locationid = '02701'")


class TestCountySelectionIntegration(unittest.TestCase):
    def test_exports_top_az_counties_by_diabetes_to_csv(self):
        sample_rows = [
            {"locationid": "04013", "countyname": "Maricopa", "stateabbr": "AZ", "measureid": "DIABETES", "datavaluetypeid": "CrudePrev", "data_value": "11.4"},
            {"locationid": "04013", "countyname": "Maricopa", "stateabbr": "AZ", "measureid": "OBESITY", "datavaluetypeid": "CrudePrev", "data_value": "31.2"},
            {"locationid": "04013", "countyname": "Maricopa", "stateabbr": "AZ", "measureid": "CSMOKING", "datavaluetypeid": "CrudePrev", "data_value": "16.1"},
            {"locationid": "04019", "countyname": "Pima", "stateabbr": "AZ", "measureid": "DIABETES", "datavaluetypeid": "CrudePrev", "data_value": "10.9"},
            {"locationid": "04019", "countyname": "Pima", "stateabbr": "AZ", "measureid": "OBESITY", "datavaluetypeid": "CrudePrev", "data_value": "29.8"},
            {"locationid": "04019", "countyname": "Pima", "stateabbr": "AZ", "measureid": "CSMOKING", "datavaluetypeid": "CrudePrev", "data_value": "14.7"},
            {"locationid": "04005", "countyname": "Coconino", "stateabbr": "AZ", "measureid": "DIABETES", "datavaluetypeid": "CrudePrev", "data_value": "8.7"},
            {"locationid": "04005", "countyname": "Coconino", "stateabbr": "AZ", "measureid": "OBESITY", "datavaluetypeid": "CrudePrev", "data_value": "24.5"},
            {"locationid": "04005", "countyname": "Coconino", "stateabbr": "AZ", "measureid": "CSMOKING", "datavaluetypeid": "CrudePrev", "data_value": "12.2"},
            {"locationid": "06037", "countyname": "Los Angeles", "stateabbr": "CA", "measureid": "DIABETES", "datavaluetypeid": "CrudePrev", "data_value": "9.8"},
            {"locationid": "06037", "countyname": "Los Angeles", "stateabbr": "CA", "measureid": "OBESITY", "datavaluetypeid": "CrudePrev", "data_value": "26.1"},
            {"locationid": "06037", "countyname": "Los Angeles", "stateabbr": "CA", "measureid": "CSMOKING", "datavaluetypeid": "CrudePrev", "data_value": "11.8"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "az_top_counties.csv"
            exported_rows = cdc_places_fetch.export_top_counties_by_measure(
                rows=sample_rows,
                state="AZ",
                measures=["DIABETES", "OBESITY", "CSMOKING"],
                estimate_type="crude_prevalence",
                ranking_measure="DIABETES",
                top_n=2,
                out_path=str(output_path),
            )

            self.assertEqual(
                exported_rows,
                [
                    {
                        "locationid": "04013",
                        "countyname": "Maricopa",
                        "stateabbr": "AZ",
                        "diabetes": "11.4",
                        "obesity": "31.2",
                        "csmoking": "16.1",
                    },
                    {
                        "locationid": "04019",
                        "countyname": "Pima",
                        "stateabbr": "AZ",
                        "diabetes": "10.9",
                        "obesity": "29.8",
                        "csmoking": "14.7",
                    },
                ],
            )

            with output_path.open(newline="", encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))

        self.assertEqual(csv_rows, exported_rows)


class TestLiveCdcPlacesIntegration(unittest.TestCase):
    def _find_county_dataset_id(self):
        datasets = cdc_places_fetch.discover_datasets(query="PLACES county", limit=25)
        for dataset in datasets:
            haystack = " ".join(
                [
                    dataset.get("name", ""),
                    dataset.get("description", ""),
                    dataset.get("category", ""),
                ]
            ).lower()
            if "places" in haystack and "county" in haystack:
                return dataset["id"]
        self.fail("Could not find a county-level CDC PLACES dataset from discovery results.")

    def test_fetch_metadata_and_live_az_vignette_slice_to_csv(self):
        try:
            dataset_id = self._find_county_dataset_id()
            metadata = cdc_places_fetch.fetch_metadata(dataset_id)
        except Exception as exc:
            self.skipTest(f"Live CDC metadata request failed: {exc}")

        self.assertEqual(metadata.get("id"), dataset_id)
        self.assertTrue(metadata.get("name"))
        column_names = {
            column.get("fieldName")
            for column in metadata.get("columns", [])
            if column.get("fieldName")
        }
        self.assertIn("stateabbr", column_names)
        self.assertIn("countyname", column_names)
        self.assertIn("diabetes_crudeprev", column_names)
        self.assertIn("obesity_crudeprev", column_names)
        self.assertIn("csmoking_crudeprev", column_names)

        where = cdc_places_fetch.build_where_clause(state="AZ")
        try:
            df = cdc_places_fetch.fetch_places_data(
                dataset_id=dataset_id,
                where=where,
                select="countyfips,countyname,stateabbr,diabetes_crudeprev,obesity_crudeprev,csmoking_crudeprev",
                limit=5,
                verbose=False,
            )
        except Exception as exc:
            self.skipTest(f"Live CDC data request failed: {exc}")

        self.assertGreater(len(df), 0)
        self.assertIn("countyfips", df.columns)
        self.assertIn("diabetes_crudeprev", df.columns)

        output_dir = os.environ.get("OUTPUT_DIR")
        if output_dir:
            output_path = Path(output_dir) / "az_county_diabetes_live.csv"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)
            with output_path.open(newline="", encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "az_county_diabetes_live.csv"
                df.to_csv(output_path, index=False)
                with output_path.open(newline="", encoding="utf-8") as handle:
                    csv_rows = list(csv.DictReader(handle))

        self.assertGreater(len(csv_rows), 0)
        self.assertTrue(all(row["stateabbr"] == "AZ" for row in csv_rows))
        self.assertTrue(all(row["diabetes_crudeprev"] for row in csv_rows))
