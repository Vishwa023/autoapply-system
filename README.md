# Instahyre Auto Apply

This project is now a single-purpose Instahyre auto-apply runner.

It does only this:
- poll your Instahyre opportunities page
- try to apply immediately
- keep a tiny local state file so it does not re-apply to the same opportunity every cycle
- save screenshots for blocked or failed attempts

It does not use Postgres, FastAPI, scoring, queues, or intervention APIs anymore in the Docker runtime.

## Runtime shape
- `autoapply`: one Playwright-based worker container
- `./data/state.json`: local apply history and retry state
- `./data/browser-profile`: persistent Chromium profile/session
- `./data/screenshots`: screenshots from attempts

## First-time setup
1. Copy env file:
   - `cp .env.example .env`
2. Put your resume where the container can read it:
   - `mkdir -p data`
   - place your resume at `./data/resume.pdf`
3. Edit `.env` and fill:
   - `FULL_NAME`
   - `EMAIL`
   - `PHONE`
   - `RESUME_PATH=/data/resume.pdf`
   - optionally `INSTAHYRE_EMAIL` and `INSTAHYRE_PASSWORD`
   - leave `BROWSER_CHANNEL` empty unless you have a specific installed browser you want to target

## Manual login once
Use this if Instahyre needs OTP/CAPTCHA or you prefer saving a browser session interactively.

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m playwright install chromium
./scripts/manual_login_local.sh
```

This opens a real browser window on your Mac. Log in once and the session will be saved under `./data/browser-profile`, which the Docker container also uses.

The runner uses the `?matching=true` opportunities page by default because the plain opportunities route can return an Instahyre error page on some accounts.

## Start auto-apply loop
```bash
docker compose up --build -d
```

## Run locally (without Docker)
If you prefer to run the runner directly on your host machine (e.g., for debugging or to see the browser window):

1. **Setup environment** (if not already done for manual login):
   ```bash
   python3 -m venv .venv
   ./.venv/bin/pip install -r requirements.txt
   ./.venv/bin/python -m playwright install chromium
   ```

2. **Run the script**:
   ```bash
   ./scripts/run_local_autoapply.sh
   ```
   This script will use `./data/browser-profile` for the session and `./data/state-local.json` for tracking. By default, it runs with `HEADLESS=false` so you can watch the automation.

## Watch logs
```bash
docker compose logs -f autoapply
```

Typical log lines:
- `login required: ...`
- `instahyre-... status=applied ...`
- `instahyre-... status=needs_user ...`
- `cycle complete opportunities=... attempted=... applied=...`

## Stop
```bash
docker compose down
```

## Files written locally
- `./data/state.json`
- `./data/screenshots/...`
- `./data/browser-profile/...`

## Important behavior
- Jobs already marked `applied` are skipped on future polls.
- Jobs marked `needs_user` are also skipped so the runner does not hammer blocked forms forever.
- Failed jobs are retried up to `MAX_APPLY_ATTEMPTS`.
- Docker runs headless; use `./scripts/manual_login_local.sh` when you need a visible browser.
- This still does not bypass CAPTCHA, OTP, or other anti-bot flows.
