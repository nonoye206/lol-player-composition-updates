"""Offline checks for persistent cohort identity and history boundaries."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import riot_feasibility_smoke as smoke


class FixedCohortTests(unittest.TestCase):
    def test_reuse_never_resamples_and_preserves_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cohort.json"
            client = Mock(platform="na1")
            seeds = [{"puuid": "synthetic-a"}, {"puuid": "synthetic-b"}]
            with patch.object(smoke, "seed_ranked_players", return_value=seeds) as seed:
                first = smoke.load_or_create_cohort(path, client, 2, (420,))
                second = smoke.load_or_create_cohort(path, client, 2, (420,))
                self.assertEqual(first, second)
                seed.assert_called_once()
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                smoke.load_or_create_cohort(path, client, 3, (420,))
            with self.assertRaises(ValueError):
                smoke.load_or_create_cohort(path, client, 2, (440,))
            self.assertEqual(before, path.read_bytes())

    def test_pagination_preserves_cutoff_and_prefix(self):
        calls = []
        def get(kind, path, params):
            calls.append(params)
            return [f"NA1_{i}" for i in range(params["start"], min(700, params["start"] + params["count"]))]
        client = Mock()
        client.get.side_effect = get
        small = smoke.match_ids_for_player(client, "synthetic-a", 300, (420,), 123456)
        large = smoke.match_ids_for_player(client, "synthetic-a", 500, (420,), 123456)
        self.assertEqual(small, large[:300])
        self.assertTrue(all(p["endTime"] == 123456 for p in calls))

    def test_snapshot_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "run_metadata.json"
            source.write_text(json.dumps({"players": 20}))
            smoke.snapshot_outputs(folder, "before_run")
            source.write_text("changed")
            snapshots = list((folder / "runs").glob("*/run_metadata.json"))
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(json.loads(snapshots[0].read_text()), {"players": 20})

    def test_required_sampling_design_is_checked_on_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cohort.json"
            client = Mock(platform="na1")
            cohort = {
                "schema_version": 1,
                "platform": "NA1",
                "queues": [420],
                "end_time": 123456,
                "sampling_design": "rank_by_primary_role",
                "players": [
                    {"anonymized_player_id": "P001", "puuid": "synthetic-a"},
                    {"anonymized_player_id": "P002", "puuid": "synthetic-b"},
                ],
            }
            path.write_text(json.dumps(cohort), encoding="utf-8")
            loaded = smoke.load_or_create_cohort(path, client, 2, (420,), "rank_by_primary_role")
            self.assertEqual(loaded, cohort)
            with self.assertRaises(ValueError):
                smoke.load_or_create_cohort(path, client, 2, (420,), "other_design")


if __name__ == "__main__":
    unittest.main()
