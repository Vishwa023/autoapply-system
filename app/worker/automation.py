from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.browser_profile import launch_persistent_context, profile_lock
from app.config import settings


KNOWN_SELECTORS = {
    "full_name": ["input[name='name']", "input[name='fullName']", "input[placeholder*='name' i]"],
    "email": ["input[type='email']", "input[name='email']"],
    "phone": ["input[type='tel']", "input[name='phone']"],
    "resume": ["input[type='file']"],
}

VIEW_BUTTON_SELECTORS = [
    "button#interested-btn.button-interested.btn.btn-success",
    "button#interested-btn",
    "button.button-interested",
]

OPPORTUNITIES_PAGE_READY_TIMEOUT_MS = 12000
OPPORTUNITIES_PAGE_SETTLE_MS = 5000
VIEW_MODAL_SETTLE_MS = 3000
MANUAL_REVIEW_WAIT_SECONDS = 600


class AutomationResult:
    def __init__(self, status: str, details: str, screenshot_path: Optional[str] = None):
        self.status = status
        self.details = details
        self.screenshot_path = screenshot_path


def _looks_like_security_check(page_content: str) -> bool:
    html = page_content.lower()
    checks = [
        "security verification",
        "verify you are a human",
        "checking if the site connection is secure",
        "cloudflare",
        "captcha",
    ]
    return any(token in html for token in checks)


def _fill_first(page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            locator.first.fill(value)
            return True
    return False


def _safe_screenshot(page, screenshot_path: Path) -> Optional[str]:
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        return str(screenshot_path)
    except PlaywrightError:
        return None


def _pause_for_manual_review(page, details: str) -> None:
    if settings.headless:
        return
    try:
        if page.is_closed():
            return
    except PlaywrightError:
        return

    print(
        f"manual review needed: {details}. Keeping browser open for up to {MANUAL_REVIEW_WAIT_SECONDS} seconds.",
        flush=True,
    )
    deadline = time.time() + MANUAL_REVIEW_WAIT_SECONDS
    while time.time() < deadline:
        try:
            if page.is_closed():
                return
            page.wait_for_timeout(1000)
        except PlaywrightError:
            return


def _needs_user_result(page, details: str, screenshot_path: Path) -> AutomationResult:
    saved_screenshot = _safe_screenshot(page, screenshot_path)
    _pause_for_manual_review(page, details)
    return AutomationResult("needs_user", details, saved_screenshot)


def _click_first_visible(page, selectors: list[str], timeout_ms: int = 3000) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except PlaywrightError:
            continue
        for idx in range(count):
            try:
                candidate = locator.nth(idx)
                if not candidate.is_visible(timeout=timeout_ms):
                    continue
                candidate.click(timeout=timeout_ms)
                return True
            except PlaywrightError:
                continue
    return False


def _click_locator(locator, timeout_ms: int = 5000) -> bool:
    try:
        locator.wait_for(state="visible", timeout=timeout_ms)
        locator.scroll_into_view_if_needed(timeout=timeout_ms)
        locator.click(timeout=timeout_ms)
        return True
    except PlaywrightError:
        try:
            locator.dispatch_event("click")
            return True
        except PlaywrightError:
            return False


def _find_matching_card_index(card_texts: list[str], job_title: str, company: str) -> int:
    title_l = " ".join((job_title or "").strip().lower().split())
    company_l = " ".join((company or "").strip().lower().split())

    for idx, text in enumerate(card_texts):
        normalized = " ".join((text or "").lower().split())
        if title_l and title_l in normalized and company_l and company_l in normalized:
            return idx

    for idx, text in enumerate(card_texts):
        normalized = " ".join((text or "").lower().split())
        if title_l and title_l in normalized:
            return idx

    for idx, text in enumerate(card_texts):
        normalized = " ".join((text or "").lower().split())
        if company_l and company_l in normalized:
            return idx

    return -1


def _wait_for_visible_selector(page, selectors: list[str], timeout_ms: int) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except PlaywrightError:
            continue
        for idx in range(count):
            try:
                locator.nth(idx).wait_for(state="visible", timeout=timeout_ms)
                return True
            except PlaywrightError:
                continue
    return False


def _wait_for_load_state_safe(page, state: str, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state(state, timeout=timeout_ms)
    except PlaywrightError:
        return


def _settle_opportunities_page(page) -> None:
    _wait_for_load_state_safe(page, "domcontentloaded", timeout_ms=OPPORTUNITIES_PAGE_READY_TIMEOUT_MS)
    _wait_for_load_state_safe(page, "networkidle", timeout_ms=OPPORTUNITIES_PAGE_READY_TIMEOUT_MS)
    _wait_for_visible_selector(
        page,
        ["a.row.text-link", *VIEW_BUTTON_SELECTORS],
        timeout_ms=OPPORTUNITIES_PAGE_READY_TIMEOUT_MS,
    )
    page.wait_for_timeout(OPPORTUNITIES_PAGE_SETTLE_MS)


def _apply_from_opportunities_page(page, job_title: str, company: str) -> bool:
    _settle_opportunities_page(page)
    cards = page.locator("a.row.text-link")
    n = cards.count()
    target_idx = _find_matching_card_index(
        [(cards.nth(i).inner_text() or "") for i in range(n)],
        job_title=job_title,
        company=company,
    )
    if target_idx < 0:
        return False

    matched_card = cards.nth(target_idx)
    clicked_view = False
    for selector in VIEW_BUTTON_SELECTORS:
        try:
            view_button = matched_card.locator(selector).first
            if view_button.count() > 0:
                clicked_view = _click_locator(view_button, timeout_ms=10000)
            if clicked_view:
                break
        except PlaywrightError:
            continue

    if not clicked_view:
        clicked_view = _click_locator(matched_card, timeout_ms=10000)

    if not clicked_view:
        return False

    _wait_for_visible_selector(
        page,
        [
            ".candidate-apply-modal .application-modal-wrap",
            ".application-modal-wrap",
        ],
        timeout_ms=10000,
    )
    page.wait_for_timeout(VIEW_MODAL_SETTLE_MS)
    _wait_for_load_state_safe(page, "networkidle", timeout_ms=8000)

    modal_apply_selectors = [
        ".candidate-apply-modal button:has-text('Apply')",
        ".candidate-apply-modal button:has-text('Apply Now')",
        ".candidate-apply-modal button[type='submit']",
        ".application-modal-wrap button:has-text('Apply')",
        ".application-modal-wrap button:has-text('Apply Now')",
        ".application-modal-wrap button[type='submit']",
    ]
    if not _wait_for_visible_selector(page, modal_apply_selectors, timeout_ms=10000):
        return False

    return _click_first_visible(
        page,
        modal_apply_selectors,
        timeout_ms=10000,
    )


def attempt_apply(
    job_url: str,
    profile: dict[str, str],
    output_dir: Path,
    job_title: str = "",
    company: str = "",
) -> AutomationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / "latest.png"
    profile_dir = str(Path(profile.get("instahyre_user_data_dir", "~/.autoapply-instahyre-profile")).expanduser())

    with sync_playwright() as p:
        with profile_lock(profile_dir):
            context = launch_persistent_context(
                p,
                profile_dir=profile_dir,
                headless=settings.headless,
                channel=settings.browser_channel or None,
            )
            page = context.new_page()

            try:
                page.goto(job_url, timeout=45000, wait_until="domcontentloaded")
                if "/login" in page.url:
                    return _needs_user_result(page, "Session expired/login required", screenshot_path)

                page_content = page.content()
                # if _looks_like_security_check(page_content):
                #     if not settings.headless:
                #         for _ in range(45):
                #             page.wait_for_timeout(2000)
                #             if not _looks_like_security_check(page.content()):
                #                 break
                #     if _looks_like_security_check(page.content()):
                #         return _needs_user_result(
                #             page,
                #             "Security verification/CAPTCHA encountered",
                #             screenshot_path,
                #         )

                if "/candidate/opportunities" in page.url:
                    submitted = _apply_from_opportunities_page(page, job_title, company)
                    if not submitted:
                        return _needs_user_result(
                            page,
                            "Matching opportunity/apply button not found on opportunities page",
                            screenshot_path,
                        )
                    page.wait_for_timeout(3000)
                    return AutomationResult(
                        "applied",
                        "Submitted from opportunities page",
                        _safe_screenshot(page, screenshot_path),
                    )

                required = {
                    "full_name": profile.get("full_name", ""),
                    "email": profile.get("email", ""),
                    "phone": profile.get("phone", ""),
                }

                for key, value in required.items():
                    if value:
                        _fill_first(page, KNOWN_SELECTORS[key], value)

                resume_path = profile.get("resume_path", "")
                if resume_path and Path(resume_path).exists():
                    for selector in KNOWN_SELECTORS["resume"]:
                        locator = page.locator(selector)
                        if locator.count() > 0:
                            locator.first.set_input_files(resume_path)
                            break

                submit_candidates = [
                    "button[type='submit']",
                    "button:has-text('Apply')",
                    "button:has-text('Apply Now')",
                    "button:has-text('I'm Interested')",
                    "button:has-text('Submit')",
                    "a:has-text('Apply')",
                    "a:has-text('Apply Now')",
                    "[role='button']:has-text('Apply')",
                ]
                submitted = _click_first_visible(page, submit_candidates)

                if not submitted:
                    return _needs_user_result(page, "No trusted submit button found; manual review needed", screenshot_path)

                saved_screenshot = _safe_screenshot(page, screenshot_path)
                page.wait_for_timeout(3000)
                html = page.content().lower()
                if "otp" in html or "one time password" in html or "verification code" in html:
                    _pause_for_manual_review(page, "OTP verification required")
                    return AutomationResult("needs_user", "OTP verification required", saved_screenshot)

                return AutomationResult("applied", "Submitted by automation", saved_screenshot)

            except PlaywrightTimeoutError:
                return AutomationResult("failed", "Page timeout", _safe_screenshot(page, screenshot_path))
            except Exception as exc:  # noqa: BLE001
                return AutomationResult(
                    "failed",
                    f"Automation error: {exc}",
                    _safe_screenshot(page, screenshot_path),
                )
            finally:
                context.close()
