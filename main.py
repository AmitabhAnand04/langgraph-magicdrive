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

from fastapi import FastAPI, Query
from langchain_core.messages import HumanMessage, BaseMessage, ToolMessage
from graph import react_graph
from uuid import uuid4

app = FastAPI()

@app.get("/query")
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
            last_message: BaseMessage = response["messages"][-1]
            # return {"result": last_message,"message_state_length": number_of_messages, "thread_id": current_thread_id}
            response_data = {
            "result": last_message, # Note: Returning the full message object here as in your original code
            "message_state_length": number_of_messages,
            "all_messages_in_message_state": response["messages"],
            "thread_id": current_thread_id # Return the thread_id used
        }

        # Add the summary to the response if it exists and is not None
        if isinstance(response, dict) and response.get("summary") is not None:
             response_data["summary"] = response["summary"]
             # Optional: print(f"Summary found and added to response.") # For debugging

        # Return the complete response dictionary
        return response_data
    except Exception as e:
        return {"error": str(e)}

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