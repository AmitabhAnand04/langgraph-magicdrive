import os
from dotenv import load_dotenv
import requests

# Global cache for access token
_access_token_cache = {
    "token": None
}

def get_zoho_access_token(force_refresh=False):
    global _access_token_cache

    if _access_token_cache["token"] and not force_refresh:
        return _access_token_cache["token"]

    load_dotenv()

    refresh_token = os.getenv("ZOHO_REFRESH_TOKEN")
    client_id = os.getenv("ZOHO_CLIENT_ID")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET")

    if not all([refresh_token, client_id, client_secret]):
        raise ValueError("Missing one or more environment variables")

    token_url = "https://accounts.zoho.in/oauth/v2/token"
    params = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    }

    try:
        response = requests.post(token_url, params=params)
        response.raise_for_status()
        access_token = response.json().get("access_token")

        if not access_token:
            raise Exception("Access token not found in response")

        _access_token_cache["token"] = access_token
        return access_token

    except requests.RequestException as e:
        raise Exception(f"Error fetching access token: {e}")

