# Frontend

The web page of the Earthquake Preparedness Assistant: chat, sources, live earthquake panel with a 3D globe.
React + TypeScript + Vite + Tailwind CSS.

## Start

You need Node.js 20 or newer (https://nodejs.org, the LTS version).

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

The page expects the backend on http://localhost:8000 (see `backend/README.md`).

## Run without the backend

```bash
npm run dev:fake
```

Answers and earthquakes are then fake, so the page can be developed and shown alone.
To see every state of the chat in this mode:

- a question containing `tomorrow` gives the "not found in the documents" answer
- a question containing `error` gives the error message
- anything else gives a normal answer with two sources

## Settings

Copy `.env.example` to `.env` to change them.

| Setting | Default | Meaning |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Address of the backend |
| `VITE_USE_FAKE` | `false` | `true` runs the page without the backend |

## Files

| File | What it does |
|---|---|
| `src/App.tsx` | The page: banner, chat, message box |
| `src/MessageBubble.tsx` | One message: user, loading, error, not found, answer with sources |
| `src/EarthquakePanel.tsx` | Live earthquake panel: globe, selected earthquake, list |
| `src/QuakeGlobe.tsx` | 3D globe with one dot per earthquake (library: react-globe.gl) |
| `public/earth.jpg` | Picture of the Earth for the globe, stored locally so it needs no internet |
| `src/useEarthquakes.ts` | Loads the earthquakes and refreshes them every 5 minutes |
| `src/api.ts` | All requests to the backend |
| `src/fakeApi.ts` | Fake answers for running without the backend |
| `src/types.ts` | Shapes of the data from the API contract |

## Globe and coordinates

The globe shows every earthquake of the past 24 hours. Bigger dot = stronger;
grey below M2.5, yellow from 2.5, orange from 4, red from 5. Click a dot or a row of the list to select it.

The backend's `/api/earthquakes` does not send coordinates yet, so the page reads them from the
same USGS feed directly (this needs internet). If the backend adds `lat` and `lon` to each event,
the page uses those and stops asking USGS; no change in the frontend is needed.

## Status

Done: dark theme, chat, emergency banner, sources, loading, error and not-found states, real backend, live panel, 3D globe.
Not done yet: microphone, play-answer button, photo upload, alert banner.
