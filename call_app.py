from __future__ import annotations

import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app_config import HOST, JSON_CONTENT_TYPE, PORT, TEXT_CONTENT_TYPE, XML_CONTENT_TYPE, load_dotenv
from reservation_ai import extract_json_object, parse_reservation_smart
from storage import get_reservations_from_supabase, load_local_reservations
from twilio_client import make_outbound_call
from voice_flow import (
    dial_status_twiml,
    handle_recording,
    handle_transcription,
    incoming_choice_twiml,
    incoming_twiml,
    reservation_twiml,
    twiml,
    voice_twiml,
)


def parse_form(body: bytes) -> dict[str, str]:
    """Parse a Twilio form-encoded webhook body into a plain dictionary."""
    parsed = urllib.parse.parse_qs(body.decode(), keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


class Handler(BaseHTTPRequestHandler):
    """HTTP request handler for status pages and Twilio webhooks."""

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path

        if path == "/":
            self.respond_text(
                "Restaurant call app is running.\n"
                "Configure your Twilio phone number voice webhook to POST /incoming.\n"
                "Optional: POST /call with target_number=+15551234567 to start a test call.\n"
            )
        elif path == "/incoming":
            self.respond_xml(incoming_twiml())
        elif path == "/voice":
            self.respond_xml(voice_twiml())
        elif path == "/reservations":
            reservations = get_reservations_from_supabase() or load_local_reservations()
            self.respond_json({"reservations": reservations})
        else:
            self.respond_text("Not found\n", status=404)

    def do_POST(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_form(self.rfile.read(length))

        if parsed_path.path == "/call":
            self.handle_call(form)
        elif parsed_path.path == "/voice":
            self.respond_xml(voice_twiml())
        elif parsed_path.path == "/incoming":
            self.respond_xml(incoming_twiml(form.get("From", "")))
        elif parsed_path.path == "/incoming-choice":
            attempts = int(query.get("attempts", ["0"])[0])
            self.respond_xml(incoming_choice_twiml(form.get("Digits", ""), attempts))
        elif parsed_path.path == "/transcription":
            handle_transcription(form)
            self.respond_xml(twiml(""))
        elif parsed_path.path == "/recording":
            handle_recording(form)
            self.respond_xml(twiml(""))
        elif parsed_path.path == "/dial-status":
            self.respond_xml(dial_status_twiml(form))
        elif parsed_path.path == "/reservation":
            previous_text = query.get("context", [""])[0]
            self.respond_xml(
                reservation_twiml(
                    form.get("SpeechResult", ""),
                    previous_text,
                    form.get("CallSid", ""),
                )
            )
        else:
            self.respond_text("Not found\n", status=404)

    def handle_call(self, form: dict[str, str]) -> None:
        target = form.get("target_number") or os.getenv("RESTAURANT_PHONE_NUMBER")
        if not target:
            self.respond_json({"error": "Missing target_number or RESTAURANT_PHONE_NUMBER"}, 400)
            return

        try:
            result = make_outbound_call(target)
        except KeyError as error:
            self.respond_json({"error": f"Missing environment variable: {error.args[0]}"}, 500)
            return
        except Exception as error:
            self.respond_json({"error": str(error)}, 502)
            return

        self.respond_json({"call_sid": result.get("sid"), "status": result.get("status")})

    def respond_xml(self, body: bytes, status: int = 200) -> None:
        self.respond(body, XML_CONTENT_TYPE, status)

    def respond_json(self, value: dict[str, object], status: int = 200) -> None:
        self.respond(json.dumps(value).encode(), JSON_CONTENT_TYPE, status)

    def respond_text(self, value: str, status: int = 200) -> None:
        self.respond(value.encode(), TEXT_CONTENT_TYPE, status)

    def respond(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Start the Twilio webhook server."""
    load_dotenv()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Listening on http://{HOST}:{PORT}")
    print("Set the Twilio phone number Voice webhook to PUBLIC_BASE_URL/incoming.")
    server.serve_forever()


if __name__ == "__main__":
    main()
