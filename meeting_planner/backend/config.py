import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env FIRST before anything else
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    BASE_DIR: Path = BASE_DIR
    APP_NAME: str = "Meeting Planner"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # FastAPI
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # MCP
    MCP_SERVER_SCRIPT: str = str(BASE_DIR / "backend" / "mcp_server" / "server.py")
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "8001"))

    # Google Calendar
    GOOGLE_CREDENTIALS_FILE: str = str(BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
    GOOGLE_TOKEN_FILE: str = str(BASE_DIR / os.getenv("GOOGLE_TOKEN_FILE", "token.json"))
    GOOGLE_SCOPES: list = ["https://www.googleapis.com/auth/calendar"]
    MOCK_CALENDAR: bool = os.getenv("MOCK_CALENDAR", "true").lower() == "true"

    # HuggingFace — reads YOUR .env value
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")
    HF_MODEL: str = os.getenv("HF_MODEL", "zai-org/GLM-4.7-Flash")

    # Defaults
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")
    SENDER_EMAIL: str = os.getenv("SENDER_EMAIL", "")


settings = Settings()

# Debug print on import
if settings.DEBUG:
    print(f"[CONFIG] HF_MODEL    = {settings.HF_MODEL}")
    print(f"[CONFIG] SENDER_EMAIL= {settings.SENDER_EMAIL}")
    print(f"[CONFIG] MOCK_CAL    = {settings.MOCK_CALENDAR}")
    print(f"[CONFIG] CREDENTIALS = {settings.GOOGLE_CREDENTIALS_FILE}")