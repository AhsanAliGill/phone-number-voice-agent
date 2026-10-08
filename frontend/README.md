# Frontend

This is plain HTML, CSS and JavaScript, with no framework and no build step. It talks to the backend REST API and joins LiveKit rooms with [`livekit-client`](https://github.com/livekit/client-sdk-js), loaded from a CDN.

| File | What it does |
|---|---|
| `index.html` | Page layout: call panel and dashboard |
| `app.js` | Voice call (token → LiveKit room → mic → live transcripts) and dashboard (list, filters, expand, delete, stats, 5 s auto-refresh) |
| `style.css` | Styles (light and dark mode, responsive) |
| `config.js` | `apiBaseUrl`: where the backend lives |

## Running

**Option 1: served by the backend (recommended).** Start the API from `backend/` and open http://127.0.0.1:8000. It serves this folder at `/`, so `config.js` can stay `apiBaseUrl: ""`.

**Option 2: served separately.** Set `apiBaseUrl: "http://127.0.0.1:8000"` in `config.js`, then:

```bash
cd frontend
python -m http.server 5500
```

Open http://127.0.0.1:5500. The backend allows cross-origin requests (`CORS_ORIGINS`, default `*`).

## Features

- **Talk to the agent:** start/end the call, mute, see the agent's state (listening, thinking or speaking), and read live transcripts of both sides.
- **Dashboard:**
  - total count, plus breakdown by language (en, hi, mixed)
  - search by number, filter by language and date range
  - click a row to see the raw transcript
  - delete a record (`DELETE /api/phone/:id`)
