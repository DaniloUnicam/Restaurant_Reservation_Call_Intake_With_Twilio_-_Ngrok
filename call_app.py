from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.sax.saxutils import escape

from main import ReservationRequest, parse_reservation


def load_dotenv(path: str = ".env") -> None:
    """Load local environment variables without overriding real env values."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DATA_FILE = Path(os.getenv("RESERVATIONS_FILE", "reservations.jsonl"))
TRANSCRIPTS_FILE = Path(os.getenv("TRANSCRIPTS_FILE", "transcripts.jsonl"))
CALL_TRANSCRIPTS: dict[str, list[dict[str, str]]] = {}
SAVED_CALLS: set[str] = set()
MAX_MENU_ATTEMPTS = 3


def twiml(body: str) -> bytes:
    """Wrap a TwiML body in a Response document encoded for HTTP."""
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'.encode()


def public_url(path: str) -> str:
    """Build an absolute callback URL from PUBLIC_BASE_URL and a path."""
    base_url = os.environ["PUBLIC_BASE_URL"].rstrip("/")
    return f"{base_url}{path}"


def normalize_phone_number(value: str) -> str:
    """Remove whitespace from a phone number before passing it to Twilio."""
    return "".join(value.split())


def reservation_to_dict(reservation: ReservationRequest) -> dict[str, object]:
    """Convert a parsed reservation to the JSONL payload format."""
    return {
        "people": reservation.people,
        "day": reservation.day,
        "time": reservation.time,
        "is_complete": reservation.is_complete,
        "original_text": reservation.original_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def save_reservation(reservation: ReservationRequest, extra: dict[str, object] | None = None) -> None:
    """Append one parsed reservation to the configured reservations file."""
    payload = reservation_to_dict(reservation)
    if extra:
        payload.update(extra)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    """Append one dictionary as a JSON line, creating parent folders first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


def voice_twiml() -> bytes:
    """Return TwiML for the outbound speech-based reservation test call."""
    prompt = (
        "Hello. This is an automated reservation intake call. "
        "Please say the number of people, the day, and the time for the table."
    )
    gather = (
        '<Gather input="speech" speechTimeout="auto" timeout="12" '
        'action="/reservation" method="POST">'
        f"<Say>{escape(prompt)}</Say>"
        "</Gather>"
        "<Say>I did not hear the reservation details. Goodbye.</Say>"
    )
    return twiml(gather)


def dial_restaurant_twiml() -> str:
    """Return TwiML that starts transcription and dials the restaurant."""
    forward_number = os.getenv("RESTAURANT_FORWARD_NUMBER")
    if not forward_number:
        return '<Say language="it-IT">Numero del ristorante non configurato. Arrivederci.</Say>'
    forward_number = normalize_phone_number(forward_number)

    callback = escape(public_url("/transcription"))
    recording_callback = escape(public_url("/recording"))
    caller_id = escape(normalize_phone_number(os.getenv("TWILIO_FROM_NUMBER", "")))
    caller_id_attr = f' callerId="{caller_id}"' if caller_id else ""
    return (
        "<Start>"
        f'<Transcription statusCallbackUrl="{callback}" languageCode="it-IT" '
        'track="both_tracks" inboundTrackLabel="cliente" outboundTrackLabel="ristorante" '
        'partialResults="false" hints="prenotazione,tavolo,persone,coperti,oggi,domani,'
        'lunedi,martedi,mercoledi,giovedi,venerdi,sabato,domenica" />'
        "</Start>"
        f'<Dial answerOnBridge="true"{caller_id_attr} action="/dial-status" method="POST" '
        'record="record-from-answer-dual" '
        f'recordingStatusCallback="{recording_callback}" '
        'recordingStatusCallbackEvent="completed">'
        f"<Number>{escape(forward_number)}</Number>"
        "</Dial>"
    )


def incoming_twiml() -> bytes:
    """Return the inbound caller menu TwiML for the Twilio phone number."""
    notice = (
        "La chiamata puo essere trascritta per gestire la prenotazione. "
        "Prema 1 per parlare con il ristorante."
    )
    body = (
        '<Gather input="dtmf" numDigits="1" timeout="8" action="/incoming-choice" method="POST">'
        f'<Say language="it-IT">{escape(notice)}</Say>'
        "</Gather>"
        f'<Say language="it-IT">{escape("Nessuna scelta ricevuta. La metto in contatto con il ristorante.")}</Say>'
        f"{dial_restaurant_twiml()}"
    )
    return twiml(body)


def incoming_choice_twiml(digit: str, attempts: int = 0) -> bytes:
    """Handle the caller's DTMF menu choice and continue the voice flow."""
    if digit == "1":
        return twiml(
            '<Say language="it-IT">La metto in contatto con il ristorante.</Say>'
            f"{dial_restaurant_twiml()}"
        )
    if attempts >= MAX_MENU_ATTEMPTS:
        return twiml('<Say language="it-IT">Scelta non valida. Arrivederci.</Say>')
    return twiml(
        '<Say language="it-IT">Scelta non valida. Prema 1 per parlare con il ristorante.</Say>'
        f'<Redirect method="POST">/incoming?attempts={attempts + 1}</Redirect>'
    )


def handle_transcription(form: dict[str, str]) -> None:
    """Store final Twilio transcription fragments and save complete bookings."""
    event = form.get("TranscriptionEvent")
    call_sid = form.get("CallSid", "unknown")

    if event != "transcription-content" or form.get("Final") != "true":
        append_jsonl(TRANSCRIPTS_FILE, {"kind": "transcription_event", **form})
        return

    try:
        transcription_data = json.loads(form.get("TranscriptionData", "{}"))
    except json.JSONDecodeError:
        transcription_data = {}

    transcript = str(transcription_data.get("transcript", "")).strip()
    if not transcript:
        return

    entry = {
        "track": form.get("Track", ""),
        "text": transcript,
        "timestamp": form.get("Timestamp", ""),
    }
    CALL_TRANSCRIPTS.setdefault(call_sid, []).append(entry)
    append_jsonl(TRANSCRIPTS_FILE, {"call_sid": call_sid, **entry})

    combined_text = " ".join(item["text"] for item in CALL_TRANSCRIPTS[call_sid])
    reservation = parse_reservation(combined_text)
    if reservation.is_complete and call_sid not in SAVED_CALLS:
        save_reservation(
            reservation,
            {
                "call_sid": call_sid,
                "transcript": combined_text,
                "source": "live_forwarded_call",
            },
        )
        SAVED_CALLS.add(call_sid)


def handle_recording(form: dict[str, str]) -> None:
    """Store Twilio recording metadata for later review."""
    append_jsonl(
        TRANSCRIPTS_FILE,
        {
            "kind": "recording",
            "call_sid": form.get("CallSid"),
            "recording_sid": form.get("RecordingSid"),
            "recording_url": form.get("RecordingUrl"),
            "recording_duration": form.get("RecordingDuration"),
            "recording_channels": form.get("RecordingChannels"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def dial_status_twiml(form: dict[str, str]) -> bytes:
    """Record the forwarded call outcome and return any final TwiML."""
    status = form.get("DialCallStatus", "unknown")
    append_jsonl(
        TRANSCRIPTS_FILE,
        {
            "kind": "dial_status",
            "call_sid": form.get("CallSid"),
            "dial_call_sid": form.get("DialCallSid"),
            "dial_call_status": status,
            "dial_call_duration": form.get("DialCallDuration"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    if status == "completed":
        return twiml("")
    return twiml(
        '<Say language="it-IT">Non riesco a collegare il ristorante in questo momento. Arrivederci.</Say>'
    )


def reservation_twiml(speech_text: str) -> bytes:
    """Confirm or retry an outbound speech reservation request."""
    reservation = parse_reservation(speech_text)
    save_reservation(reservation)

    if reservation.is_complete:
        message = (
            f"Perfetto, ho salvato un tavolo per {reservation.people} persone "
            f"il {reservation.day} alle {reservation.time}. Arrivederci."
        )
        return twiml(f'<Say language="it-IT">{escape(message)}</Say><Hangup/>')

    missing = []
    if reservation.people is None:
        missing.append("numero di persone")
    if reservation.day is None:
        missing.append("giorno")
    if reservation.time is None:
        missing.append("orario")

    message = "Mi manca " + ", ".join(missing) + ". Puo ripetere la prenotazione?"
    retry = (
        '<Gather input="speech" language="it-IT" speechTimeout="auto" timeout="15" '
        'action="/reservation" method="POST">'
        f'<Say language="it-IT">{escape(message)}</Say>'
        "</Gather>"
        '<Say language="it-IT">Non riesco a completare la prenotazione. Arrivederci.</Say>'
    )
    return twiml(retry)


def make_outbound_call(target_number: str) -> dict[str, object]:
    """Create an outbound Twilio call that uses the /voice webhook."""
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = normalize_phone_number(os.environ["TWILIO_FROM_NUMBER"])

    data = urllib.parse.urlencode(
        {
            "To": target_number,
            "From": from_number,
            "Url": public_url("/voice"),
            "Method": "POST",
        }
    ).encode()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    request = urllib.request.Request(url, data=data, method="POST")
    token = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def parse_form(body: bytes) -> dict[str, str]:
    """Parse a Twilio form-encoded webhook body into a plain dictionary."""
    parsed = urllib.parse.parse_qs(body.decode(), keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


class Handler(BaseHTTPRequestHandler):
    """HTTP request handler for local status pages and Twilio webhooks."""

    def do_GET(self) -> None:
        """Serve the local health page used during manual setup checks."""
        if self.path == "/":
            self.respond_text(
                "Restaurant call app is running.\n"
                "Configure your Twilio phone number voice webhook to POST /incoming.\n"
                "Optional: POST /call with target_number=+15551234567 to start a test call.\n"
            )
            return
        self.respond_text("Not found\n", status=404)

    def do_POST(self) -> None:
        """Route Twilio webhook POST requests to the matching flow handler."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_form(self.rfile.read(length))

        if path == "/call":
            self.handle_call(form)
        elif path == "/voice":
            self.respond_xml(voice_twiml())
        elif path == "/incoming":
            self.respond_xml(incoming_twiml())
        elif path == "/incoming-choice":
            attempts = int(query.get("attempts", ["0"])[0])
            self.respond_xml(incoming_choice_twiml(form.get("Digits", ""), attempts))
        elif path == "/transcription":
            handle_transcription(form)
            self.respond_xml(twiml(""))
        elif path == "/recording":
            handle_recording(form)
            self.respond_xml(twiml(""))
        elif path == "/dial-status":
            self.respond_xml(dial_status_twiml(form))
        elif path == "/reservation":
            self.respond_xml(reservation_twiml(form.get("SpeechResult", "")))
        else:
            self.respond_text("Not found\n", status=404)

    def handle_call(self, form: dict[str, str]) -> None:
        """Handle the local API endpoint that starts an outbound test call."""
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
        """Send a TwiML/XML response."""
        self.send_response(status)
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, value: dict[str, object], status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_text(self, value: str, status: int = 200) -> None:
        """Send a plain text response."""
        body = value.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Start the local Twilio webhook server."""
    load_dotenv()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Listening on http://{HOST}:{PORT}")
    print("Set the Twilio phone number Voice webhook to PUBLIC_BASE_URL/incoming.")
    server.serve_forever()


if __name__ == "__main__":
    main()
