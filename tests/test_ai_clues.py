import unittest
from datetime import date, datetime, timezone

from backend.contextos.ai_clues import interpret, reasons


class SearchClueTest(unittest.TestCase):
    def test_last_month_source_and_image_are_soft_hints(self):
        clues = interpret("the blue screenshot from example.org last month", date(2026, 11, 21))
        self.assertEqual(clues["approx_date"], (date(2026, 10, 1), date(2026, 11, 1)))
        self.assertEqual(clues["source_domain"], "example.org")
        self.assertEqual(clues["kind"], "image")
        row = {"captured_at": datetime(2026, 10, 9, tzinfo=timezone.utc),
               "source_domain": "example.org", "kind": "image"}
        self.assertEqual(reasons(row, clues, explicit_date=False, explicit_domain=False, explicit_kind=False),
                         ["approximate_date", "source_hint", "type_hint"])
        self.assertEqual(reasons(row, clues, explicit_date=True, explicit_domain=True, explicit_kind=True), [])

    def test_calendar_month_and_unrecognized_text(self):
        clues = interpret("paper from October 2026", date(2026, 11, 21))
        self.assertEqual(clues["approx_date"], (date(2026, 10, 1), date(2026, 11, 1)))
        self.assertEqual(clues["kind"], "pdf")
        self.assertEqual(interpret("a chart about memory", date(2026, 11, 21)), {})


if __name__ == "__main__":
    unittest.main()
