"""
One-time Google OAuth setup script.
Run this to authenticate with Google Calendar and generate token.json.

Usage:
    python setup_google_auth.py
"""

import os
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on path
project_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_dir))

from dotenv import load_dotenv
load_dotenv(project_dir / ".env")

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar"]

CREDENTIALS_FILE = str(project_dir / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
TOKEN_FILE = str(project_dir / os.getenv("GOOGLE_TOKEN_FILE", "token.json"))


def main():
    print("=" * 60)
    print("  Google Calendar OAuth Setup")
    print("=" * 60)
    print()

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"[ERROR] credentials.json not found at: {CREDENTIALS_FILE}")
        print("   Download it from Google Cloud Console:")
        print("   https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    print(f"  Credentials file: {CREDENTIALS_FILE}")
    print(f"  Token file:       {TOKEN_FILE}")
    print()

    creds = None

    # Check if token already exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            print("[OK] token.json already exists and is valid!")
            print("     You're already authenticated with Google Calendar.")
            return
        elif creds and creds.expired and creds.refresh_token:
            print("[INFO] Token expired, refreshing...")
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
                print("[OK] Token refreshed successfully!")
                return
            except Exception as e:
                print(f"[ERROR] Token refresh failed: {e}")
                print("        Will re-authenticate...")
                creds = None

    # Run OAuth flow
    print("[INFO] Opening browser for Google sign-in...")
    print("       Please sign in and grant calendar access.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print()
    print("[OK] Authentication successful!")
    print(f"     Token saved to: {TOKEN_FILE}")
    print()
    print("     You can now run the meeting planner with real Google Calendar.")
    print("     Make sure MOCK_CALENDAR=false in your .env file.")


if __name__ == "__main__":
    main()
