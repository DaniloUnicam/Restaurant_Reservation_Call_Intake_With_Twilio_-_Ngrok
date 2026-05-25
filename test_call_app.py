from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import call_app
from call_app import (
    handle_transcription,
    incoming_choice_twiml,
    incoming_twiml,
    reservation_twiml,
    voice_twiml,
)


class CallAppTests(TestCase):
    def test_voice_twiml_asks_for_reservation_details(self):
        xml = voice_twiml().decode()

        self.assertIn('<Gather input="speech"', xml)
        self.assertIn('action="/reservation"', xml)
        self.assertIn("number of people", xml)

    def test_incoming_twiml_listens_in_italian(self):
        with patch.dict(
            call_app.os.environ,
            {
                "PUBLIC_BASE_URL": "https://example.test",
                "RESTAURANT_FORWARD_NUMBER": "+390123456789",
                "TWILIO_FROM_NUMBER": "+390987654321",
            },
        ):
            xml = incoming_twiml().decode()

        self.assertIn("<Start>", xml)
        self.assertIn("<Transcription", xml)
        self.assertIn('languageCode="it-IT"', xml)
        self.assertIn('<Gather input="dtmf"', xml)
        self.assertIn('action="/incoming-choice"', xml)
        self.assertIn("<Dial", xml)
        self.assertIn("+390123456789", xml)

    def test_incoming_choice_one_dials_restaurant(self):
        with patch.dict(
            call_app.os.environ,
            {
                "PUBLIC_BASE_URL": "https://example.test",
                "RESTAURANT_FORWARD_NUMBER": "+390123456789",
            },
        ):
            xml = incoming_choice_twiml("1").decode()

        self.assertIn("<Dial", xml)
        self.assertIn("+390123456789", xml)

    def test_incoming_choice_invalid_redirects_to_menu(self):
        xml = incoming_choice_twiml("9").decode()

        self.assertIn("<Redirect", xml)
        self.assertIn("/incoming?attempts=1", xml)

    def test_reservation_twiml_confirms_complete_request(self):
        with TemporaryDirectory() as directory:
            call_app.DATA_FILE = call_app.Path(directory) / "reservations.jsonl"
            xml = reservation_twiml("A table for four tomorrow at 7:30 pm").decode()

        self.assertIn("ho salvato un tavolo per 4 persone", xml)
        self.assertIn("<Hangup/>", xml)

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
