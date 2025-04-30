import os
import requests
from dotenv import load_dotenv

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

def create_zoho_ticket(subject: str):
    load_dotenv()

    department_id = os.getenv("ZOHO_DEPARTMENT_ID")
    contact_id = os.getenv("ZOHO_CONTACT_ID")
    org_id = os.getenv("ZOHO_ORG_ID")

    if not all([department_id, contact_id, org_id]):
        raise ValueError("Missing env variables")

    url = "https://desk.zoho.in/api/v1/tickets"

    def make_request(token):
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "orgId": org_id,
            "Content-Type": "application/json"
        }

        payload = {
            "subject": subject,
            "departmentId": department_id,
            "contactId": contact_id
        }

        return requests.post(url, headers=headers, json=payload)

    # First attempt
    token = get_zoho_access_token()
    response = make_request(token)

    # If unauthorized, refresh token and retry once
    if response.status_code == 401 and "INVALID_OAUTH" in response.text:
        print("Token Invalid... Creating New!!")
        token = get_zoho_access_token(force_refresh=True)
        response = make_request(token)

    response.raise_for_status()

    ticket_data = response.json()
    ticket_id = ticket_data.get("id")
    ticket_number = ticket_data.get("ticketNumber")

    return {
        "message": f"Ticket created with ticket id {ticket_id}, and ticket number {ticket_number}"
    }


# print(create_zoho_ticket(subject="Test Subject token"))