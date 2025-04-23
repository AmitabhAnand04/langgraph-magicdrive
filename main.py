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

app = FastAPI()

@app.get("/query")
def query(user_query: str = Query(...)):
    try:
        human_message = HumanMessage(content=user_query)
        response = react_graph.invoke({"messages": [human_message]})
        # Extract the content from the last message
        if response and response.get("messages"):
            last_message: BaseMessage = response["messages"][-1]
            return {"result": last_message}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)