Restaurant Reservation Call Intake
==================================

A small Python project for collecting restaurant reservation details from text
or phone calls. The app uses the Anthropic Claude SDK to extract structured
reservation fields when `ANTHROPIC_API_KEY` is configured, then falls back to a
deterministic local parser when Claude is unavailable.

Features
========

- Extracts reservation details from English and Italian text with Claude.
- Falls back to local parsing rules for offline use and tests.
- Detects party size, reservation day/date, and reservation time.
- Supports terminal-based intake for local testing.
- Supports Twilio inbound calls with a DTMF menu.
- Forwards callers to a configured restaurant number.
- Starts Twilio live transcription and records call metadata.
- Saves completed reservations to `reservations.jsonl`.
- Saves transcription and recording events to `transcripts.jsonl`.

Project Structure
=================

- `main.py`: core reservation parser and terminal intake flow.
- `call_app.py`: HTTP webhook server for Twilio voice calls.
- `test_main.py`: parser tests.
- `test_call_app.py`: Twilio/TwiML and transcription tests.
- `.env`: local configuration file. This file must not be committed.

Requirements
============

- Python 3.14 or newer, as declared in `pyproject.toml`.
- `uv` for running the project commands.
- A Twilio account with a voice-capable phone number.
- A public HTTPS tunnel, such as ngrok or cloudflared, for local webhook testing.

Environment Variables
=====================

Create a `.env` file in the project root:

```env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+15551234567
RESTAURANT_FORWARD_NUMBER=+390123456789
PUBLIC_BASE_URL=https://your-public-tunnel.example
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-5-20250929
CLAUDE_FALLBACK_TO_REGEX=true
HOST=127.0.0.1
PORT=8000
```

Variable reference:

- `TWILIO_ACCOUNT_SID`: Twilio account SID used for outbound test calls.
- `TWILIO_AUTH_TOKEN`: Twilio auth token used for outbound test calls.
- `TWILIO_FROM_NUMBER`: your Twilio phone number in E.164 format.
- `RESTAURANT_FORWARD_NUMBER`: phone number that receives forwarded calls.
- `PUBLIC_BASE_URL`: public HTTPS base URL that points to this local server.
- `ANTHROPIC_API_KEY`: enables reservation parsing through the Claude SDK.
- `CLAUDE_MODEL`: optional Claude model override.
- `CLAUDE_FALLBACK_TO_REGEX`: set to `false` to fail instead of using local
  parsing when the Claude request fails.
- `HOST`: local bind host. Defaults to `127.0.0.1`.
- `PORT`: local port. Defaults to `8000`.
- `RESERVATIONS_FILE`: optional output path for parsed reservations.
- `TRANSCRIPTS_FILE`: optional output path for transcript events.

Terminal Intake
===============

When `ANTHROPIC_API_KEY` is present, terminal intake uses Claude to extract the
reservation. Without it, the local parser handles supported examples.

Run the parser in terminal mode:

```powershell
uv run python main.py
```

Example input:

```text
I need a table for four tomorrow at 7:30 pm
```

Example Italian input:

```text
Ciao, vorrei prenotare un tavolo per 4 persone alle 8:30 di lunedi 25 maggio
```

Twilio Inbound Call Flow
========================

Start the webhook server:

```powershell
uv run python call_app.py
```

Expose the local server through a public HTTPS tunnel. For ngrok:

```powershell
ngrok http 8000
```

Set `PUBLIC_BASE_URL` in `.env` to the HTTPS tunnel URL, without a trailing
slash:

```env
PUBLIC_BASE_URL=https://your-ngrok-domain.ngrok-free.dev
```

In the Twilio Console, configure your Twilio phone number Voice webhook:

```text
URL:    https://your-ngrok-domain.ngrok-free.dev/incoming
Method: HTTP POST
```

When a customer calls the Twilio number:

1. Twilio requests `/incoming`.
2. The app plays an Italian notice and asks the caller to press `1`.
3. If the caller presses `1`, Twilio requests `/incoming-choice`.
4. The app starts live transcription and dials `RESTAURANT_FORWARD_NUMBER`.
5. Completed transcription fragments are posted to `/transcription`.
6. Recording metadata is posted to `/recording`.
7. Dial completion status is posted to `/dial-status`.

The transcription handler combines final transcript fragments and sends the text
through `parse_reservation`. With `ANTHROPIC_API_KEY` set, that means Claude is
used for the extraction step.

If the caller does not press a key, the app automatically forwards the call
after the menu timeout.

Outbound Test Call
==================

You can also ask Twilio to call a target number and collect reservation details
with speech input:

```powershell
curl -X POST http://127.0.0.1:8000/call -d "target_number=+15557654321"
```

The outbound call uses the `/voice` webhook and then posts speech recognition
results to `/reservation`.

Data Files
==========

Runtime files are local and ignored by Git:

- `reservations.jsonl`: saved reservation payloads.
- `transcripts.jsonl`: raw transcription, recording, and dial status events.
- `debug.log`: local debug output, if generated.
- `.claude/`: local assistant/tooling configuration.

Testing
=======

Run the full test suite:

```powershell
uv run python -m unittest
```

Troubleshooting
===============

If the Twilio call ends immediately after the first message, check these points:

- The webhook URL in Twilio must be the current public tunnel URL plus
  `/incoming`.
- The Twilio webhook method must be `HTTP POST`.
- The local server must be running with `uv run python call_app.py`.
- The tunnel must be online and forwarding to `http://127.0.0.1:8000`.
- `PUBLIC_BASE_URL` must match the active tunnel URL.
- `RESTAURANT_FORWARD_NUMBER` must be set in E.164 format, for example
  `+390123456789`.
- If ngrok shows `ERR_NGROK_3200`, the endpoint is offline and Twilio cannot
  reach your app.

Security Notes
==============

Never commit `.env`, Twilio credentials, API keys, transcripts, recordings, or
local assistant settings. The repository ignores these files by default.
