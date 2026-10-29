"""The installed producer validates real inputs, not external admission records."""
from pathlib import Path
import tempfile
import unittest

from hiroute.data.shandong import produce_shandong_snapshot
from hiroute.data.shandong_spatial import read_osm_poly


class ShandongInputContractTests(unittest.TestCase):
    def test_producer_reaches_input_validation_without_prior_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.poly"
            with self.assertRaises(FileNotFoundError):
                produce_shandong_snapshot(
                    Path(directory) / "missing.pbf", missing, {}, {},
                    projection="EPSG:4326", max_distance_m=1,
                )

    def test_boundary_reader_uses_file_and_geometry_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                read_osm_poly(Path(directory) / "missing.poly")


if __name__ == "__main__":
    unittest.main()
