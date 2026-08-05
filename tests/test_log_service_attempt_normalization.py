from __future__ import annotations

import unittest

from services.log_service import collect_image_attempts


class ImageAttemptNormalizationTests(unittest.TestCase):
    def test_boolean_values_and_true_false_strings_are_preserved(self) -> None:
        attempts = collect_image_attempts([
            {"slot": 1, "attempt": 1, "status": "failed", "switched_account": False},
            {"slot": 1, "attempt": 2, "status": "failed", "switched_account": True},
            {"slot": 1, "attempt": 3, "status": "failed", "switched_account": " false "},
            {"slot": 1, "attempt": 4, "status": "failed", "switched_account": "TRUE"},
        ])

        self.assertEqual(
            [attempt["switched_account"] for attempt in attempts],
            [False, True, False, True],
        )

    def test_invalid_boolean_values_are_omitted_instead_of_becoming_true(self) -> None:
        attempts = collect_image_attempts([
            {"slot": 1, "attempt": 1, "status": "failed", "switched_account": "falsey"},
            {"slot": 1, "attempt": 2, "status": "failed", "switched_account": "yes"},
            {"slot": 1, "attempt": 3, "status": "failed", "switched_account": 1},
        ])

        self.assertEqual(len(attempts), 3)
        self.assertTrue(all("switched_account" not in attempt for attempt in attempts))

    def test_slot_and_attempt_are_one_based_in_attempts_and_monitor_events(self) -> None:
        attempts = collect_image_attempts([{
            "slot": 0,
            "attempt": -2,
            "status": "failed",
            "monitor": {
                "events": [{
                    "event": "image_attempt_failed",
                    "slot": "0",
                    "attempt": 0,
                    "switched_account": "false",
                }],
            },
        }])

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["slot"], 1)
        self.assertEqual(attempts[0]["attempt"], 1)
        self.assertEqual(
            attempts[0]["monitor"]["events"],
            [{
                "event": "image_attempt_failed",
                "slot": 1,
                "attempt": 1,
                "switched_account": False,
            }],
        )


if __name__ == "__main__":
    unittest.main()
