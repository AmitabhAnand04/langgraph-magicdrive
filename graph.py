import json
import os
import sqlite3
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage, RemoveMessage
# from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.prebuilt import ToolNode
from tools.kb_tools.kb_tool import chat_engine
from tools.lq_tools.lq_tool import nl_sql_nl_gemini
from tools.tkt_tool import create_zoho_ticket
from prompts import AGENT_PROMPT

llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

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
def kb_tool(query: str) -> dict:
    """Answer for knowledge-based questions."""
    result =  chat_engine.chat(query).response
    return {
        "tool_name": "kb_tool",
        "content": result
    }

def lq_tool(query: str) -> dict:
    """answer for database query related questions.

    Args:
        query: user query
    """
    # return f"[LQ Tool] SQL executed for: {query}"
    result =  nl_sql_nl_gemini (query)
    return {
        "tool_name": "lq_tool",
        "content": result
    }

def tkt_tool(query: str) -> dict:
    """Answer for knowledge-based questions."""
    result =  create_zoho_ticket(query)
    return {
        "tool_name": "tkt_tool",
        "content": result
    }

tools = [kb_tool, lq_tool, tkt_tool]
llm_with_tools = llm.bind_tools(tools)

class State(MessagesState):
    summary: str

# System message
# sys_msg = SystemMessage(content="You are a helpful assistant whic will decide which tool to use for the user provided query.")
sys_msg = SystemMessage(
    content= AGENT_PROMPT
)
# Node
def assistant(state: State):
    print("Assistant node started!!")
    # for m in state['messages']:
    #     m.pretty_print()
    # Get summary if it exists
    summary = state.get("summary", "")

    # If there is summary, then we add it
    if summary:
        
        # Add summary to system message
        summary_message = f"Summary of conversation earlier: {summary}"

        # Append summary to any newer messages
        messages = [sys_msg] + [SystemMessage(content=summary_message)] + state["messages"]
    
    else:
        messages = [sys_msg] + state["messages"]
    # print(messages)
    for m in messages:
        m.pretty_print()
    # return {"messages": [llm_with_tools.invoke(messages)]}
    return {"messages": state["messages"] + [llm_with_tools.invoke(messages)]}


# def summarize_conversation(state: State):
#     print("Summerizing node started!!")
#     # First, we get any existing summary
#     summary = state.get("summary", "")

#     # Create our summarization prompt 
#     if summary:
        
#         # A summary already exists
#         summary_message = (
#             f"This is summary of the conversation to date: {summary}\n\n"
#             "Extend the summary by taking into account the new messages above:"
#         )
        
#     else:
#         summary_message = "Create a summary of the conversation above:"

#     # Only summarize if there's enough actual content
#     if len(state["messages"]) >= 1:
#         messages = state["messages"] + [HumanMessage(content=summary_message)]
#         response = llm.invoke(messages)

#         recent_messages = state["messages"][-actual_conv_len:]
#         delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-actual_conv_len]]

#         return {
#             "summary": response.content,
#             "messages": delete_messages + recent_messages
#         }
#     else:
#         print("No messages to summarize")
#         return {
#             "summary": summary,  # keep the old one
#             "messages": state["messages"]  # do not change anything
#         }


#     # # Add prompt to our history
#     # messages = state["messages"] + [HumanMessage(content=summary_message)]
#     # response = llm.invoke(messages)
    
#     # # # Delete all but the 2 most recent messages
#     # # delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-4]]
#     # # return {"summary": response.content, "messages": delete_messages}
#     # # Keep last N messages (actual conversation), remove older ones
#     # recent_messages = state["messages"][-actual_conv_len:]
#     # delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-actual_conv_len]]

#     # return {
#     #     "summary": response.content,
#     #     "messages": delete_messages + recent_messages
#     # }

def summarize_conversation(state: State):
    print("Summarizing node started!!")

    # Fetch existing summary if any
    summary = state.get("summary", "")

    # Build summarization prompt
    if summary:
        summary_message = (
            f"This is a summary of the conversation so far: {summary}\n\n"
            "Extend the summary by taking into account the new messages above:"
        )
    else:
        summary_message = "Create a summary of the conversation above:"

    # Filter out messages that don't have content (e.g., tool calls)
    valid_messages = [
        m for m in state.get("messages", [])
        if hasattr(m, "content") and m.content and m.content.strip()
    ]

    # Append the summarization prompt
    messages = valid_messages + [HumanMessage(content=summary_message)]

    # Call the LLM to get the updated summary
    response = llm.invoke(messages)

    # Decide how many messages to retain (actual_conv_len must be defined globally or passed)
    recent_messages = state["messages"][-actual_conv_len:]
    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-actual_conv_len]]

    return {
        "summary": response.content,
        "messages": delete_messages + recent_messages
    }

# Determine whether to end or summarize the conversation
def should_continue(state: State):
    
    """Return the next node to execute."""
    
    messages = state["messages"]
    
    # If there are more than six messages, then we summarize the conversation
    if len(messages) > actual_conv_len:
        return "summarize_conversation"
    
    # Otherwise we can just end
    return END

def tool_routing_condition(state: State) -> str:
    """Route based on tool_name in tool output."""
    messages = state.get("messages", [])
    if not messages:
        return "assistant"  # fallback
    
    last_message = messages[-1]
    tool_result = getattr(last_message, "content", "")

    if isinstance(tool_result, str):
        try:
            tool_result = json.loads(tool_result)
        except json.JSONDecodeError:
            pass  # leave as string if it's not valid JSON

    if isinstance(tool_result, dict):
        tool_name = tool_result.get("tool_name", "")
    else:
        tool_name = getattr(tool_result, "tool_name", "unknown")

    if tool_name == "lq_tool":
        return END
    return "assistant"

# Graph
builder = StateGraph(State)

# Define nodes: these do the work
builder.add_node("assistant", assistant)
builder.add_node("tools", ToolNode(tools))
builder.add_node(summarize_conversation)

# Define edges: these determine how the control flow moves
builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant",
    # If the latest message (result) from assistant is a tool call -> tools_condition routes to tools
    # If the latest message (result) from assistant is a not a tool call -> tools_condition routes to END
    tools_condition,
)
# builder.add_edge("tools", "assistant")
builder.add_conditional_edges("tools", tool_routing_condition)
builder.add_conditional_edges("assistant", should_continue)
builder.add_edge("summarize_conversation", END)
# builder.add_edge("tools", END)
# memory = MemorySaver()
memory = SqliteSaver(conn)
react_graph = builder.compile(checkpointer=memory)

# def msglen(state = messagestate) -> int:
#     """
#     Iterates through messages in the state and calls pretty_print() on each,
#     collecting the output. Assumes state['messages'] is a list of objects
#     with a pretty_print() method.

#     Args:
#         state: A dictionary expected to contain a 'messages' key with a list
#                of message objects, each having a pretty_print() method.

#     Returns:
#         A string containing the pretty-printed representation of all messages,
#         separated by newlines.
#     """
#     # pretty_output = []
#     # # Iterate directly as requested, assuming the structure is correct
#     # for m in state['messages']:
#     #     output = m.pretty_print()
#     #     pretty_output.append(output)

#     # Join the collected pretty-printed strings with a newline separator
#     # return "\n".join(pretty_output)
#     return len(state['messages'])
# sys_msg = SystemMessage(
#     content="""
# You are an AI assistant that **only decides which tool to use** for a given user query. 

# You MUST NOT answer the user's query yourself.

# You have access to the following tools:
# 1. `kb_tool`: Use when the user is asking for knowledge-based answers.
# 2. `lq_tool`: Use when the user is asking to retrieve data or perform operations on a database.

# Always respond with a tool call — even if the query seems simple.

# You will receive a sequence of messages:
# - `HumanMessage(content="...")`: This is a query from the user.
# - `ToolMessage(content="...")`: This is a response returned by a tool that was previously called.

# if there it toolmessage in the message then a tool has already been called and returned the answer. Your job is done; the assistant will use the tool's response to reply to the user.

# DO NOT respond directly to the user's query under any circumstance other that greetings. it there is greet from the user then don't respond with tool call and just greet back.

# Example 1:
# User: What is RAG in AI?
# → Call: kb_tool(query="What is RAG in AI?")

# Example 2:
# User: Show me the total claims filed last month
# → Call: lq_tool(query="Show me the total claims filed last month")

# Example 3:
# User: How do I file a claim?
# → Call: kb_tool(query="How do I file a claim?")

# Example 4:
# User: Give me the list of agents in California
# → Call: lq_tool(query="Give me the list of agents in California")
# """
# )

# print(sys_msg)