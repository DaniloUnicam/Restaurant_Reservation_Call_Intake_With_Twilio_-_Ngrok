from __future__ import annotations

import json
import os
import urllib.parse
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import storage
from app_config import ENABLE_LIVE_TRANSCRIPTION, GATHER_INPUT, normalize_phone_number, public_url
from reservation_ai import parse_reservation_smart


CALL_TRANSCRIPTS: dict[str, list[dict[str, str]]] = {}
SAVED_CALLS: set[str] = set()


def twiml(body: str) -> bytes:
    """Wrap a TwiML body in a Response document encoded for HTTP."""
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'.encode()


def voice_twiml() -> bytes:
    """Return TwiML for the outbound speech-based reservation test call."""
    return reservation_prompt_twiml()


def incoming_twiml(_caller_number: str = "") -> bytes:
    """Return the inbound voice-agent TwiML for the Twilio phone number."""
    return reservation_prompt_twiml()


def incoming_choice_twiml(_digit: str, _attempts: int = 0) -> bytes:
    """Handle the caller's DTMF menu choice and continue the voice flow."""
    return reservation_prompt_twiml()


def reservation_prompt_twiml(message: str | None = None, context: str = "") -> bytes:
    """Ask the caller for reservation details with speech recognition."""
    prompt = message or (
        "Salve, benvenuto. Per prenotare un tavolo dica il numero di persone, "
        "il giorno e l'orario della prenotazione."
    )
    action = "/reservation"
    if context:
        action += "?" + urllib.parse.urlencode({"context": context})
    gather = (
        f'<Gather input="{GATHER_INPUT}" language="it-IT" speechTimeout="auto" timeout="12" '
        f'action="{escape(action)}" method="POST">'
        f'<Say language="it-IT">{escape(prompt)}</Say>'
        "</Gather>"
        '<Say language="it-IT">Non ho sentito la risposta. La prego di richiamare. Arrivederci.</Say>'
    )
    return twiml(gather)


def dial_restaurant_twiml() -> str:
    """Return TwiML that starts transcription and dials the restaurant."""
    forward_number = os.getenv("RESTAURANT_FORWARD_NUMBER")
    if not forward_number:
        return '<Say language="it-IT">Numero del ristorante non configurato. Arrivederci.</Say>'

    callback = escape(public_url("/transcription"))
    recording_callback = escape(public_url("/recording"))
    caller_id = escape(normalize_phone_number(os.getenv("TWILIO_FROM_NUMBER", "")))
    caller_id_attr = f' callerId="{caller_id}"' if caller_id else ""
    transcription = ""
    if ENABLE_LIVE_TRANSCRIPTION:
        transcription = (
            "<Start>"
            f'<Transcription statusCallbackUrl="{callback}" languageCode="it-IT" '
            'track="both_tracks" partialResults="false" />'
            "</Start>"
        )
    return (
        transcription +
        f'<Dial answerOnBridge="true"{caller_id_attr} action="/dial-status" method="POST" '
        'record="record-from-answer-dual" '
        f'recordingStatusCallback="{recording_callback}" '
        'recordingStatusCallbackEvent="completed">'
        f"<Number>{escape(normalize_phone_number(forward_number))}</Number>"
        "</Dial>"
    )


def reservation_twiml(
    speech_text: str,
    previous_text: str = "",
    call_sid: str = "",
    source: str = "voice_agent",
) -> bytes:
    """Confirm or retry a speech reservation request."""
    combined_text = " ".join(part for part in (previous_text, speech_text) if part).strip()
    reservation, parser, parser_error = parse_reservation_smart(combined_text)
    storage.append_jsonl(
        storage.TRANSCRIPTS_FILE,
        {
            "kind": "speech_attempt",
            "call_sid": call_sid,
            "text": speech_text,
            "combined_text": combined_text,
            "parser": parser,
            "parser_error": parser_error,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    if reservation.is_complete:
        storage.save_reservation(
            reservation,
            {
                "call_sid": call_sid,
                "transcript": combined_text,
                "source": source,
                "parser": parser,
            },
        )
        message = (
            f"Perfetto, ho salvato un tavolo per {reservation.people} persone "
            f"il {reservation.day} alle {reservation.time}. Arrivederci."
        )
        return twiml(f'<Say language="it-IT">{escape(message)}</Say><Hangup/>')

    missing = missing_fields(reservation)
    return reservation_prompt_twiml("Mi manca " + ", ".join(missing) + ". Puo dirmelo adesso?", combined_text)


def missing_fields(reservation: object) -> list[str]:
    missing = []
    if getattr(reservation, "people", None) is None:
        missing.append("numero di persone")
    if getattr(reservation, "day", None) is None:
        missing.append("giorno")
    if getattr(reservation, "time", None) is None:
        missing.append("orario")
    return missing


def handle_transcription(form: dict[str, str]) -> None:
    """Store final Twilio transcription fragments and save complete bookings."""
    event = form.get("TranscriptionEvent")
    call_sid = form.get("CallSid", "unknown")

    if event != "transcription-content" or form.get("Final") != "true":
        storage.append_jsonl(storage.TRANSCRIPTS_FILE, {"kind": "transcription_event", **form})
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
    storage.append_jsonl(storage.TRANSCRIPTS_FILE, {"call_sid": call_sid, **entry})

    # Live transcription can arrive in fragments, so parse the accumulated text.
    combined_text = " ".join(item["text"] for item in CALL_TRANSCRIPTS[call_sid])
    reservation, parser, parser_error = parse_reservation_smart(combined_text)
    if parser_error:
        storage.append_jsonl(
            storage.TRANSCRIPTS_FILE,
            {"kind": "parser_error", "call_sid": call_sid, "parser": parser, "error": parser_error},
        )
    if reservation.is_complete and call_sid not in SAVED_CALLS:
        storage.save_reservation(
            reservation,
            {
                "call_sid": call_sid,
                "transcript": combined_text,
                "source": "live_forwarded_call",
                "parser": parser,
            },
        )
        SAVED_CALLS.add(call_sid)


def handle_recording(form: dict[str, str]) -> None:
    """Store Twilio recording metadata for later review."""
    storage.append_jsonl(
        storage.TRANSCRIPTS_FILE,
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
    storage.append_jsonl(
        storage.TRANSCRIPTS_FILE,
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
