from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.config import settings
from app.web.database import get_user_bundle
from app.web.settings import WEB_DATA_DIR
from app.worker.simple_runner import run_cycle_with_profile


def _timestamped(message: str) -> str:
    return f"[{datetime.utcnow().isoformat()}] {message}"


class AutomationManager:
    def __init__(self, *, profile_loader: Callable[[int], dict[str, str]]):
        self._profile_loader = profile_loader
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._logs: deque[str] = deque(maxlen=200)
        self._user_id: int | None = None
        self._last_started_at: str | None = None
        self._last_finished_at: str | None = None
        self._last_error: str | None = None

    def _log(self, message: str) -> None:
        entry = _timestamped(message)
        with self._lock:
            self._logs.append(entry)

    def _user_paths(self, user_id: int) -> tuple[str, str]:
        user_root = WEB_DATA_DIR / "users" / str(user_id)
        state_path = user_root / "state.json"
        screenshots_dir = user_root / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        return str(state_path), str(screenshots_dir)

    def _loop(self, user_id: int) -> None:
        with self._lock:
            self._last_started_at = datetime.utcnow().isoformat()
            self._last_finished_at = None
            self._last_error = None

        try:
            while not self._stop_event.is_set():
                profile = self._profile_loader(user_id)
                state_path, screenshots_dir = self._user_paths(user_id)
                run_cycle_with_profile(
                    profile=profile,
                    state_path=state_path,
                    screenshots_dir=screenshots_dir,
                    log_fn=self._log,
                )
                for _ in range(max(settings.apply_poll_seconds, 1)):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._last_error = str(exc)
            self._log(f"runner error: {exc}")
        finally:
            with self._lock:
                self._last_finished_at = datetime.utcnow().isoformat()
                self._thread = None
                self._user_id = None
            self._stop_event.clear()

    def start(self, user_id: int) -> dict[str, object]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._user_id == user_id:
                    return self.status()
                raise RuntimeError("Another automation session is already running")

            self._logs.clear()
            self._user_id = user_id
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, args=(user_id,), daemon=True)
            self._thread.start()
            self._log(f"automation started for user {user_id}")
            return self.status()

    def stop(self) -> dict[str, object]:
        thread: threading.Thread | None = None
        with self._lock:
            thread = self._thread
            if thread and thread.is_alive():
                self._stop_event.set()
                self._logs.append(_timestamped("stop requested"))
        if thread and thread.is_alive():
            thread.join(timeout=5)
        return self.status()

    def status(self) -> dict[str, object]:
        with self._lock:
            running = bool(self._thread and self._thread.is_alive())
            return {
                "running": running,
                "user_id": self._user_id,
                "last_started_at": self._last_started_at,
                "last_finished_at": self._last_finished_at,
                "last_error": self._last_error,
                "logs": list(self._logs),
            }


def build_runtime_profile_for_user(user_id: int) -> dict[str, str]:
    bundle = get_user_bundle(user_id)
    user = bundle["user"]
    profile = bundle["profile"]
    user_root = WEB_DATA_DIR / "users" / str(user_id)
    browser_profile = user_root / "browser-profile"
    browser_profile.mkdir(parents=True, exist_ok=True)
    runtime_profile = {
        "full_name": profile["full_name"],
        "email": profile["contact_email"] or user["email"],
        "phone": profile["phone"],
        "resume_path": profile["resume_path"],
        "instahyre_user_data_dir": str(browser_profile),
        "instahyre_email": profile["instahyre_email"],
        "instahyre_password": profile["instahyre_password"],
        "instahyre_opportunities_url": settings.instahyre_opportunities_url,
        "instahyre_login_url": settings.instahyre_login_url,
    }
    return {key: value for key, value in runtime_profile.items() if value}
