from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError


@contextmanager
def profile_lock(profile_dir: str):
    profile_path = Path(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    lock_path = profile_path / ".profile.lock"
    with lock_path.open("w") as lock_file:
        deadline = time.time() + 180
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise TimeoutError("Timed out waiting for Instahyre browser profile lock")
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _profile_has_live_browser_process(profile_dir: str) -> bool:
    proc_root = Path("/proc")
    if not proc_root.exists():
        return False

    for proc_dir in proc_root.iterdir():
        if not proc_dir.name.isdigit():
            continue
        try:
            cmdline = (proc_dir / "cmdline").read_bytes().decode("utf-8", errors="ignore")
        except OSError:
            continue
        if not cmdline:
            continue
        flattened = cmdline.replace("\x00", " ")
        if profile_dir in flattened and "chrome" in flattened:
            return True
    return False


def cleanup_stale_chromium_profile_locks(profile_dir: str) -> list[str]:
    profile_path = Path(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)

    if _profile_has_live_browser_process(profile_dir):
        return []

    stale_paths = [
        profile_path / "SingletonLock",
        profile_path / "SingletonSocket",
        profile_path / "SingletonCookie",
        profile_path / "Default" / "LOCK",
    ]
    removed: list[str] = []

    for path in stale_paths:
        try:
            if path.exists() or path.is_symlink():
                os.unlink(path)
                removed.append(str(path))
        except FileNotFoundError:
            continue
    return removed


def launch_persistent_context(playwright, *, profile_dir: str, headless: bool, channel: str | None):
    removed = cleanup_stale_chromium_profile_locks(profile_dir)
    if removed:
        print(f"cleared stale chromium locks: {', '.join(removed)}", flush=True)

    try:
        return playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            channel=channel,
        )
    except PlaywrightError as exc:
        message = str(exc).lower()
        recoverable = (
            "profile appears to be in use" in message
            or "target page, context or browser has been closed" in message
        )
        if not recoverable:
            raise

        removed = cleanup_stale_chromium_profile_locks(profile_dir)
        if removed:
            print(f"retrying after clearing stale chromium locks: {', '.join(removed)}", flush=True)
        return playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            channel=channel,
        )
