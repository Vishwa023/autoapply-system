from __future__ import annotations

from pathlib import Path

from fastapi import Cookie, FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token

from app.web.automation_manager import AutomationManager, build_runtime_profile_for_user
from app.web.database import (
    create_session,
    create_user,
    delete_expired_sessions,
    delete_session,
    get_profile,
    get_session,
    get_user_bundle,
    get_user_by_email,
    get_user_by_google_sub,
    init_db,
    update_resume_path,
    update_user_google_sub,
    upsert_profile,
    utcnow,
)
from app.web.schemas import (
    AutomationStatusOut,
    GoogleLoginRequest,
    LoginRequest,
    ProfileOut,
    ProfileRequest,
    SessionOut,
    SignupRequest,
    UserOut,
)
from app.web.security import hash_password, issue_session_token, session_expiry, verify_password
from app.web.settings import (
    FRONTEND_DIST_DIR,
    FRONTEND_ORIGINS,
    GOOGLE_CLIENT_ID,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    WEB_DATA_DIR,
)


def _profile_to_output(profile: dict[str, str]) -> ProfileOut:
    return ProfileOut(
        full_name=profile["full_name"],
        contact_email=profile["contact_email"],
        phone=profile["phone"],
        instahyre_email=profile["instahyre_email"],
        has_instahyre_password=bool(profile["instahyre_password"]),
        resume_uploaded=bool(profile["resume_path"]),
        resume_path=profile["resume_path"],
    )


def _bundle_to_session(bundle: dict[str, dict[str, str]]) -> SessionOut:
    user = bundle["user"]
    profile = bundle["profile"]
    return SessionOut(
        user=UserOut(id=user["id"], email=user["email"]),
        profile=_profile_to_output(profile),
        google_login_enabled=bool(GOOGLE_CLIENT_ID),
    )


def _require_session(session_token: str | None) -> dict[str, str]:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    delete_expired_sessions(utcnow())
    session = get_session(session_token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return session


def _set_session_cookie(response: Response, *, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


init_db()
WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
automation_manager = AutomationManager(profile_loader=build_runtime_profile_for_user)
app = FastAPI(title="Instahyre Auto Apply Web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/session", response_model=SessionOut)
def session(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> SessionOut:
    active_session = _require_session(session_token)
    return _bundle_to_session(get_user_bundle(active_session["user_id"]))


@app.post("/api/auth/signup", response_model=SessionOut)
def signup(payload: SignupRequest, response: Response) -> SessionOut:
    if get_user_by_email(payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    user = create_user(payload.email, password_hash=hash_password(payload.password))
    token = issue_session_token()
    create_session(token, user["id"], session_expiry(SESSION_MAX_AGE_SECONDS))
    _set_session_cookie(response, token=token)
    return _bundle_to_session(get_user_bundle(user["id"]))


@app.post("/api/auth/login", response_model=SessionOut)
def login(payload: LoginRequest, response: Response) -> SessionOut:
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user.get("password_hash")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = issue_session_token()
    create_session(token, user["id"], session_expiry(SESSION_MAX_AGE_SECONDS))
    _set_session_cookie(response, token=token)
    return _bundle_to_session(get_user_bundle(user["id"]))


@app.post("/api/auth/google", response_model=SessionOut)
def google_login(payload: GoogleLoginRequest, response: Response) -> SessionOut:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google login is not configured")

    try:
        token_info = google_id_token.verify_oauth2_token(payload.credential, GoogleRequest(), GOOGLE_CLIENT_ID)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Google login failed: {exc}") from exc

    email = token_info.get("email")
    google_sub = token_info.get("sub")
    if not email or not google_sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account is missing email")

    user = get_user_by_google_sub(google_sub)
    if not user:
        user = get_user_by_email(email)
        if user:
            update_user_google_sub(user["id"], google_sub)
            user = get_user_bundle(user["id"])["user"]
        else:
            user = create_user(email, google_sub=google_sub)

    token = issue_session_token()
    create_session(token, user["id"], session_expiry(SESSION_MAX_AGE_SECONDS))
    _set_session_cookie(response, token=token)
    return _bundle_to_session(get_user_bundle(user["id"]))


@app.post("/api/auth/logout")
def logout(response: Response, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> dict[str, bool]:
    if session_token:
        delete_session(session_token)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@app.put("/api/profile", response_model=SessionOut)
def save_profile(
    payload: ProfileRequest,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> SessionOut:
    active_session = _require_session(session_token)
    upsert_profile(
        active_session["user_id"],
        full_name=payload.full_name,
        contact_email=payload.contact_email,
        phone=payload.phone,
        instahyre_email=payload.instahyre_email,
        instahyre_password=payload.instahyre_password,
    )
    return _bundle_to_session(get_user_bundle(active_session["user_id"]))


@app.post("/api/profile/resume", response_model=SessionOut)
async def upload_resume(
    file: UploadFile = File(...),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> SessionOut:
    active_session = _require_session(session_token)
    suffix = Path(file.filename or "resume.pdf").suffix.lower() or ".pdf"
    if suffix not in {".pdf", ".doc", ".docx"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a PDF, DOC, or DOCX resume")
    user_root = WEB_DATA_DIR / "users" / str(active_session["user_id"])
    user_root.mkdir(parents=True, exist_ok=True)
    resume_path = user_root / f"resume{suffix}"
    contents = await file.read()
    resume_path.write_bytes(contents)
    update_resume_path(active_session["user_id"], str(resume_path))
    return _bundle_to_session(get_user_bundle(active_session["user_id"]))


@app.get("/api/automation/status", response_model=AutomationStatusOut)
def automation_status(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> AutomationStatusOut:
    _require_session(session_token)
    return AutomationStatusOut(**automation_manager.status())


@app.post("/api/automation/start", response_model=AutomationStatusOut)
def automation_start(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> AutomationStatusOut:
    active_session = _require_session(session_token)
    profile = get_profile(active_session["user_id"])
    if not profile["full_name"] or not profile["contact_email"] or not profile["phone"] or not profile["resume_path"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete your profile and upload a resume before starting automation",
        )
    return AutomationStatusOut(**automation_manager.start(active_session["user_id"]))


@app.post("/api/automation/stop", response_model=AutomationStatusOut)
def automation_stop(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> AutomationStatusOut:
    _require_session(session_token)
    return AutomationStatusOut(**automation_manager.stop())


@app.get("/", include_in_schema=False)
def root() -> FileResponse | dict[str, str]:
    index_file = FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Frontend not built yet. Run npm install && npm run build inside ./frontend."}


if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
