import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import build_changed_champion_expansion as mod


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "build_changed_champion_expansion.py"


class ChangedChampionExpansionTests(unittest.TestCase):
    def test_official_event_universe_is_unique_and_official(self):
        events = [(patch, champion) for patch, (_, _, _, champions) in mod.PATCHES.items() for champion in champions]
        self.assertEqual(258, len(events))
        self.assertEqual(len(events), len(set(events)))
        for _, (_, _, url, champions) in mod.PATCHES.items():
            self.assertTrue(url.startswith("https://www.leagueoflegends.com/"))
            self.assertTrue(champions)

    def test_outputs_use_anonymized_ids_only(self):
        with tempfile.TemporaryDirectory() as td:
            matches = Path(td) / "matches.csv"
            out = Path(td) / "out"
            with matches.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "anonymized_player_id",
                        "gameStartTimestamp",
                        "matchId",
                        "patch",
                        "championName",
                    ],
                )
                writer.writeheader()
                for player_index in range(1, 21):
                    for match_index in range(101):
                        writer.writerow(
                            {
                                "anonymized_player_id": f"P{player_index:03d}",
                                "gameStartTimestamp": player_index * 1_000_000 + match_index,
                                "matchId": f"TEST_{player_index}_{match_index}",
                                "patch": "16.1" if match_index < 100 else "16.2",
                                "championName": "Ashe",
                            }
                        )
            subprocess.run(
                [sys.executable, str(SCRIPT), "--matches", str(matches), "--out-dir", str(out)],
                check=True,
            )
            with (out / "official_changed_champion_patch_table.csv").open(encoding="utf-8-sig") as f:
                official = list(csv.DictReader(f))
            with (out / "sample_size_expansion_test.csv").open(encoding="utf-8-sig") as f:
                expansion = list(csv.DictReader(f))
            self.assertEqual(258, len(official))
            self.assertEqual({"20", "100", "300", "500"}, {r["target_players"] for r in expansion})
            private_ids = ["private-account-id-1", "private-account-id-2"]
            for path in out.iterdir():
                text = path.read_text(encoding="utf-8-sig")
                self.assertNotIn("RGAPI-", text)
                for private_id in private_ids:
                    self.assertNotIn(private_id, text)


if __name__ == "__main__":
    unittest.main()
