import unittest
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from expand_rank_role_stratified_cohort import (
    checkpoint_path_for,
    grid_counts,
    is_full,
    load_checkpoint,
    parse_role_targets,
    quota_grid,
    stratum_for_tier,
    write_checkpoint,
)


class RankRoleCohortTests(unittest.TestCase):
    def test_role_targets(self):
        self.assertEqual(
            {"TOP": 20, "JUNGLE": 20, "MIDDLE": 20, "BOTTOM": 20, "UTILITY": 20},
            parse_role_targets("TOP:20,JUNGLE:20,MIDDLE:20,BOTTOM:20,UTILITY:20"),
        )

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            parse_role_targets("TOP:20,FILL:80")

    def test_master_plus_mapping(self):
        self.assertEqual("MASTER_PLUS", stratum_for_tier("CHALLENGER"))
        self.assertEqual("MASTER_PLUS", stratum_for_tier("GRANDMASTER"))
        self.assertEqual("MASTER_PLUS", stratum_for_tier("MASTER"))
        self.assertEqual("DIAMOND", stratum_for_tier("DIAMOND"))

    def test_grid_completeness(self):
        grid = quota_grid(("GOLD",), 2, {"TOP": 1, "JUNGLE": 1})
        players = [
            {"seed_stratum": "GOLD", "primary_role": "TOP"},
            {"seed_stratum": "GOLD", "primary_role": "JUNGLE"},
        ]
        self.assertTrue(is_full(grid_counts(players), grid))

    def test_grid_missing_role(self):
        grid = quota_grid(("GOLD",), 2, {"TOP": 1, "JUNGLE": 1})
        counts = defaultdict(Counter)
        counts["GOLD"]["TOP"] = 1
        self.assertFalse(is_full(counts, grid))

    def test_checkpoint_roundtrip(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "cohort.json"
            checkpoint = checkpoint_path_for(output)
            args = Mock(
                random_seed=7,
                players_per_stratum=2,
                role_probe_matches=50,
                min_role_probe_matches=10,
            )
            selected = [
                {
                    "anonymized_player_id": "P001",
                    "puuid": "synthetic-a",
                    "seed_tier": "GOLD",
                    "seed_stratum": "GOLD",
                    "primary_role": "TOP",
                }
            ]
            role_targets = {"TOP": 1, "JUNGLE": 1}
            write_checkpoint(
                checkpoint,
                args,
                "NA1",
                ("GOLD",),
                role_targets,
                123456,
                selected,
                Counter({"GOLD:duplicate": 2}),
            )
            end_time, loaded, rejections = load_checkpoint(
                checkpoint,
                args,
                "NA1",
                ("GOLD",),
                role_targets,
            )
            self.assertEqual(123456, end_time)
            self.assertEqual(selected, loaded)
            self.assertEqual(2, rejections["GOLD:duplicate"])

    def test_checkpoint_setting_mismatch_rejected(self):
        with TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "cohort.checkpoint.json"
            args = Mock(
                random_seed=7,
                players_per_stratum=2,
                role_probe_matches=50,
                min_role_probe_matches=10,
            )
            write_checkpoint(
                checkpoint,
                args,
                "NA1",
                ("GOLD",),
                {"TOP": 1, "JUNGLE": 1},
                123456,
                [],
                Counter(),
            )
            with self.assertRaises(ValueError):
                load_checkpoint(checkpoint, args, "NA1", ("PLATINUM",), {"TOP": 1, "JUNGLE": 1})


if __name__ == "__main__":
    unittest.main()
