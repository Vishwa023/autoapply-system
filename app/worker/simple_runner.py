from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.config import settings
from app.runtime_profile import load_runtime_profile
from app.services.instahyre_source import crawl_instahyre_opportunities
from app.worker.automation import attempt_apply
from app.worker.simple_state import SimpleStateStore


def _log(message: str) -> None:
    print(f"[{datetime.utcnow().isoformat()}] {message}", flush=True)


def _opportunity_key(external_id: str | None, apply_url: str) -> str:
    if external_id:
        return external_id
    digest = hashlib.sha1(apply_url.encode("utf-8")).hexdigest()[:16]
    return f"instahyre-{digest}"


def run_cycle_with_profile(
    *,
    profile: dict[str, str],
    state_path: str,
    screenshots_dir: str,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    logger = log_fn or _log
    state = SimpleStateStore(state_path)
    logger("starting poll cycle")
    crawl = crawl_instahyre_opportunities(profile=profile, manual_login=False)
    if crawl.requires_login:
        logger(f"login required: {crawl.details}")
        return

    if not crawl.opportunities:
        logger("no opportunities found")
        return

    attempted = 0
    applied = 0
    blocked = 0
    failed = 0

    for opportunity in crawl.opportunities:
        apply_url = str(opportunity.apply_url)
        key = _opportunity_key(opportunity.external_id, apply_url)

        output_dir = Path(screenshots_dir) / key
        result = attempt_apply(
            apply_url,
            profile,
            output_dir,
            job_title=opportunity.title,
            company=opportunity.company,
        )
        attempted += 1

        state.record(
            key=key,
            title=opportunity.title,
            company=opportunity.company,
            apply_url=apply_url,
            status=result.status,
            details=result.details,
            screenshot_path=result.screenshot_path,
        )

        logger(
            f"{key} status={result.status} company='{opportunity.company}' "
            f"title='{opportunity.title}' details='{result.details}'"
        )

        if result.status == "applied":
            applied += 1
            continue

        if result.status == "needs_user":
            blocked += 1
            if "login required" in result.details.lower():
                logger("stopping current cycle because the saved Instahyre session needs login again")
                break
            continue

        failed += 1

    logger(
        f"cycle complete opportunities={len(crawl.opportunities)} attempted={attempted} "
        f"applied={applied} blocked={blocked} failed={failed}"
    )


def run_cycle() -> None:
    run_cycle_with_profile(
        profile=load_runtime_profile(),
        state_path=settings.state_path,
        screenshots_dir=settings.screenshots_dir,
        log_fn=_log,
    )


def worker_loop() -> None:
    while True:
        try:
            run_cycle()
        except Exception as exc:  # noqa: BLE001
            _log(f"runner error: {exc}")
        time.sleep(settings.apply_poll_seconds)


if __name__ == "__main__":
    worker_loop()
