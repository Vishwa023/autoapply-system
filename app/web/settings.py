from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_DATA_DIR = Path(os.getenv("WEB_DATA_DIR", ROOT_DIR / "data" / "web"))
DATABASE_PATH = Path(os.getenv("WEB_DATABASE_PATH", WEB_DATA_DIR / "app.db"))
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
SESSION_COOKIE_NAME = os.getenv("WEB_SESSION_COOKIE_NAME", "autoapply_session")
SESSION_MAX_AGE_SECONDS = int(os.getenv("WEB_SESSION_MAX_AGE_SECONDS", "2592000"))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
DEFAULT_FRONTEND_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("WEB_CORS_ORIGINS", DEFAULT_FRONTEND_ORIGINS).split(",")
    if origin.strip()
]
