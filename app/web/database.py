from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.web.settings import DATABASE_PATH


def utcnow() -> str:
    return datetime.utcnow().isoformat()


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                google_sub TEXT UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL DEFAULT '',
                contact_email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                instahyre_email TEXT NOT NULL DEFAULT '',
                instahyre_password TEXT NOT NULL DEFAULT '',
                resume_path TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, google_sub, created_at FROM users WHERE email = ?",
            (_normalize_email(email),),
        ).fetchone()
    return _row_to_dict(row)


def get_user_by_google_sub(google_sub: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, google_sub, created_at FROM users WHERE google_sub = ?",
            (google_sub,),
        ).fetchone()
    return _row_to_dict(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, google_sub, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_dict(row)


def create_user(email: str, *, password_hash: str | None = None, google_sub: str | None = None) -> dict[str, Any]:
    now = utcnow()
    normalized_email = _normalize_email(email)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (email, password_hash, google_sub, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (normalized_email, password_hash, google_sub, now),
        )
        user_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO profiles (user_id, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (user_id, now, now),
        )
    user = get_user_by_id(user_id)
    if user is None:
        raise RuntimeError("Failed to create user")
    return user


def update_user_google_sub(user_id: int, google_sub: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET google_sub = ? WHERE id = ?", (google_sub, user_id))


def get_profile(user_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT user_id, full_name, contact_email, phone, instahyre_email,
                   instahyre_password, resume_path, created_at, updated_at
            FROM profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"profile missing for user {user_id}")
    return dict(row)


def upsert_profile(
    user_id: int,
    *,
    full_name: str,
    contact_email: str,
    phone: str,
    instahyre_email: str,
    instahyre_password: str,
    resume_path: str | None = None,
) -> dict[str, Any]:
    current = get_profile(user_id)
    now = utcnow()
    next_resume_path = current["resume_path"]
    if resume_path is not None:
        next_resume_path = resume_path
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE profiles
            SET full_name = ?, contact_email = ?, phone = ?, instahyre_email = ?,
                instahyre_password = ?, resume_path = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                full_name.strip(),
                _normalize_email(contact_email),
                phone.strip(),
                _normalize_email(instahyre_email),
                instahyre_password,
                next_resume_path,
                now,
                user_id,
            ),
        )
    return get_profile(user_id)


def update_resume_path(user_id: int, resume_path: str) -> dict[str, Any]:
    current = get_profile(user_id)
    return upsert_profile(
        user_id,
        full_name=current["full_name"],
        contact_email=current["contact_email"],
        phone=current["phone"],
        instahyre_email=current["instahyre_email"],
        instahyre_password=current["instahyre_password"],
        resume_path=resume_path,
    )


def create_session(token: str, user_id: int, expires_at: str) -> None:
    now = utcnow()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, user_id, now, expires_at),
        )


def get_session(token: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT token, user_id, created_at, expires_at
            FROM sessions
            WHERE token = ?
            """,
            (token,),
        ).fetchone()
    return _row_to_dict(row)


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def delete_expired_sessions(now: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))


def get_user_bundle(user_id: int) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    if user is None:
        raise KeyError(f"user {user_id} not found")
    return {"user": user, "profile": get_profile(user_id)}
