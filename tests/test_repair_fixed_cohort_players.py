import unittest

from repair_fixed_cohort_players import merge_rows


def row(player, match, ts, champion="A"):
    return {
        "anonymized_player_id": player,
        "matchId": match,
        "gameStartTimestamp": str(ts),
        "championName": champion,
    }


class RepairMergeTests(unittest.TestCase):
    def test_merge_preserves_fallback_and_deduplicates(self):
        fallback = [row("P019", "M1", 1), row("P019", "M2", 2)]
        deeper = [row("P019", "M2", 2, "updated"), row("P019", "M3", 3)]
        result = merge_rows(fallback, deeper, max_matches=3)
        self.assertEqual(["M3", "M2", "M1"], [r["matchId"] for r in result])
        self.assertEqual("updated", next(r for r in result if r["matchId"] == "M2")["championName"])

    def test_merge_applies_per_player_cap(self):
        rows = [row("P019", f"M{i}", i) for i in range(4)] + [row("P020", f"N{i}", i) for i in range(4)]
        result = merge_rows(rows, max_matches=2)
        self.assertEqual(4, len(result))
        self.assertEqual({"P019", "P020"}, {r["anonymized_player_id"] for r in result})


if __name__ == "__main__":
    unittest.main()
