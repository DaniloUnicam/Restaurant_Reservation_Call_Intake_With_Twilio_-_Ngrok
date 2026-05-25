from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "un": 1,
    "uno": 1,
    "una": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
    "dieci": 10,
    "undici": 11,
    "dodici": 12,
    "tredici": 13,
    "quattordici": 14,
    "quindici": 15,
    "sedici": 16,
    "diciassette": 17,
    "diciotto": 18,
    "diciannove": 19,
    "venti": 20,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "lunedi": 0,
    "martedi": 1,
    "mercoledi": 2,
    "giovedi": 3,
    "venerdi": 4,
    "sabato": 5,
    "domenica": 6,
}

MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}


@dataclass(frozen=True)
class ReservationRequest:
    """Parsed reservation fields plus the original user text."""

    people: int | None
    day: str | None
    time: str | None
    original_text: str

    @property
    def is_complete(self) -> bool:
        """Return true when every required reservation field is present."""
        return self.people is not None and self.day is not None and self.time is not None


def parse_reservation(text: str, today: date | None = None) -> ReservationRequest:
    """Parse free-form reservation text with deterministic local rules."""
    today = today or date.today()
    normalized = normalize_text(text)

    return ReservationRequest(
        people=find_people(normalized),
        day=find_day(normalized, today),
        time=find_time(normalized),
        original_text=text,
    )


def find_people(text: str) -> int | None:
    """Find a party size expressed as digits or supported number words."""
    patterns = [
        r"\b(?:for|party of|table for|reservation for)\s+(\d{1,2}|[a-z]+)\b",
        r"\b(\d{1,2}|[a-z]+)\s+(?:people|persons|guests|diners)\b",
        r"\b(?:per|siamo in|tavolo per|prenotare per|prenotazione per)\s+(\d{1,2}|[a-z]+)\b",
        r"\b(\d{1,2}|[a-z]+)\s+(?:persone|clienti|ospiti|coperti)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return parse_number(match.group(1))
    return None


def parse_number(value: str) -> int | None:
    """Convert a positive digit string or known number word into an integer."""
    if value.isdigit():
        number = int(value)
        return number if number > 0 else None
    return NUMBER_WORDS.get(value)


def normalize_text(text: str) -> str:
    """Lowercase text, remove accents, and collapse repeated whitespace."""
    text = text.lower().replace("è", "e")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(text.strip().split())


def find_day(text: str, today: date) -> str | None:
    """Find a reservation day and return it as an ISO date string."""
    if "today" in text:
        return today.isoformat()
    if "tomorrow" in text or "domani" in text:
        return (today + timedelta(days=1)).isoformat()
    if "oggi" in text:
        return today.isoformat()

    italian_date_match = re.search(
        r"\b(\d{1,2})\s+(?:di\s+)?("
        + "|".join(MONTHS)
        + r")(?:\s+(\d{4}))?\b",
        text,
    )
    if italian_date_match:
        day_number = int(italian_date_match.group(1))
        month = MONTHS[italian_date_match.group(2)]
        year = int(italian_date_match.group(3) or today.year)
        try:
            return date(year, month, day_number).isoformat()
        except ValueError:
            return None

    date_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
    if date_match:
        first = int(date_match.group(1))
        second = int(date_match.group(2))
        year = int(date_match.group(3) or today.year)
        if year < 100:
            year += 2000

        # Accept common US month/day phrasing first, then day/month.
        for month, day_number in ((first, second), (second, first)):
            try:
                return date(year, month, day_number).isoformat()
            except ValueError:
                pass

    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b(?:next\s+|prossimo\s+|prossima\s+)?{name}\b", text):
            return next_weekday(today, weekday).isoformat()

    return None


def next_weekday(today: date, weekday: int) -> date:
    """Return the next future date for the requested weekday."""
    days_ahead = (weekday - today.weekday()) % 7
    return today + timedelta(days=days_ahead or 7)


def find_time(text: str) -> str | None:
    """Find a reservation time and return it as HH:MM in 24-hour format."""
    text = text.replace(".", ":")
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3)
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    match = re.search(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"

    match = re.search(r"\b(?:alle|ore|per le|verso le)\s+(\d{1,2})(?:\s+e\s+(\d{1,2}))?\b", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    return None


def prompt_for_missing(reservation: ReservationRequest) -> ReservationRequest:
    """Ask for missing reservation fields in the terminal."""
    people = reservation.people
    day = reservation.day
    time = reservation.time

    if people is None:
        people = parse_number(input("How many people? ").strip().lower())
    if day is None:
        day = find_day(input("Which day? "), date.today())
    if time is None:
        time = find_time(input("What time? "))

    return ReservationRequest(people, day, time, reservation.original_text)


def main() -> None:
    """Run the command-line reservation intake demo."""
    print("Restaurant reservation call intake")
    print("Type the caller's request, for example: 'A table for four tomorrow at 7:30 pm'.")
    transcript = input("> ")

    reservation = prompt_for_missing(parse_reservation(transcript))

    print("\nReservation request")
    print(f"People: {reservation.people or 'unknown'}")
    print(f"Day:    {reservation.day or 'unknown'}")
    print(f"Time:   {reservation.time or 'unknown'}")
    print(f"Status: {'complete' if reservation.is_complete else 'needs follow-up'}")


if __name__ == "__main__":
    main()
