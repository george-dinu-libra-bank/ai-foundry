# Libra Assist — Admin Console

The operator/admin surface for **Libra Assist**, built on top of the
[RAG Teaching API](../backend/README.md). It is a thin frontend that consumes the
documented API at `http://localhost:7799` and surfaces its results **and errors**
honestly — the screen an operator uses to load knowledge, inspect what's stored,
and test answers (not the end-user chat).

Plain **HTML + CSS + JavaScript** (`fetch`). No framework, no build step, no
dependencies.

## Run it

The backend must be running first (see [`code/backend`](../backend/README.md) —
`docker compose up -d --build`, then confirm `GET /health` is `ok`).

Then just **open `index.html`** in a browser:

```bash
# from this folder
start index.html      # Windows
# open index.html     # macOS
# xdg-open index.html # Linux
```

CORS on the API is open (`*`), so the page works straight from disk (`file://`) —
no dev server needed. If you prefer serving it:

```bash
python -m http.server 5500   # then visit http://localhost:5500
```

The **API base** field in the top bar defaults to `http://localhost:7799` and is
remembered between sessions; point it elsewhere if your backend runs on another port.

## What it does

Each control is wired to the matching endpoint:

| Tab | Endpoint(s) | Shows |
|---|---|---|
| **Status** | `GET /health`, `GET /config` | Active chat/embedding providers + models, Qdrant reachability, chunking/retrieval defaults, Azure Foundry config (key masked) |
| **Chunk** | `POST /chunk` | Paste text, pick a strategy (`static` / `sentence` / `dynamic` / `semantic`) + params, see the resulting chunks with char/token counts |
| **Ingest** | `POST /ingest` | How many chunks were stored, the **vector dimension**, the embedding model, and the first 8 numbers of an embedding |
| **Collection** | `GET` / `DELETE /collection` | What Qdrant holds; reset is guarded by a confirm dialog |
| **Search** | `POST /search` | Nearest chunks with **cosine similarity scores**, highest first, plus a score bar |
| **Ask** | `POST /ask` | The **answer**, the **retrieved chunks**, and the exact **`prompt_sent`**; toggle `use_rag`, or **Compare RAG on/off** side by side |

### Honest error surfacing

Every call routes through one `fetch` wrapper that reads the API's status code and
`detail` message and renders them in a red box instead of failing silently — e.g.
`409` on a dimension mismatch, `404` on an empty collection, `503` when Qdrant is
down, `502` on an LLM/embedding failure, `422` on bad input, and a `NETWORK` state
when the backend can't be reached at all.

### Stretch goals included

- First few numbers of the embedding vector shown on `/ingest` and `/search`.
- Side-by-side `use_rag: false` vs `true` comparison for the same question.
- Last-used settings (API base, strategy, `top_k`, `use_rag`, temperature) persisted
  in `localStorage`.

## Security

- Talks **only** to the local API.
- **No secrets in the frontend** — the Foundry key stays server-side in the
  backend's `.env`; the browser never sees it (`/config` returns it masked).

## Files

- `index.html` — markup and layout
- `styles.css` — the course-neutral "Libra" theme (light + dark aware)
- `app.js` — API layer, rendering, and all endpoint wiring
