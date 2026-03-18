from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.browser_profile import launch_persistent_context, profile_lock
from app.config import settings
from app.opportunities import OpportunityIn


DEFAULT_OPPORTUNITIES_URL = "https://www.instahyre.com/candidate/opportunities/?matching=true"
DEFAULT_LOGIN_URL = "https://www.instahyre.com/login/"


@dataclass
class CrawlResult:
    opportunities: List[OpportunityIn]
    requires_login: bool
    details: str


def _is_instahyre_job_url(href: str) -> bool:
    if not href:
        return False
    parsed = urlparse(href)
    host = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/")
    if "instahyre.com" not in host:
        return False
    if re.match(r"^/candidate/opportunities/\d+$", path):
        return True
    if re.match(r"^/job/[^/]+$", path):
        return True
    return False


def _normalize_instahyre_url(base_url: str, raw_href: str) -> str:
    href = (raw_href or "").strip()
    if not href:
        return ""
    absolute = urljoin(base_url.rstrip("/") + "/", href)
    parsed = urlparse(absolute)
    cleaned = parsed._replace(query="", fragment="")
    return urlunparse(cleaned).rstrip("/")


def extract_job_links_from_html(base_url: str, links: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for href in links:
        href = _normalize_instahyre_url(base_url, href)
        if not _is_instahyre_job_url(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        deduped.append(href)
    return deduped


def _fill_first_visible(page, selectors: List[str], value: str, timeout_ms: int = 15000) -> bool:
    if not value:
        return False

    for selector in selectors:
        locator = page.locator(selector)
        try:
            locator.first.wait_for(state="visible", timeout=timeout_ms)
            locator.first.fill(value)
            return True
        except PlaywrightError:
            continue
    return False


def _submit_login_form(page, email: str, password: str) -> bool:
    page.wait_for_timeout(3000)

    email_filled = _fill_first_visible(
        page,
        [
            "input[type='email']",
            "input[name='email']",
            "input[autocomplete='username']",
        ],
        email,
    )
    password_filled = _fill_first_visible(
        page,
        [
            "input[type='password']",
            "input[name='password']",
            "input[autocomplete='current-password']",
        ],
        password,
    )

    if not (email_filled and password_filled):
        return False

    for selector in [
        "button[type='submit']",
        "button:has-text('Login')",
        "button:has-text('Log in')",
        "button:has-text('Sign in')",
        "button:has-text('Continue')",
    ]:
        locator = page.locator(selector)
        try:
            locator.first.wait_for(state="visible", timeout=5000)
            locator.first.click()
            page.wait_for_timeout(3000)
            return True
        except PlaywrightError:
            continue

    return False


def _stable_external_id(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"instahyre-{digest}"


def _extract_opportunities_from_page(page, opportunities_url: str) -> List[OpportunityIn]:
    card_rows = page.evaluate(
        """
        () => {
          const out = [];
          for (const el of document.querySelectorAll("a.row.text-link")) {
            const text = (el.innerText || "").trim();
            if (!text) continue;
            const lines = text.split("\\n").map(x => x.trim()).filter(Boolean);
            if (lines.length === 0) continue;
            out.push(lines);
          }
          return out;
        }
        """
    )

    opportunities: List[OpportunityIn] = []
    for idx, lines in enumerate(card_rows):
        heading = lines[0]
        parts = heading.split(" - ", 1)
        company = parts[0].strip() if parts else "Instahyre"
        title = parts[1].strip() if len(parts) > 1 else heading.strip()
        key = f"{company}|{title}|{idx}"
        opportunities.append(
            OpportunityIn(
                external_id=_stable_external_id(key),
                title=title,
                company=company,
                location=lines[1] if len(lines) > 1 else None,
                salary=None,
                apply_url=opportunities_url,
            )
        )

    if opportunities:
        return opportunities

    links = page.evaluate(
        """
        () => {
          const out = new Set();
          for (const el of document.querySelectorAll("a[href], [data-href], [data-url]")) {
            const href = el.getAttribute("href") || el.getAttribute("data-href") || el.getAttribute("data-url");
            if (href) out.add(href);
          }
          return Array.from(out);
        }
        """
    )
    urls = extract_job_links_from_html(settings.instahyre_base_url, links)

    for idx, url in enumerate(urls):
        opportunities.append(
            OpportunityIn(
                external_id=_stable_external_id(url),
                title=f"Instahyre Opportunity #{idx + 1}",
                company="Instahyre",
                location=None,
                salary=None,
                apply_url=url,
            )
        )
    return opportunities


def crawl_instahyre_opportunities(profile: Dict[str, str], manual_login: bool = False) -> CrawlResult:
    user_data_dir = profile.get("instahyre_user_data_dir", "~/.autoapply-instahyre-profile")
    opportunities_url = profile.get("instahyre_opportunities_url", DEFAULT_OPPORTUNITIES_URL)
    login_url = profile.get("instahyre_login_url", DEFAULT_LOGIN_URL)
    email = profile.get("instahyre_email", "")
    password = profile.get("instahyre_password", "")

    profile_dir = str(Path(user_data_dir).expanduser())

    with sync_playwright() as p:
        with profile_lock(profile_dir):
            context = launch_persistent_context(
                p,
                profile_dir=profile_dir,
                headless=False if manual_login else settings.headless,
                channel=settings.browser_channel or None,
            )
            page = context.new_page()

            try:
                page.goto(opportunities_url, timeout=45000, wait_until="domcontentloaded")
                if ("/login" in page.url) or page.locator("input[type='password']").count() > 0:
                    if manual_login:
                        page.goto(login_url, timeout=45000, wait_until="domcontentloaded")
                        _submit_login_form(page, email, password)
                        # Give the user time to complete interactive login/2FA once.
                        for _ in range(90):
                            page.wait_for_timeout(2000)
                            try:
                                current_url = page.url
                                password_fields = page.locator("input[type='password']").count()
                                if ("/login" not in current_url) and password_fields == 0:
                                    break
                            except PlaywrightError:
                                # Page is navigating; keep polling until it settles.
                                continue
                        page.goto(opportunities_url, timeout=45000, wait_until="domcontentloaded")
                    elif email and password:
                        page.goto(login_url, timeout=45000, wait_until="domcontentloaded")
                        _submit_login_form(page, email, password)
                        page.goto(opportunities_url, timeout=45000, wait_until="domcontentloaded")
                    else:
                        return CrawlResult(
                            opportunities=[],
                            requires_login=True,
                            details="Instahyre login required. Provide credentials or run manual login mode.",
                        )

                if ("/login" in page.url) or page.locator("input[type='password']").count() > 0:
                    return CrawlResult(
                        opportunities=[],
                        requires_login=True,
                        details="Unable to establish logged-in session. Run with manual_login=true once.",
                    )

                for _ in range(5):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(800)

                opportunities = _extract_opportunities_from_page(page, opportunities_url)
                return CrawlResult(
                    opportunities=opportunities,
                    requires_login=False,
                    details=f"Found {len(opportunities)} opportunities",
                )
            finally:
                context.close()
