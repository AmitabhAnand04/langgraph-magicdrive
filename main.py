import os
import json
import pprint
import re
from typing import List
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, BaseMessage, ToolMessage
from openai import BaseModel
import requests
from azure.storage.blob import ContainerClient
from graph import react_graph
from uuid import uuid4
from dotenv import load_dotenv
from tools.feature_query_tool.feature_query_tool import build_index_fq
from tools.issue_resolution_matching_tool.issue_resolution_matching_tool import build_index, delete_blob_from_azure

load_dotenv()
def langsmith_config():
    os.environ['LANGSMITH_TRACING']='true'
    os.environ['LANGSMITH_API_KEY']=os.getenv("LANGSMITH_API_KEY")
    os.environ['LANGSMITH_PROJECT']=os.getenv("LANGSMITH_PROJECT")


langsmith_config()

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

ISSUE_UPLOADS_BLOB_PREFIX = "issue_resolution_data_uploads/"
FEATURE_UPLOADS_BLOB_PREFIX = "feature_query_data_uploads/"
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB max
ALLOWED_EXTENSIONS = {".csv", ".docx"}

# Azure Blob Container client (adjust your connection string and container name)
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

container_client = ContainerClient.from_connection_string(AZURE_CONNECTION_STRING, container_name=CONTAINER_NAME)

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
            
            response_data = {
                "result": content,
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
    


def secure_filename(filename: str) -> str:
    filename = filename.strip().replace(" ", "_")
    filename = re.sub(r'[^A-Za-z0-9_.-]', '', filename)
    return filename


@app.post("/upload/issue")
async def upload_issue_file(file: UploadFile = File()):
    filename = secure_filename(file.filename)
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file extension. Allowed: .csv")

    contents = await file.read()
    if len(contents) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=400, detail="File too large. Max size is 100MB.")

    blob_path = ISSUE_UPLOADS_BLOB_PREFIX + filename

    try:
        blob_client = container_client.get_blob_client(blob_path)
        blob_client.upload_blob(contents, overwrite=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file to Azure Blob Storage: {str(e)}")

    try:
        build_index(container_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild index after upload: {str(e)}")

    return {"message": f"Uploaded '{filename}' for issue and reindexed successfully."}

@app.post("/upload/feature")
async def upload_feature_file(file: UploadFile = File()):
    filename = secure_filename(file.filename)
    if not filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Invalid file extension. Allowed: .docx")

    contents = await file.read()
    if len(contents) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=400, detail="File too large. Max size is 100MB.")

    blob_path = FEATURE_UPLOADS_BLOB_PREFIX + filename

    try:
        blob_client = container_client.get_blob_client(blob_path)
        blob_client.upload_blob(contents, overwrite=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file to Azure Blob Storage: {str(e)}")

    try:
        build_index_fq(container_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild index after upload: {str(e)}")

    return {"message": f"Uploaded '{filename}' for feature and reindexed successfully."}

@app.delete("/delete/issue")
async def delete_issue_file(filename: str = Query()):
    filename = secure_filename(filename)
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file extension. Allowed: .csv")

    full_blob_name = ISSUE_UPLOADS_BLOB_PREFIX + filename

    try:
        blob_client = container_client.get_blob_client(full_blob_name)
        blob_client.delete_blob()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete blob: {str(e)}")

    try:
        build_index(container_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild index after deletion: {str(e)}")

    return {"message": f"Deleted '{filename}' for issue and reindexed successfully."}

@app.delete("/delete/feature")
async def delete_feature_file(filename: str = Query()):
    filename = secure_filename(filename)
    if not filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Invalid file extension. Allowed: .docx")

    full_blob_name = FEATURE_UPLOADS_BLOB_PREFIX + filename

    try:
        blob_client = container_client.get_blob_client(full_blob_name)
        blob_client.delete_blob()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete blob: {str(e)}")

    try:
        build_index_fq(container_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild index after deletion: {str(e)}")

    return {"message": f"Deleted '{filename}' for feature and reindexed successfully."}

@app.post("/reindex/issue")
async def reindex_issue():
    try:
        result = build_index(container_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild issue index: {str(e)}")

    if not result:
        return {"message": "No documents found for issue in Azure Blob Storage."}
    return {"message": "Issue index rebuilt successfully."}

@app.post("/reindex/feature")
async def reindex_feature():
    try:
        result = build_index_fq(container_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild feature index: {str(e)}")

    if not result:
        return {"message": "No documents found for feature in Azure Blob Storage."}
    return {"message": "Feature index rebuilt successfully."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)