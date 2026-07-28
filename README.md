# NXT Reel AI

AI Creative Director that turns a talking-head video into an export-ready,
fully-edited viral reel — jump cuts, dynamic captions, B-roll, motion
graphics, browser recordings, zooms, music, SFX, and CTA — with no manual
editing.

**Core philosophy:** AI decides everything; the renderer only executes.

## Architecture

```
Upload Video → Extract Audio → Whisper Transcription → GPT-5 Director
   → Timeline JSON → [Browser | Stock | Motion Graphics | Image Gen | UI Template] Engines
   → Render Engine → Export MP4
```

- **`app/ai/transcription.py`** — Whisper transcription (audio → word-timed segments)
- **`app/ai/director.py`** — GPT-5 AI Director (segments → creative Timeline JSON)
- **`app/models/timeline.py`** — the Timeline JSON schema — the single contract
  every other module reads/writes
- **`app/engines/`** — the 5 visual engines, each resolving one kind of `VisualEvent`
- **`app/services/render_service.py`** — Render Engine: resolves assets + composites
  the final MP4 (composition logic is stubbed — see `composite_timeline`)
- **`app/api/routes/`** — REST API: `/upload`, `/transcribe`, `/generate-timeline`,
  `/render`, `/export`, `/project`, `/status`

## What's implemented vs. stubbed

Implemented: project structure, DB models, Timeline schema, all API routes,
Whisper transcription call, GPT-5 Director call + prompt, Celery job wiring,
engine skeletons with real Playwright/MoviePy/API calls.

Left as clear extension points (marked `TODO` / `NotImplementedError`):
- `composite_timeline()` — the actual FFmpeg/MoviePy composition of jump
  cuts, caption burn-in, layered visuals, and audio mixing
- Browser Engine action replay (currently just loads a URL and waits)
- UI Template Engine's dynamic data injection into HTML templates
- Style presets currently only set a string on the Director prompt — you'll
  want a `style_presets.py` config mapping each preset to concrete caption
  fonts/colors/pacing/music library tags

These are left for you to fill in deliberately, since they're where your
actual creative/product decisions belong — the scaffold gives you a place
to put them without guessing your taste for you.

## Deploying to your VPS

1. **Create an isolated user** so this project never touches your other
   project's files or containers:
   ```bash
   sudo bash deploy/setup_vps_user.sh
   ```
   This creates a `nxtreel` system user, adds it to the `docker` group, and
   sets up `~/nxt-reel-ai` and `~/storage/{uploads,renders,assets}`.

2. **Copy this project onto the VPS** into that user's home directory, e.g.:
   ```bash
   scp -r nxt-reel-ai/ nxtreel@your-vps-ip:~/nxt-reel-ai
   ```

3. **Switch to that user and configure secrets:**
   ```bash
   su - nxtreel
   cd ~/nxt-reel-ai
   cp .env.example .env
   # edit .env: set POSTGRES_PASSWORD, OPENAI_API_KEY, etc.
   ```

4. **Bring it up:**
   ```bash
   docker compose up -d --build
   ```
   - Backend API: `http://your-vps-ip:8000` (docs at `/docs`)
   - Frontend: `http://your-vps-ip:3000`

5. If you're running this alongside Coolify, you can instead point Coolify
   at this repo/directory as a Docker Compose resource rather than running
   `docker compose` by hand — the `docker-compose.yml` here works either way.

## Local development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests:
```bash
pytest
```

## Development rules (per project spec)

Production-quality code only, no demo architecture, modular design,
Docker-first, API-first, typed Python, environment variables only (no
hardcoded secrets), logging everywhere, unit + integration tests, no
duplicated logic, clean architecture.
