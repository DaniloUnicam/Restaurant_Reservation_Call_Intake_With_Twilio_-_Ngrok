Restaurant Table Reserver
=========================

Applicazione Python per raccogliere prenotazioni di un ristorante da testo o
chiamate VoIP. Il sistema parla in italiano, estrae numero di persone, giorno e
orario, salva le prenotazioni localmente e, se configurato, le sincronizza su
Supabase. Il progetto puo essere eseguito in locale oppure pubblicato su
Hostingguru.

Funzionalita
============

- Parsing di prenotazioni in italiano e inglese.
- Assistente vocale in italiano per chiamate VoIP/Twilio.
- Domande di follow-up se mancano persone, giorno o orario.
- Estrazione avanzata con Google Gemini, con fallback al parser locale.
- Salvataggio su `reservations.jsonl`.
- Salvataggio opzionale su database Supabase via REST API.
- Storico trascrizioni, tentativi vocali, registrazioni e stato chiamata in
  `transcripts.jsonl`.
- Endpoint `/reservations` per leggere le prenotazioni salvate.
- Supporto a deploy pubblico su Hostingguru.

Struttura
=========

- `call_app.py`: server HTTP e routing dei webhook VoIP/Twilio.
- `app_config.py`: configurazione, lettura `.env` e costanti condivise.
- `reservation_parser.py`: parser deterministico locale.
- `storage.py`: salvataggio JSONL e integrazione Supabase.
- `reservation_ai.py`: estrazione prenotazione con Gemini e fallback locale.
- `voice_flow.py`: TwiML, flusso vocale, trascrizioni e conferme.
- `twilio_client.py`: avvio chiamate outbound tramite API Twilio.
- `test_main.py`: test del parser.
- `test_call_app.py`: test del flusso voce, TwiML e trascrizioni.
- `.env`: configurazione locale, da non committare.

Requisiti
=========

- Python 3.10 o superiore.
- `uv` per installare ed eseguire il progetto.
- Account Twilio o provider VoIP compatibile con webhook HTTP/TwiML.
- Progetto Supabase con tabella `reservations`, se si vuole il salvataggio su
  database.
- Hostingguru, oppure un tunnel HTTPS come ngrok/cloudflared per test locali.

Configurazione
==============

Creare un file `.env` nella root:

```env
HOST=127.0.0.1
PORT=8000
PUBLIC_BASE_URL=https://tuo-dominio.it

TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+15551234567

GEMINI_API_KEY=...
GENAI_MODEL=gemini-2.5-flash-native-audio-preview-12-2025

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=...

RESERVATIONS_FILE=reservations.jsonl
TRANSCRIPTS_FILE=transcripts.jsonl

RESTAURANT_FORWARD_NUMBER=+390000000000
ENABLE_LIVE_TRANSCRIPTION=false
```

Variabili principali:

- `PUBLIC_BASE_URL`: URL pubblico del server, ad esempio il dominio su
  Hostingguru, senza slash finale.
- `TWILIO_*`: credenziali e numero VoIP/Twilio usati per ricevere o avviare
  chiamate.
- `GEMINI_API_KEY`: chiave Google GenAI. Se manca, resta attivo il parser
  locale.
- `SUPABASE_URL`: URL del progetto Supabase.
- `SUPABASE_SERVICE_KEY`: service key Supabase usata dal backend.
- `RESTAURANT_FORWARD_NUMBER`: numero reale del ristorante per eventuale
  inoltro chiamata.
- `ENABLE_LIVE_TRANSCRIPTION`: abilita la trascrizione live delle chiamate
  inoltrate quando supportata.

Database Supabase
=================

Il backend scrive nella tabella `reservations` tramite REST API. La tabella deve
accettare almeno i campi generati dal payload:

```json
{
  "people": 4,
  "day": "2026-05-27",
  "time": "20:30",
  "is_complete": true,
  "original_text": "...",
  "created_at": "...",
  "call_sid": "...",
  "transcript": "...",
  "source": "voice_agent",
  "parser": "google_genai"
}
```

Se Supabase non e configurato o non risponde, l'app continua a salvare in
`reservations.jsonl`.

Esecuzione Locale
=================

Installare/eseguire con `uv`:

```powershell
uv run python call_app.py
```

Esempio:

```text
Ciao, vorrei prenotare un tavolo per 4 persone alle 20:30 di lunedi 25 maggio
```

Flusso VoIP
===========

Configurare il numero VoIP/Twilio in modo che il webhook voce punti a:

```text
POST https://tuo-dominio.it/incoming
```

Flusso della chiamata:

1. Il cliente chiama il numero VoIP.
2. Il provider invia la chiamata a `/incoming`.
3. L'app chiede in italiano numero di persone, giorno e orario.
4. Il risultato vocale arriva a `/reservation`.
5. L'app estrae i dati con Gemini o parser locale.
6. Se la prenotazione e completa, viene salvata su JSONL e Supabase.
7. Se manca qualcosa, l'app fa una nuova domanda solo sui dati mancanti.

Endpoint utili
==============

- `GET /`: health check.
- `POST /incoming`: webhook chiamate in ingresso.
- `POST /reservation`: ricezione trascrizione vocale.
- `POST /call`: avvia una chiamata outbound di test.
- `GET /reservations`: lista prenotazioni, da Supabase se disponibile,
  altrimenti dal file locale.
- `POST /transcription`: callback trascrizione live.
- `POST /recording`: callback registrazione.
- `POST /dial-status`: esito inoltro chiamata.

Hosting su Hostingguru
======================

Su Hostingguru pubblicare il progetto come applicazione Python esposta via HTTPS.
Il comando di avvio deve eseguire:

```powershell
uv run python call_app.py
```

Impostare nelle variabili ambiente del pannello Hostingguru gli stessi valori
del file `.env`, in particolare:

- `PUBLIC_BASE_URL` con il dominio pubblico Hostingguru.
- credenziali `TWILIO_*`.
- credenziali `SUPABASE_*`.
- eventuale `GEMINI_API_KEY`.

Dopo il deploy, configurare il provider VoIP/Twilio con:

```text
https://tuo-dominio.it/incoming
```

Chiamata outbound di test
=========================

```powershell
curl -X POST https://tuo-dominio.it/call -d "target_number=+390000000000"
```

In locale:

```powershell
curl -X POST http://127.0.0.1:8000/call -d "target_number=+390000000000"
```

Test
====

```powershell
uv run python -m unittest
```

Sicurezza
=========

Non committare `.env`, credenziali Twilio, chiavi Supabase, trascrizioni,
registrazioni o file di runtime. Usare la service key Supabase solo lato server.
