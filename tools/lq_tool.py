import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_lq_response(prompt: str):
    # Get base URL from environment variable
    base_url = os.getenv("LQ_TOOL_BASE_URL")
    if not base_url:
        raise ValueError("Environment variable 'KB_API_BASE_URL' is not set.")

    # Full URL with route
    endpoint = f"{base_url.rstrip('/')}/kb"

    # Query parameters
    params = {"prompt": prompt}

    try:
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

# res = get_lq_response(prompt="Why isn’t my broker data showing up after emailing the file?")
# print(res)