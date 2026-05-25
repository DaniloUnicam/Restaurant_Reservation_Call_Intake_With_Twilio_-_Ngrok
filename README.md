Restaurant Reservation Call Intake
==================================

Small Python app for restaurant phone-call intake. It reads a caller's request
from typed transcript text and extracts:

- number of people
- reservation day/date
- reservation time

Run:

```powershell
uv run python main.py
```

Example input:

```text
I need a table for four tomorrow at 7:30 pm
```

Run tests:

```powershell
uv run python -m unittest
```

Incoming Phone Calls
====================

For the real restaurant flow, customers call your Twilio restaurant number.
Twilio starts live transcription, forwards the call to the real restaurant
phone, extracts reservation details from the conversation, and saves them to
`reservations.jsonl`. Raw transcript events and recording links are saved to
`transcripts.jsonl`.

Create a `.env` file:

```env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+15551234567
RESTAURANT_FORWARD_NUMBER=+390123456789
PUBLIC_BASE_URL=https://your-public-tunnel.example
```

Run the webhook server:

```powershell
uv run python call_app.py
```

Expose `http://127.0.0.1:8000` with a public HTTPS tunnel such as ngrok or
cloudflared. In the Twilio console, set your Twilio phone number's Voice webhook
to:

```text
https://your-public-tunnel.example/incoming
```

Now call the Twilio number from a phone. Twilio will forward the call to
`RESTAURANT_FORWARD_NUMBER` and transcribe both call legs.

Example conversation:

```text
Ciao, vorrei prenotare un tavolo per 4 persone alle 8:30 di lunedi 25 maggio
```

Optional outbound test call:

```powershell
curl -X POST http://127.0.0.1:8000/call -d "target_number=+15557654321"
```
