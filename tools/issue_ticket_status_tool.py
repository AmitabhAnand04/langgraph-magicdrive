import os
import requests

from utils.zoho_utils import get_zoho_access_token

def get_ticket_status(ticket_id: str, email: str) -> str:
    """
    Fetches the status of a Zoho Desk ticket using its ID and validates the email.

    Args:
        ticket_id (str): The Zoho Desk ticket ID.
        email (str): Email ID to validate against the ticket.

    Returns:
        str: Ticket status message or an error message if the email doesn't match.

    Raises:
        ValueError: If required environment variable is missing.
        HTTPError: If the API request fails.
    """
    org_id = os.getenv("ZOHO_ORG_ID")

    if not org_id:
        raise ValueError("Missing required environment variable: ZOHO_ORG_ID")

    url = f"https://desk.zoho.in/api/v1/tickets/{ticket_id}?include=contacts,products,assignee,departments,team"

    def make_request(token):
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "orgId": org_id,
            "Content-Type": "application/json"
        }
        return requests.get(url, headers=headers)

    # First attempt
    token = get_zoho_access_token()
    response = make_request(token)

    # Retry once if token is invalid
    if response.status_code == 401 and "INVALID_OAUTH" in response.text:
        print("Token Invalid... Creating New!!")
        token = get_zoho_access_token(force_refresh=True)
        response = make_request(token)

    response.raise_for_status()

    data = response.json()

    # Compare provided email with email from the response
    ticket_email = data.get("email", "").strip().lower()
    # print("Email in the request: "+email)
    # print("Email in the response: "+ticket_email)

    if email.strip().lower() != ticket_email:
        return (
            "The email address you provided is not associated with the ticket you are trying to access. "
            "Please use the correct email address linked to the ticket or create a new ticket using your email."
        )

    # If email matches, return ticket status
    subject = data.get("subject", "No subject provided")
    status_type = data.get("statusType", "Unknown")

    return (
        f"The current status of your ticket regarding '{subject}' is: **{status_type}**."
    )
