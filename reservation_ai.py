from __future__ import annotations

import json
import os
import re
from datetime import date

from app_config import GENAI_MODEL
from reservation_parser import ReservationRequest, parse_reservation


def parse_reservation_smart(text: str) -> tuple[ReservationRequest, str, str | None]:
    """Use Gemini for flexible extraction, falling back to local parsing."""
    local = parse_reservation(text)
    llm_reservation, error = parse_reservation_with_genai(text)
    if llm_reservation is None:
        return local, "local", error

    # Keep local values as a safety net when Gemini returns null for a field.
    return (
        ReservationRequest(
            llm_reservation.people if llm_reservation.people is not None else local.people,
            llm_reservation.day if llm_reservation.day is not None else local.day,
            llm_reservation.time if llm_reservation.time is not None else local.time,
            text,
        ),
        "google_genai",
        None,
    )


def parse_reservation_with_genai(text: str) -> tuple[ReservationRequest | None, str | None]:
    """Ask Google GenAI to extract reservation fields as JSON."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None, None

    try:
        from google import genai
    except ImportError:
        return None, "google-genai package is not installed"

    prompt = (
        "Estrai i dati di una prenotazione ristorante da questa trascrizione italiana.\n"
        f"Data di oggi: {date.today().isoformat()}.\n"
        "Rispondi solo con JSON valido con chiavi: people, day, time.\n"
        "people deve essere un intero o null. day deve essere YYYY-MM-DD o null. "
        "time deve essere HH:MM in formato 24 ore o null.\n"
        f"Trascrizione: {text}"
    )
    schema = {
        "type": "object",
        "properties": {
            "people": {"type": ["integer", "null"]},
            "day": {"type": ["string", "null"]},
            "time": {"type": ["string", "null"]},
        },
        "required": ["people", "day", "time"],
    }

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GENAI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "response_json_schema": schema},
        )
        payload = json.loads(extract_json_object(response.text or "{}"))
        return reservation_from_payload(payload, text), None
    except Exception as error:
        return None, str(error)


def extract_json_object(text: str) -> str:
    """Return the first JSON object from a model response."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    return match.group(0) if match else stripped


def reservation_from_payload(payload: dict[str, object], original_text: str) -> ReservationRequest:
    """Validate and normalize reservation JSON from GenAI."""
    people = payload.get("people")
    day = payload.get("day")
    time_value = payload.get("time")

    people = people if isinstance(people, int) and people > 0 else None
    day = day if isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) else None
    time_value = (
        time_value
        if isinstance(time_value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value)
        else None
    )
    return ReservationRequest(people, day, time_value, original_text)
