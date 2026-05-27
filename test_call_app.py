from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import call_app
from call_app import (
    extract_json_object,
    handle_transcription,
    incoming_choice_twiml,
    incoming_twiml,
    parse_reservation_smart,
    reservation_twiml,
    voice_twiml,
)


class CallAppTests(TestCase):
    def test_voice_twiml_asks_for_reservation_details(self):
        xml = voice_twiml().decode()

        self.assertIn('<Gather input="dtmf speech"', xml)
        self.assertIn('language="it-IT"', xml)
        self.assertIn('action="/reservation"', xml)
        self.assertIn("numero di persone", xml)

    def test_incoming_twiml_listens_in_italian(self):
        xml = incoming_twiml().decode()

        self.assertIn('<Gather input="dtmf speech"', xml)
        self.assertIn('language="it-IT"', xml)
        self.assertIn('action="/reservation"', xml)
        self.assertNotIn("<Dial", xml)

    def test_incoming_choice_returns_to_voice_agent(self):
        xml = incoming_choice_twiml("1").decode()

        self.assertIn('<Gather input="dtmf speech"', xml)
        self.assertNotIn("<Transcription", xml)

    def test_incoming_choice_invalid_returns_to_voice_agent(self):
        xml = incoming_choice_twiml("9").decode()

        self.assertIn('<Gather input="dtmf speech"', xml)
        self.assertNotIn("<Redirect", xml)

    def test_reservation_twiml_confirms_complete_request(self):
        with TemporaryDirectory() as directory:
            call_app.DATA_FILE = call_app.Path(directory) / "reservations.jsonl"
            call_app.TRANSCRIPTS_FILE = call_app.Path(directory) / "transcripts.jsonl"
            xml = reservation_twiml("A table for four tomorrow at 7:30 pm").decode()

        self.assertIn("ho salvato un tavolo per 4 persone", xml)
        self.assertIn("<Hangup/>", xml)

    def test_reservation_twiml_asks_for_missing_fields_with_context(self):
        with TemporaryDirectory() as directory:
            call_app.DATA_FILE = call_app.Path(directory) / "reservations.jsonl"
            call_app.TRANSCRIPTS_FILE = call_app.Path(directory) / "transcripts.jsonl"
            xml = reservation_twiml("Siamo in quattro", call_sid="CA123").decode()

            self.assertFalse(call_app.DATA_FILE.exists())

        self.assertIn("Mi manca giorno, orario", xml)
        self.assertIn("context=Siamo+in+quattro", xml)
        self.assertIn('action="/reservation?', xml)

    def test_smart_parser_uses_genai_when_available(self):
        llm_reservation = call_app.ReservationRequest(5, "2026-05-30", "21:00", "raw")
        with patch.object(call_app, "parse_reservation_with_genai", return_value=(llm_reservation, None)):
            reservation, parser, error = parse_reservation_smart("prenota sabato sera per cinque")

        self.assertEqual(parser, "google_genai")
        self.assertIsNone(error)
        self.assertEqual(reservation.people, 5)
        self.assertEqual(reservation.day, "2026-05-30")
        self.assertEqual(reservation.time, "21:00")

    def test_smart_parser_falls_back_to_local_parser(self):
        with patch.object(call_app, "parse_reservation_with_genai", return_value=(None, "boom")):
            reservation, parser, error = parse_reservation_smart("per 4 persone domani alle 20:30")

        self.assertEqual(parser, "local")
        self.assertEqual(error, "boom")
        self.assertEqual(reservation.people, 4)
        self.assertEqual(reservation.time, "20:30")

    def test_extract_json_object_handles_markdown_fence(self):
        self.assertEqual(
            extract_json_object('```json\n{"people": 2, "day": null, "time": null}\n```'),
            '{"people": 2, "day": null, "time": null}',
        )

    def test_live_transcription_accumulates_and_saves_reservation(self):
        with TemporaryDirectory() as directory:
            call_app.DATA_FILE = call_app.Path(directory) / "reservations.jsonl"
            call_app.TRANSCRIPTS_FILE = call_app.Path(directory) / "transcripts.jsonl"
            call_app.CALL_TRANSCRIPTS.clear()
            call_app.SAVED_CALLS.clear()

            handle_transcription(
                {
                    "TranscriptionEvent": "transcription-content",
                    "Final": "true",
                    "CallSid": "CA123",
                    "Track": "inbound_track",
                    "Timestamp": "2026-05-21T10:00:00Z",
                    "TranscriptionData": '{"transcript":"Vorrei prenotare un tavolo per 4 persone"}',
                }
            )
            handle_transcription(
                {
                    "TranscriptionEvent": "transcription-content",
                    "Final": "true",
                    "CallSid": "CA123",
                    "Track": "inbound_track",
                    "Timestamp": "2026-05-21T10:00:03Z",
                    "TranscriptionData": '{"transcript":"alle 8:30 di lunedi 25 maggio"}',
                }
            )

            saved = call_app.DATA_FILE.read_text(encoding="utf-8")

        self.assertIn('"people": 4', saved)
        self.assertIn('"time": "08:30"', saved)
        self.assertIn('"source": "live_forwarded_call"', saved)
