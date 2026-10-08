# Backend: voice agent + API

All commands below run from this `backend/` folder. For the overview, see the [root README](../README.md).

This is a LiveKit voice agent that collects a **10-digit Indian mobile number** through natural conversation. It understands English, Hindi and Hinglish, numbers spoken in any grouping, pauses, and self-corrections. Each confirmed number goes to a FastAPI + SQLite backend.

The number parsing is fully deterministic and **no LLM is used anywhere**. The agent's replies come from a small state machine.

```
mic ─► LiveKit BVC noise suppression ─► Silero VAD ─► SNR meter
    ─► Deepgram Nova-3 "multi" (hi + en, streaming)
    ─► PhoneCollector state machine ─► parse_phone_number()
    ─► Deepgram Aura-2 TTS (static prompts cached) ─► speaker
                       │ on "yes"
                       ▼
              FastAPI  POST /api/phone ─► SQLite
```

## Project layout

```
src/phone_agent/
├── parsing/
│   ├── phone_parser.py   # parse_phone_number() / parsePhoneNumber(): the core module
│   └── vocab.py          # English, romanised-Hindi and Devanagari word tables
├── dialog/
│   ├── collector.py      # conversation state machine (no LiveKit dependency)
│   └── prompts.py        # every sentence the agent says, in en + hi
├── agent/
│   ├── worker.py         # LiveKit AgentServer / AgentSession wiring
│   ├── snr.py            # per-turn SNR estimate on the audio fed to STT
│   └── tts_cache.py      # cached synthesis of static prompts
├── api/
│   ├── main.py           # FastAPI app
│   ├── routes.py         # /api/phone CRUD, stats, parse, token
│   ├── schemas.py        # camelCase request/response models + validation
│   └── db.py             # SQLAlchemy model (SQLite)
└── config.py             # settings from .env
tests/                    # parser, dialog and API tests (100 cases)
```

## Setup

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env        # then fill in the keys
uv run phone-agent download-files   # one-time: VAD / noise-cancellation weights
```

### Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LIVEKIT_URL` | ✔ | | LiveKit server URL (`wss://<project>.livekit.cloud`) |
| `LIVEKIT_API_KEY` | ✔ | | LiveKit API key |
| `LIVEKIT_API_SECRET` | ✔ | | LiveKit API secret |
| `DEEPGRAM_API_KEY` | ✔ | | Deepgram STT |
| `AGENT_NAME` | | *(empty)* | Empty means auto-dispatch. Set a name for explicit dispatch. |
| `DEEPGRAM_MODEL` | | `nova-3` | STT model |
| `DEEPGRAM_LANGUAGE` | | `multi` | Multilingual code-switching (Hindi + English) |
| `STT_PROVIDER` | | `deepgram` | `deepgram` (Nova-3 streaming + confidence) or `groq` (Whisper) |
| `TTS_PROVIDER` | | `deepgram` | `deepgram` (Aura-2, same key as STT) or `groq` (Orpheus) |
| `GROQ_API_KEY` | only if a provider is `groq` | | Groq key |
| `GROQ_STT_MODEL` / `GROQ_STT_LANGUAGE` | | `whisper-large-v3-turbo` / *(auto)* | Groq Whisper settings. Leave the language empty for Hinglish. |
| `GROQ_TTS_MODEL` / `GROQ_TTS_VOICE` | | `canopylabs/orpheus-v1-english` / `autumn` | Groq voice. Others: diana, hannah, austin, daniel, troy |
| `DEEPGRAM_TTS_MODEL` | | `aura-2-andromeda-en` | Deepgram voice |
| `TTS_CACHE_DIR` | | `.cache/tts` | Where cached prompt audio is stored |
| `NOISE_CANCELLATION` | | `bvc` | `bvc`, `bvc_telephony`, `nc` or `none` |
| `MIN_SNR_DB` | | `8` | A turn below this SNR is rejected and asked for again |
| `MIN_STT_CONFIDENCE` | | `0.55` | A turn below this STT confidence is rejected and asked for again |
| `PAUSE_TIMEOUT_S` | | `4` | Silence allowed mid-number before the agent prompts |
| `ENDPOINTING_MIN_DELAY_S` | | `0.6` | VAD end-of-speech delay |
| `DATABASE_URL` | | `sqlite:///./data/phone_numbers.db` | SQLAlchemy URL |
| `API_BASE_URL` | | `http://127.0.0.1:8000` | Where the agent POSTs confirmed numbers |
| `API_HOST` / `API_PORT` | | `127.0.0.1` / `8000` | API bind address |
| `FRONTEND_DIR` | | `../frontend` | Folder served at `/`. Nothing is served if it doesn't exist. |

## Running

Use two terminals:

```bash
uv run phone-api          # FastAPI on http://127.0.0.1:8000  (docs at /docs)
```

```bash
uv run phone-agent dev    # registers the agent worker with LIVEKIT_URL
```

Then open **http://127.0.0.1:8000** in a browser. The page has two panels:

- **Talk to the agent:** "Start call" gets a token from `/api/token`, joins a LiveKit room with your mic, and shows live transcripts of both sides. The agent joins automatically and hangs up after saving.
- **Collected numbers (dashboard):** stats (total, English, Hindi, mixed), filters by phone number, language and date range, click a row to see its raw transcript, and Delete (calls `DELETE /api/phone/:id`). It refreshes every 5 s, so a number shows up as soon as the agent saves it.

The frontend lives in [`../frontend`](../frontend). FastAPI serves it at `/`, after the `/api` routes. Other ways to talk to the agent:

- **Terminal:** `uv run phone-agent console` uses your mic and speakers directly.
- **LiveKit Agents Playground:** https://agents-playground.livekit.io

## Backend API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/phone` | Saves a number. Body: `{rawTranscript, parsedNumber, language, collectedAt?}`. Returns **422** unless `parsedNumber` is exactly 10 digits starting with 6–9. |
| `GET` | `/api/phone` | Lists records, newest first. Filters: `search` (digits), `language` (`en`, `hi`, `mixed`), `from` / `to` (ISO datetimes), `limit`. |
| `DELETE` | `/api/phone/{id}` | Deletes a record (204, or 404 if it doesn't exist). |
| `GET` | `/api/phone/stats` | Returns `{total, byLanguage: {en, hi, mixed}}`. |
| `POST` | `/api/parse` | Debug helper: runs the parser on `{transcript}`. |
| `GET` | `/api/token` | Returns a LiveKit participant token for a new room. |
| `GET` | `/api/health` | Liveness check. |

Each record stores `id`, `rawTranscript`, `parsedNumber`, `language` (`en`, `hi` or `mixed`) and `collectedAt` (UTC).

## `parse_phone_number(transcript)`

The parser lives in [`src/phone_agent/parsing/phone_parser.py`](src/phone_agent/parsing/phone_parser.py). It is also exported as `parsePhoneNumber`. It runs six steps in order:

1. **Normalise.** Lower-cases the text, converts Devanagari digits (`९८७`) to ASCII, and strips punctuation and ellipses.
2. **Tokenise.** Splits on whitespace and separates digit runs from letters.
3. **Self-correction.** Drops everything before the last correction marker. English markers include `wait`, `sorry`, `I mean`, `no no` and `let me repeat`. Hindi markers include `galat`, `nahi`, `ruko`, `matlab`, `phir se`, `रुको` and `गलत`.
4. **Classify.** Maps each token to one of: a digit (0–9), a multi-digit number word, a tens word, a multiplier (`double` or `triple`), `hundred`, or `thousand`. Filler words like "my number is" or "mera number hai" are ignored.
5. **Compose.** Builds the digit string from those tokens:
   - `ninety eight` → 98, `atthaanve` → 98, `अट्ठानवे` → 98
   - `double seven` → 77, `triple nine` → 999
   - `nine hundred eighty seven` → 987
   - `oh`, `o`, `zero`, `shunya`, `sifar` and `शून्य` all → 0
6. **Validate.** Strips a `+91` or leading `0` prefix when exactly 10 digits remain, then requires 10 digits starting with 6–9.

It returns a `ParseResult` containing the digits, the language (`en`, `hi` or `mixed`), whether a correction happened, and an error (`no_digits`, `too_few`, `too_many` or `invalid_prefix`).

The language is decided from the words that matched. Only English → `en`, only Hindi → `hi`, both → `mixed`. A transcript made only of numerals falls back to the language the STT detected.

Bare English "no" is deliberately **not** a correction marker, because STT often writes Hindi *nau* (9) as "no".

## Conversation flow

`dialog/collector.py` contains the state machine:

| Situation | What the agent does |
|---|---|
| Fewer than 10 digits so far | **Stays silent** and accumulates the digits. A pause never ends the number. |
| 4 s of silence with partial digits | "I only got 8 digits. Could you repeat your full number?" |
| 10 valid digits | "Let me confirm — your number is nine, eight, seven, six, five… four, three, two, one, zero. Is that correct?" The number is always read digit by digit. |
| User says yes, "haan" or "sahi hai" | POSTs to the API, then "Thank you! Your number has been saved." and the call ends. |
| User says no, "nahi" or "galat" | Resets and asks for the number again. |
| "No, it's 98…" while confirming | Treats the new digits as a fresh attempt. |
| More than 10 digits, or a first digit outside 6–9 | Resets and gives the matching error prompt. |
| Low SNR or low STT confidence | Discards **only that segment** and asks for it again. Digits collected earlier are kept. |

The pause timer counts from the moment the user stops speaking, using VAD state, and is cancelled as soon as they start speaking again.

The agent always *understands* English, Hindi and Hinglish. Both TTS options (Groq and Deepgram) have English-only voices, so it always *replies* in English. Hindi prompt texts are still in `dialog/prompts.py`, ready for a multilingual TTS.

## Noise handling: what's used and why

1. **LiveKit Background Voice Cancellation (BVC)** runs on the input track before VAD and STT (`NOISE_CANCELLATION=bvc`). It is Krisp's model, integrated natively in LiveKit Cloud. Besides stationary noise (traffic, fans, room echo), it also removes **other people's voices**, i.e. background chatter. That matters here because a nearby speaker reading out digits would otherwise get merged into the number. `bvc_telephony` is tuned for SIP/8 kHz calls. A self-hosted LiveKit server can't use these filters, so set `none` there.
   - RNNoise or WebRTC NS handle stationary noise but not competing speech, so they were not used.
2. **The SNR gate** ([`agent/snr.py`](src/phone_agent/agent/snr.py)) wraps `stt_node` and measures each turn's SNR on the *suppressed* audio, which is what the STT actually hears:
   - SNR = 90th-percentile turn level − 10th-percentile level over the last 15 s.
   - Turns below `MIN_SNR_DB` are not parsed. The agent asks for that segment again instead of guessing.
3. **The STT confidence gate.** Deepgram's transcript confidence is checked the same way, against `MIN_STT_CONFIDENCE`.
4. **STT choice.** Deepgram Nova-3 with `language=multi` transcribes Hindi and English code-switching in one streaming connection with interim results. Hinglish like "nine aath saat 6 5" never forces a language switch. It also returns a confidence score for the gate above.
   - Groq Whisper (`STT_PROVIDER=groq`) is supported as an alternative. It is not streaming: Silero VAD cuts the audio into utterances. It returns no confidence score, so only the SNR gate applies. Whisper sometimes writes Hindi in Urdu script, and the parser understands that too.

## Bonus features

- **Confidence scoring:** low STT confidence or low SNR causes the agent to ask again for only the affected segment.
- **Unit tests:** 100 cases, run with `uv run pytest`. They cover grouping styles, the three languages, double/triple/oh/shunya, self-correction, validation, the dialog flow, and the API.
- **TTS caching:** the greeting, error prompts and the "saved" message are synthesised once and stored as WAV in `.cache/tts`. They play back without a TTS request. The confirmation contains the number, so it is always streamed live.
- **Prompt caching (LLM):** not applicable, because the agent uses no LLM.

## Tests

```bash
uv run pytest
```
