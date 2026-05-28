from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request

from app_config import TWILIO_FORM_CONTENT_TYPE, normalize_phone_number, public_url


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
    request = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json",
        data=data,
        method="POST",
    )
    token = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", TWILIO_FORM_CONTENT_TYPE)

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())
