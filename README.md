# Voice Agent: Phone Number Collection

A voice agent built on **LiveKit Agents** that collects a **10-digit Indian mobile number** through natural conversation. It handles:

- English, Hindi and Hinglish ("nine aath saat 6 5 chaar…")
- any grouping: single digits, pairs, triples, 5 + 5, or all at once
- "double seven", "triple nine", "oh", "shunya", "sifar"
- pauses of up to 4 seconds mid-number, without interrupting
- self-corrections ("nine eight seven — wait, sorry — nine eight six…")
- noisy audio: noise suppression, plus re-asking for any segment with low SNR or low confidence

The number parsing is **deterministic, with no LLM**. Every number is read back digit by digit, and only confirmed, valid numbers are saved.

## Demo video

[![Watch the demo on Vimeo](https://i.vimeocdn.com/video/2209779797-d5bceee7f9f30d868ac25e503614487127b9871d7a255f904a7b149afcc3c437-d_1280?region=us)](https://vimeo.com/1233953389)

▶️ **[Watch the demo on Vimeo](https://vimeo.com/1233953389)**

## Repository layout

```
voice-phone-agent/
├── backend/                 Python (uv): FastAPI + LiveKit agent
│   ├── src/phone_agent/
│   │   ├── parsing/         parse_phone_number(): spoken text → 10 digits
│   │   ├── dialog/          conversation state machine + prompts
│   │   ├── agent/           LiveKit worker, SNR meter, TTS cache
│   │   ├── api/             REST API + SQLite
│   │   └── config.py        settings from .env
│   ├── tests/               100 tests (parser, dialog, API)
│   ├── .env.example
│   └── README.md            backend details: parser, noise handling, API, env vars
└── frontend/                plain HTML / CSS / JS, no build step
    ├── index.html           call panel + dashboard
    ├── app.js               LiveKit client + dashboard logic
    ├── style.css
    ├── config.js            backend URL (empty = same origin)
    └── README.md
```

## Stack

| Part | Choice |
|---|---|
| Voice framework | LiveKit Agents 1.8 |
| Speech-to-text | Deepgram Nova-3 `multi` (Hindi + English, streaming). Groq Whisper is optional. |
| Text-to-speech | Deepgram Aura-2. Groq Orpheus is optional. |
| Noise suppression | LiveKit BVC (Krisp), plus an SNR gate and an STT-confidence gate |
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend | HTML/JS with `livekit-client` |
| Package manager | uv |

## Quick start

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), a [LiveKit Cloud](https://cloud.livekit.io) project and a [Deepgram](https://console.deepgram.com) API key.

```bash
cd backend
uv sync
cp .env.example .env              # fill in LIVEKIT_* and DEEPGRAM_API_KEY
uv run phone-agent download-files # one-time model download
```

Then use two terminals, both in `backend/`:

```bash
uv run phone-api          # API + frontend on http://127.0.0.1:8000
```

```bash
uv run phone-agent dev    # voice agent worker
```

Open **http://127.0.0.1:8000** and press **Start call**. Collected numbers appear in the dashboard on the same page.

To run the tests:

```bash
cd backend && uv run pytest
```

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/phone` | Save a validated number |
| `GET` | `/api/phone` | List numbers. Filters: `search`, `language`, `from`, `to` |
| `DELETE` | `/api/phone/{id}` | Delete a record |
| `GET` | `/api/phone/stats` | Total and per-language counts |
| `GET` | `/api/token` | LiveKit token for the browser call |

Interactive docs are at http://127.0.0.1:8000/docs. See [backend/README.md](backend/README.md) for the full details.
