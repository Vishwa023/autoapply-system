from __future__ import annotations

from app.config import settings


def load_runtime_profile() -> dict[str, str]:
    profile = {
        "full_name": settings.full_name,
        "email": settings.email,
        "phone": settings.phone,
        "resume_path": settings.resume_path,
        "instahyre_user_data_dir": settings.instahyre_user_data_dir,
        "instahyre_email": settings.instahyre_email,
        "instahyre_password": settings.instahyre_password,
        "instahyre_opportunities_url": settings.instahyre_opportunities_url,
        "instahyre_login_url": settings.instahyre_login_url,
    }
    return {key: value for key, value in profile.items() if value}
