from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


class SimpleStateStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"jobs": {}}

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"jobs": {}}

        jobs = payload.get("jobs")
        if not isinstance(jobs, dict):
            return {"jobs": {}}
        return {"jobs": jobs}

    def get(self, key: str) -> dict[str, Any] | None:
        return self.load()["jobs"].get(key)

    def should_attempt(self, key: str, max_attempts: int) -> bool:
        record = self.get(key)
        if not record:
            return True

        status = record.get("status", "")
        attempts = int(record.get("attempts", 0))
        if status in {"applied", "needs_user"}:
            return False
        return attempts < max_attempts

    def record(
        self,
        *,
        key: str,
        title: str,
        company: str,
        apply_url: str,
        status: str,
        details: str,
        screenshot_path: str | None,
    ) -> dict[str, Any]:
        state = self.load()
        previous = state["jobs"].get(key, {})
        attempts = int(previous.get("attempts", 0)) + 1
        state["jobs"][key] = {
            "title": title,
            "company": company,
            "apply_url": apply_url,
            "status": status,
            "details": details,
            "attempts": attempts,
            "screenshot_path": screenshot_path,
            "updated_at": _utcnow(),
        }
        self._save(state)
        return state["jobs"][key]

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.path)
