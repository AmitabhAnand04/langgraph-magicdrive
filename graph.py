import json
import os
import sqlite3
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.prebuilt import ToolNode
from tools.feature_query_tool.feature_query_tool import chat_engine, query_engine
from tools.issue_resolution_matching_tool import get_resolution_matching_result
from tools.issue_ticket_creation_tool import create_zoho_ticket
from tools.issue_ticket_status_tool  import get_ticket_status
from prompts import AGENT_PROMPT

llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")

# Define path depending on environment
if os.getenv("WEBSITE_SITE_NAME"):
    # Running on Azure Web App
    db_path = "/home/chat_memory.db"
else:
    # Running locally
    db_path = "chat_memory.db"
    
print(f"DB Path = {db_path}")
conn = sqlite3.connect(db_path, check_same_thread=False)

conv_len = 4
actual_conv_len = conv_len * 4
def feature_query_tool(query: str) -> dict:
    """Answer for knowledge-based questions."""
    # result =  chat_engine.chat(query).response
    result = query_engine.query(query).response
    return {
        "tool_name": "feature_query_tool",
        "content": result
    }

def issue_resolution_matching_tool(query: str) -> dict:
    """answers resolutions from previously created similar ticket.

    Args:
        query: user query
    """
    # return f"[LQ Tool] SQL executed for: {query}"
    result =  get_resolution_matching_result (query)
    return {
        "tool_name": "issue_resolution_matching_tool",
        "content": result
    }

def issue_ticket_creation_tool(query: str, email: str) -> dict:
    """For creating a new Zoho Desk ticket"""
    result =  create_zoho_ticket(query, email)
    return {
        "tool_name": "issue_ticket_creation_tool",
        "content": result
    }

def issue_ticket_status_tool(query: str, email: str) -> dict:
    """Fetches the status of a Zoho Desk ticket using its ID and validates the email."""
    result = get_ticket_status(query, email)
    return {
        "tool_name": "issue_ticket_status_tool",
        "content": result
    }

tools = [feature_query_tool, issue_resolution_matching_tool, issue_ticket_creation_tool, issue_ticket_status_tool]
llm_with_tools = llm.bind_tools(tools)

State = MessagesState

# System message
sys_msg = SystemMessage(
    content= AGENT_PROMPT
)
# Node
def assistant(state: State):
    # print("Assistant node started!!")
    messages = [sys_msg] + state["messages"]
    # print(state["messages"])
    # for m in messages:
    #     m.pretty_print()
    return {"messages": state["messages"] + [llm_with_tools.invoke(messages)]}

# Graph
builder = StateGraph(State)

# Define nodes: these do the work
builder.add_node("assistant", assistant)
builder.add_node("tools", ToolNode(tools))
# builder.add_node(summarize_conversation)

# Define edges: these determine how the control flow moves
builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant",
    # If the latest message (result) from assistant is a tool call -> tools_condition routes to tools
    # If the latest message (result) from assistant is a not a tool call -> tools_condition routes to END
    tools_condition,
)
# builder.add_edge("tools", "assistant")
builder.add_edge("tools", "assistant")
builder.add_edge("assistant", END)
memory = SqliteSaver(conn)
react_graph = builder.compile(checkpointer=memory)