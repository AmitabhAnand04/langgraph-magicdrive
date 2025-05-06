# from fastapi import FastAPI
# from pydantic import BaseModel
# from langchain_core.messages import HumanMessage
# from graph import react_graph

# app = FastAPI()

# class QueryInput(BaseModel):
#     user_query: str

# @app.post("/query")
# def query(request: QueryInput):
#     try:
#         human_message = HumanMessage(content=request.user_query)
#         response = react_graph.invoke({"messages": [human_message]})
#         return response  # Direct return — no serialization logic
#     except Exception as e:
#         return {"error": str(e)}
    
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

import os
import json
import pprint
import re
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage, BaseMessage, ToolMessage
from openai import BaseModel
import requests
from graph import react_graph
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()


# Constants from environment
CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")

# Base URLs
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_BASE_URL")
CONVERSATIONS_URL = f"{CHATWOOT_BASE_URL}/conversations"
MESSAGES_URL_TEMPLATE = f"{CHATWOOT_BASE_URL}/conversations/{{conversation_id}}/messages"

def safe_parse_content(content: str):
    """
    Handles:
    - Markdown-wrapped JSON containing a nested stringified JSON
    - Properly parses fields like 'sql_result' which might be a stringified list of dicts
    """
    try:
        # Match the outer markdown-wrapped JSON block
        match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if match:
            outer_json_str = match.group(1)
            outer_json = json.loads(outer_json_str)

            if (
                isinstance(outer_json, dict) 
                and "lq_tool_response" in outer_json 
                and isinstance(outer_json["lq_tool_response"], dict)
            ):
                inner_json_str = outer_json["lq_tool_response"].get("content", "")
                parsed = json.loads(inner_json_str)

                # Fix improperly stringified JSON inside specific fields
                if isinstance(parsed.get("sql_result"), str):
                    try:
                        parsed["sql_result"] = json.loads(parsed["sql_result"])
                    except json.JSONDecodeError:
                        pass  # leave as string if not parseable

                if "explain_result" in parsed:
                    parsed["content"] = parsed.pop("explain_result")
                return parsed
            
    except Exception as e:
        print("Exception occurred:", e)

    return content

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
            # return {"result": last_message,"message_state_length": number_of_messages, "thread_id": current_thread_id}
        #     response_data = {
        #     "result": last_message, # Note: Returning the full message object here as in your original code
        #     "message_state_length": number_of_messages,
        #     "all_messages_in_message_state": response["messages"],
        #     "thread_id": current_thread_id # Return the thread_id used
        # }

        # Add the summary to the response if it exists and is not None
        if isinstance(response, dict) and response.get("summary") is not None:
             response_data["summary"] = response["summary"]
             # Optional: print(f"Summary found and added to response.") # For debugging

        # Return the complete response dictionary
        return response_data
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/get-chat-history/{thread_id}")
async def get_chat_history(thread_id: str):
    try:
        snapshot = react_graph.get_state({'configurable': {'thread_id': thread_id}})
        messages = snapshot.values.get("messages", [])
        # return messages
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

                # If it's a tool call, add that info
                function_call = m.additional_kwargs.get("function_call")
                if function_call:
                    tool_name = function_call.get("name")
                    arguments = function_call.get("arguments")
                    content += f"\n\n[Tool Call → `{tool_name}` with args: {arguments}]"

            elif m.__class__.__name__ == "ToolMessage":
                role = "tool"
                content = m.content

            formatted.append({"role": role, "content": content})

        return {"thread_id": thread_id, "messages": formatted}

    except Exception as e:
        print("ERROR in get-chat-history:", str(e))
        return {"error": str(e), "thread_id": thread_id}

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
# @app.get("/getmessages")
# def get_messages_endpoint():
#     """
#     FastAPI endpoint to retrieve and return pretty-printed messages
#     from the application state.
#     """
#     # Call your function with the current application state
#     # pretty_messages_string = get_simple_pretty_printed_messages()

#     # Return the string output
#     # FastAPI automatically handles returning strings as plain text responses
#     return msglen()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)