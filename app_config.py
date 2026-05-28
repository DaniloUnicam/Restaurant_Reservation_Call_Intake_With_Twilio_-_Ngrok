from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


SUPABASE_PLACEHOLDER_URL = "https://your-project.supabase.co"
TWILIO_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
JSON_CONTENT_TYPE = "application/json"
XML_CONTENT_TYPE = "text/xml"
TEXT_CONTENT_TYPE = "text/plain"
GATHER_INPUT = "dtmf speech"
DEFAULT_GENAI_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
TRUE_VALUES = {"1", "true", "yes"}


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


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


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in TRUE_VALUES


def public_url(path: str) -> str:
    """Build an absolute callback URL from PUBLIC_BASE_URL and a path."""
    base_url = os.environ["PUBLIC_BASE_URL"].rstrip("/")
    return f"{base_url}{path}"


def normalize_phone_number(value: str) -> str:
    """Remove whitespace from a phone number before passing it to Twilio."""
    return "".join(value.split())


load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
GENAI_MODEL = os.getenv("GENAI_MODEL", DEFAULT_GENAI_MODEL)
ENABLE_LIVE_TRANSCRIPTION = env_bool("ENABLE_LIVE_TRANSCRIPTION")
