import os
import requests
from dotenv import load_dotenv

from utils.zoho_utils import get_zoho_access_token

def create_zoho_ticket(subject: str, email: str):
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
            "contactId": contact_id,
            "email": email
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
        "message": f"Ticket created for email ID {email} with ticket ID {ticket_id} and ticket number {ticket_number}."
    }


# print(create_zoho_ticket(subject="Test Subject token"))