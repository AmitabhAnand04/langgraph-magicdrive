import os
import json
import pprint
import re
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

class InputData(BaseModel):
    thread_id: str
    source_id: str

@app.post("/api/sendchat")
def send_chat_history_to_chatwoot(data: InputData):
    try:
        snapshot = react_graph.get_state({'configurable': {'thread_id': data.thread_id}})
        messages = snapshot.values.get("messages", [])

        if not messages:
            return {"message": "No history to send in the given thread_id."}

        # Format messages
        formatted = []
        for m in messages:
            role = "unknown"
            content = ""

            if m.__class__.__name__ == "HumanMessage":
                role = "user"
                content = m.content
            elif m.__class__.__name__ == "AIMessage":
                role = "assistant"
                content = m.content or ""
                function_call = m.additional_kwargs.get("function_call")
                if function_call:
                    tool_name = function_call.get("name")
                    arguments = function_call.get("arguments")
                    content += f"\n\n[Tool Call → `{tool_name}` with args: {arguments}]"
            elif m.__class__.__name__ == "ToolMessage":
                role = "tool"
                content = m.content

            formatted.append(f"{role}: {content}")

        final_string = "\n\n".join(formatted)

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
                if src_id == data.source_id:
                    conversation_id = msg.get("conversation_id")
                    break

        if not conversation_id:
            return {"message": "No matching source_id found."}

        # Step 2: Post the formatted chat history to Chatwoot
        message_url = MESSAGES_URL_TEMPLATE.format(conversation_id=conversation_id)
        message_payload = json.dumps({
            "content": final_string,
            "private": True
        })
        message_headers = {
            'api_access_token': CHATWOOT_API_TOKEN,
            'Content-Type': 'application/json'
        }

        msg_response = requests.post(message_url, headers=message_headers, data=message_payload)
        return {
            "thread_id": data.thread_id,
            "conversation_id": conversation_id,
            "message_sent": final_string,
            "message":"Messages sent to chatwoot!!"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)