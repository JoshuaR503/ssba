"""Dataset replay is explicit, retains source measurements, and excludes labels."""

import json
import unittest

from wafer_project.config import PROJECT_ROOT
from wafer_project.lot_records import prepare_lot_analysis


class LotRecordTests(unittest.TestCase):
    def test_carrier_payload_uses_heldout_measurements_and_no_label_or_fake_temperature(self):
        result = prepare_lot_analysis("W001")
        self.assertTrue(result["mapping_is_demonstration_only"])
        self.assertEqual(result["record_source"], "kaggle_secom_dataset_replay")
        self.assertEqual(len(result["payload"]["features"]), 590)
        self.assertEqual(result["payload"]["context"], {"lot_id": "W001"})
        self.assertEqual(set(result["payload"]), {"record_id", "features", "context"})
        import pandas as pd

        splits = pd.read_csv(PROJECT_ROOT / "data/ai/secom-v1/data_splits.csv")
        self.assertIn(result["payload"]["record_id"], set(splits[splits.split == "test"].record_id))

    def test_unknown_carrier_is_rejected_without_calling_an_api(self):
        with self.assertRaisesRegex(ValueError, "not in"):
            prepare_lot_analysis("not-a-carrier")
