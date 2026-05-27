Restaurant Reservation Call Intake
==================================

A small Python project for collecting restaurant reservation details from text
or phone calls. The app uses deterministic local parsing rules, so it works
without any AI SDK or external language-model API.

Features
========

- Extracts reservation details from English and Italian text.
- Works offline for parsing and tests.
- Detects party size, reservation day/date, and reservation time.
- Supports terminal-based intake for local testing.
- Supports Twilio inbound calls with an Italian speech-based reservation agent.
- Collects missing reservation fields with follow-up voice prompts.
- Saves completed reservations to `reservations.jsonl`.
- Saves speech attempts and transcript events to `transcripts.jsonl`.

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
PUBLIC_BASE_URL=https://your-public-tunnel.example
GEMINI_API_KEY=your-google-genai-key
HOST=127.0.0.1
PORT=8000
```

Variable reference:

- `TWILIO_ACCOUNT_SID`: Twilio account SID used for outbound test calls.
- `TWILIO_AUTH_TOKEN`: Twilio auth token used for outbound test calls.
- `TWILIO_FROM_NUMBER`: your Twilio phone number in E.164 format.
- `PUBLIC_BASE_URL`: public HTTPS base URL that points to this local server.
- `GEMINI_API_KEY`: optional Google GenAI API key for flexible reservation
  extraction. `GOOGLE_API_KEY` also works.
- `GENAI_MODEL`: optional Gemini model name. Defaults to `gemini-2.5-flash`.
- `HOST`: local bind host. Defaults to `127.0.0.1`.
- `PORT`: local port. Defaults to `8000`.
- `RESERVATIONS_FILE`: optional output path for parsed reservations.
- `TRANSCRIPTS_FILE`: optional output path for transcript events.

Terminal Intake
===============

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
2. The app asks in Italian for number of people, day, and time.
3. Twilio posts the recognized speech to `/reservation`.
4. The app extracts structured fields with Google GenAI when configured,
   falling back to the local parser if the API key is missing or the model
   fails.
5. The app saves complete reservations to
   `reservations.jsonl`.
6. If one or more fields are missing, the app asks only for the missing details.

Example saved reservation:

```json
{"people": 4, "day": "2026-05-27", "time": "20:30", "is_complete": true}
```

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
- `transcripts.jsonl`: speech attempts and raw transcription events.
- `debug.log`: local debug output, if generated.

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
- If ngrok shows `ERR_NGROK_3200`, the endpoint is offline and Twilio cannot
  reach your app.

Security Notes
==============

Never commit `.env`, Twilio credentials, transcripts, recordings, or local tool
settings. The repository ignores these files by default.
