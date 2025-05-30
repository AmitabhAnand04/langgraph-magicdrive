import os
import json
import pprint
import re
from typing import List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, BaseMessage, ToolMessage
from openai import BaseModel
import requests
from graph import react_graph
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Add this section
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Or ["*"] for all origins (not recommended in prod)
    allow_credentials=True,
    allow_methods=["*"],  # Or ["POST", "GET", "OPTIONS"] for more control
    allow_headers=["*"],  # Or specify: ["Content-Type", "Authorization"]
)

def langsmith_config():
    os.environ['LANGSMITH_TRACING']='true'
    os.environ['LANGSMITH_API_KEY']=os.getenv("LANGSMITH_API_KEY")
    os.environ['LANGSMITH_PROJECT']=os.getenv("LANGSMITH_PROJECT")
# Constants from environment
CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")

# Base URLs
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_BASE_URL")
CONVERSATIONS_URL = f"{CHATWOOT_BASE_URL}/conversations"
MESSAGES_URL_TEMPLATE = f"{CHATWOOT_BASE_URL}/conversations/{{conversation_id}}/messages"

@app.get("/api/query")
def query(user_query: str = Query(...), thread_id: str | None = Query(None)):
    try:
        current_thread_id = thread_id or str(uuid4())
        human_message = HumanMessage(content=user_query)
        config = {"configurable": {"thread_id": current_thread_id}}
        response = react_graph.invoke({"messages": [human_message]}, config)
        number_of_messages = len(response['messages'])
        # Extract the content from the last message
        # for m in response['messages']:
        #     m.pretty_print()
        if response and response.get("messages"):
            messages = response.get("messages", [])  
            last_message = messages[-1]
            # logging.info(last_message)
            content = getattr(last_message, "content", "")
            # logging.info(content)
            # Check if content looks like a JSON string
            if isinstance(content, str):
                try:
                    # First decode the main content
                    tool_result = json.loads(content)

                    # Now decode the inner 'content' field if it's a string
                    if isinstance(tool_result.get("content"), str):
                        try:
                            tool_result["content"] = json.loads(tool_result["content"])

                            # Now decode the 'sql_result' if it's a string
                            if isinstance(tool_result["content"].get("sql_result"), str):
                                try:
                                    tool_result["content"]["sql_result"] = json.loads(
                                        tool_result["content"]["sql_result"]
                                    )
                                except json.JSONDecodeError:
                                    pass

                        except json.JSONDecodeError:
                            pass
                except json.JSONDecodeError:
                    tool_result = content

            response_data = {
                "result": tool_result,
                "message_state_length": number_of_messages,
                "all_messages_in_message_state": response["messages"],
                "thread_id": current_thread_id
            }

        # Add the summary to the response if it exists and is not None
        if isinstance(response, dict) and response.get("summary") is not None:
             response_data["summary"] = response["summary"]
             # Optional: print(f"Summary found and added to response.") # For debugging

        # Return the complete response dictionary
        return response_data
    except Exception as e:
        return {"error": str(e)}

class ChatEntry(BaseModel):
    user: str
    assistant: str

@app.post("/api/sendchat")
def send_chat_history_to_chatwoot(source_id: str = Query(...), body: List[ChatEntry] = []):
    try:
        # Step 1: Find matching conversation by source_id
        headers = {'api_access_token': CHATWOOT_API_TOKEN}
        response = requests.get(CONVERSATIONS_URL, headers=headers)
        response_data = response.json()

        conversation_id = None
        payloads = response_data.get("data", {}).get("payload", [])
        for item in payloads:
            msgs = item.get("messages", [])
            if msgs:
                msg = msgs[0]
                src_id = msg.get("conversation", {}).get("contact_inbox", {}).get("source_id")
                if src_id == source_id:
                    conversation_id = msg.get("conversation_id")
                    break

        if not conversation_id:
            return {"message": "No matching source_id found."}

        # Step 2: Post each message to Chatwoot individually
        message_url = MESSAGES_URL_TEMPLATE.format(conversation_id=conversation_id)
        message_headers = {
            'api_access_token': CHATWOOT_API_TOKEN,
            'Content-Type': 'application/json'
        }

        sent_messages = []

        for entry in body:
            # Send user message (incoming)
            if entry.user:
                user_payload = {
                    "content": "User:\n" + entry.user,
                    "message_type": "outgoing"
                }
                resp_user = requests.post(message_url, headers=message_headers, data=json.dumps(user_payload))
                sent_messages.append({
                    "type": "user",
                    "content": entry.user,
                    "status": resp_user.status_code,
                    "response": resp_user.json()
                })

            # Send assistant message (outgoing)
            if entry.assistant:
                assistant_payload = {
                    "content": "Assistant:\n" + entry.assistant,
                    "message_type": "outgoing"
                }
                resp_assistant = requests.post(message_url, headers=message_headers, data=json.dumps(assistant_payload))
                sent_messages.append({
                    "type": "assistant",
                    "content": entry.assistant,
                    "status": resp_assistant.status_code,
                    "response": resp_assistant.json()
                })

        return {
            "conversation_id": conversation_id,
            "message": "Messages sent to Chatwoot!",
            "details": sent_messages
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == "__main__":
    import uvicorn
    langsmith_config()
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)