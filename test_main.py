from datetime import date
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from main import parse_reservation, parse_reservation_with_claude


class ReservationParserTests(TestCase):
    def test_parses_people_relative_day_and_pm_time(self):
        reservation = parse_reservation(
            "Hi, I need a table for four tomorrow at 7:30 pm.",
            today=date(2026, 5, 21),
        )

        self.assertEqual(reservation.people, 4)
        self.assertEqual(reservation.day, "2026-05-22")
        self.assertEqual(reservation.time, "19:30")
        self.assertTrue(reservation.is_complete)

    def test_parses_party_size_weekday_and_24_hour_time(self):
        reservation = parse_reservation(
            "Can I reserve a party of 6 for Saturday at 20:15?",
            today=date(2026, 5, 21),
        )

        self.assertEqual(reservation.people, 6)
        self.assertEqual(reservation.day, "2026-05-23")
        self.assertEqual(reservation.time, "20:15")

    def test_parses_numeric_date(self):
        reservation = parse_reservation(
            "Reservation for two on 06/03 at 8pm",
            today=date(2026, 5, 21),
        )

        self.assertEqual(reservation.people, 2)
        self.assertEqual(reservation.day, "2026-06-03")
        self.assertEqual(reservation.time, "20:00")

    def test_parses_italian_reservation_sentence(self):
        reservation = parse_reservation(
            "Ciao, vorrei prenotare un tavolo per 4 persone alle 8:30 di lunedi 25 maggio",
            today=date(2026, 5, 21),
        )

        self.assertEqual(reservation.people, 4)
        self.assertEqual(reservation.day, "2026-05-25")
        self.assertEqual(reservation.time, "08:30")

    def test_claude_sdk_parser_reads_json_response(self):
        response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text='{"people": 3, "day": "2026-05-22", "time": "19:45"}',
                )
            ]
        )

        with patch("anthropic.Anthropic") as client_class:
            client_class.return_value.messages.create.return_value = response
            reservation = parse_reservation_with_claude(
                "Prenota per tre domani alle 19:45",
                today=date(2026, 5, 21),
            )

        self.assertEqual(reservation.people, 3)
        self.assertEqual(reservation.day, "2026-05-22")
        self.assertEqual(reservation.time, "19:45")
        client_class.return_value.messages.create.assert_called_once()


if __name__ == "__main__":
    main()
