"""One-time OAuth2 helper to obtain a Google refresh token.

Usage:
    uv run python -m app.scripts.google_auth

Prerequisites:
    1. Go to Google Cloud Console > APIs & Services > Credentials
    2. Click "Create Credentials" > "OAuth client ID"
    3. Application type: "Desktop app"
    4. Download the client ID and secret
    5. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env

This script opens a browser window for you to log in with your Google
account and grant read-only Drive access. It then prints the refresh
token to paste into your .env as GOOGLE_REFRESH_TOKEN.
"""

from __future__ import annotations

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def main() -> None:
    # Load settings to get client_id and client_secret
    from app.config import get_settings

    settings = get_settings()

    if not settings.google_client_id or not settings.google_client_secret:
        print(
            "\nError: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env\n"
            "\nSteps:\n"
            "  1. Go to https://console.cloud.google.com/apis/credentials\n"
            "  2. Create Credentials > OAuth client ID > Desktop app\n"
            "  3. Copy the Client ID and Client Secret into your .env\n"
            "  4. Re-run this script\n"
        )
        sys.exit(1)

    # Build the OAuth flow from client credentials
    client_config = {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    print("\nOpening browser for Google Drive authorization...\n")
    credentials = flow.run_local_server(port=0)

    print("\n" + "=" * 60)
    print("Success! Add this to your .env file:")
    print("=" * 60)
    print(f"\nGOOGLE_REFRESH_TOKEN={credentials.refresh_token}\n")
    print("=" * 60)
    print(
        "\nThis token gives read-only access to your Google Drive.\n"
        "It does not expire unless you revoke it.\n"
    )


if __name__ == "__main__":
    main()
