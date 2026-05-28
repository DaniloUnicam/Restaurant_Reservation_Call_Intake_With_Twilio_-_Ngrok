from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from app_config import JSON_CONTENT_TYPE, SUPABASE_PLACEHOLDER_URL, log
from reservation_parser import ReservationRequest


DATA_FILE = Path(os.getenv("RESERVATIONS_FILE", "reservations.jsonl"))
TRANSCRIPTS_FILE = Path(os.getenv("TRANSCRIPTS_FILE", "transcripts.jsonl"))


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    """Append one dictionary as a JSON line, creating parent folders first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


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
    """Append one parsed reservation to local JSONL + Supabase if configured."""
    payload = reservation_to_dict(reservation)
    if extra:
        payload.update(extra)
    append_jsonl(DATA_FILE, payload)
    save_reservation_to_supabase(payload)


def load_local_reservations() -> list[dict[str, object]]:
    """Load all reservations from the local JSONL file."""
    if not DATA_FILE.exists():
        return []

    results: list[dict[str, object]] = []
    with DATA_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            if line := line.strip():
                results.append(json.loads(line))
    results.reverse()
    return results


def supabase_config() -> tuple[str, str] | None:
    """Return configured Supabase REST credentials, if they are usable."""
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not supabase_key or supabase_url == SUPABASE_PLACEHOLDER_URL:
        return None
    return supabase_url, supabase_key


def supabase_request(method: str, path: str, payload: dict[str, object] | None = None) -> object | None:
    """Call Supabase REST using only the standard library."""
    config = supabase_config()
    if config is None:
        return None

    supabase_url, supabase_key = config
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{supabase_url}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {supabase_key}")
    request.add_header("apikey", supabase_key)
    if payload is not None:
        request.add_header("Content-Type", JSON_CONTENT_TYPE)
        request.add_header("Prefer", "return=minimal")

    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read().decode()
    return json.loads(body) if body else None


def save_reservation_to_supabase(payload: dict[str, object]) -> bool:
    """Save a reservation to Supabase via REST API. Returns True on success."""
    if supabase_config() is None:
        return False

    try:
        supabase_request("POST", "/rest/v1/reservations", payload)
        log(f"Reservation saved to Supabase: {payload.get('people')}p on {payload.get('day')}")
        return True
    except Exception as error:
        log(f"Failed to save to Supabase: {error}")
        return False


def get_reservations_from_supabase() -> list[dict[str, object]]:
    """Fetch all reservations from Supabase via REST API."""
    if supabase_config() is None:
        return []

    try:
        result = supabase_request("GET", "/rest/v1/reservations?order=created_at.desc")
        return result if isinstance(result, list) else []
    except Exception as error:
        log(f"Failed to fetch from Supabase: {error}")
        return []
