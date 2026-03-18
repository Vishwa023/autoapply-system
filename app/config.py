from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    headless: bool = False
    browser_channel: str = ""
    instahyre_base_url: str = "https://www.instahyre.com"
    instahyre_opportunities_url: str = "https://www.instahyre.com/candidate/opportunities/?matching=true"
    instahyre_login_url: str = "https://www.instahyre.com/login/"
    instahyre_user_data_dir: str = "/data/browser-profile"
    instahyre_email: str = ""
    instahyre_password: str = ""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    resume_path: str = ""

    apply_poll_seconds: int = 300
    max_apply_attempts: int = 2
    state_path: str = "/data/state.json"
    screenshots_dir: str = "/data/screenshots"


settings = Settings()
