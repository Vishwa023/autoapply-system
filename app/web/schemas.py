from __future__ import annotations

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str


class ProfileRequest(BaseModel):
    full_name: str
    contact_email: str
    phone: str
    instahyre_email: str
    instahyre_password: str


class UserOut(BaseModel):
    id: int
    email: str


class ProfileOut(BaseModel):
    full_name: str
    contact_email: str
    phone: str
    instahyre_email: str
    has_instahyre_password: bool
    resume_uploaded: bool
    resume_path: str


class SessionOut(BaseModel):
    user: UserOut
    profile: ProfileOut
    google_login_enabled: bool


class AutomationStatusOut(BaseModel):
    running: bool
    user_id: int | None
    last_started_at: str | None
    last_finished_at: str | None
    last_error: str | None
    logs: list[str]
