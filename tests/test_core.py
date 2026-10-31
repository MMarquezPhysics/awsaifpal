from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (  # noqa: E402
    correct_count,
    finish_session,
    is_correct,
    load_bank,
    merge_attempts,
    new_session,
    score,
    select_questions,
    valid_attempt,
    valid_session,
)


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bank = load_bank()
        cls.by_id = {question["id"]: question for question in cls.bank}

    def test_random_selection_and_family_variety(self) -> None:
        pool = [question for question in self.bank if question["origin"] == "original"]
        first = select_questions(pool, 65, random.Random(1))
        second = select_questions(pool, 65, random.Random(2))
        self.assertNotEqual([item["id"] for item in first], [item["id"] for item in second])
        self.assertEqual(len({self.by_id[item["id"]].get("family", item["id"]) for item in first}), 65)
        self.assertTrue(all(sorted(item["order"]) == list(range(len(self.by_id[item["id"]]["options"]))) for item in first))

    def test_scoring_and_saved_attempt(self) -> None:
        session = new_session(self.bank, "all", "exam", 65, 90, now_ms=1_000_000)
        self.assertTrue(valid_session(session, self.by_id))
        for item in session["items"][:13]:
            question = self.by_id[item["id"]]
            session["responses"][item["id"]] = question["answer"]
            self.assertTrue(is_correct(question, question["answer"]))
        self.assertEqual(correct_count(session, self.by_id), 13)
        self.assertEqual(score(session, self.by_id), 200)
        row = finish_session(session, self.by_id, now_ms=4_600_000)
        self.assertTrue(valid_attempt(row))
        self.assertEqual((row["questions"], row["correct"], row["elapsedMs"]), (65, 13, 3_600_000))
        self.assertEqual(len(merge_attempts([row], row)), 1)

    def test_timeout_caps_elapsed_time(self) -> None:
        session = new_session(self.bank, "provided", "guide", 10, 1, now_ms=100_000)
        row = finish_session(session, self.by_id, now_ms=200_000)
        self.assertEqual(session["finishReason"], "time")
        self.assertEqual(row["elapsedMs"], 60_000)
        self.assertEqual(finish_session(session, self.by_id, now_ms=300_000), row)


if __name__ == "__main__":
    unittest.main()
