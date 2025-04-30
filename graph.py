from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage, RemoveMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.prebuilt import ToolNode
from tools.kb_tools.kb_tool import chat_engine
from tools.lq_tools.lq_tool import nl_sql_nl_gemini
from tools.tkt_tool import create_zoho_ticket

llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")
conv_len = 4
actual_conv_len = conv_len * 4
def kb_tool(query: str) -> dict:
    """Answer for knowledge-based questions."""
    return chat_engine.chat(query).response

def lq_tool(query: str) -> dict:
    """answer for database query related questions.

    Args:
        query: user query
    """
    # return f"[LQ Tool] SQL executed for: {query}"
    return nl_sql_nl_gemini (query)

def tkt_tool(query: str) -> dict:
    """Answer for knowledge-based questions."""
    return create_zoho_ticket(query)

tools = [kb_tool, lq_tool, tkt_tool]
llm_with_tools = llm.bind_tools(tools)

class State(MessagesState):
    summary: str

# System message
# sys_msg = SystemMessage(content="You are a helpful assistant whic will decide which tool to use for the user provided query.")
sys_msg = SystemMessage(
    content="""
You are an AI assistant that decides which tool to use for an initial user query and then uses the tool's response to answer the user.

You have access to the following tools:

kb_tool: Use when the user is asking for knowledge-based answers.
lq_tool: Use when the user is asking to retrieve data or perform operations on a database.
tkt_tool: Use when the user is asking to create ticket or log for any bug or help. (use the appropriate subject as query for the tool call from complete conversation)

When you receive an initial user query:

Determine the most appropriate tool to use.
Respond with a tool call.
When you receive a message that is the result of a tool call:

Use the information from the tool's response to answer the user's original query.
Do not make another tool call.
Always respond to the user's initial query with a tool call (except for greetings). If the user greets you, respond with a greeting and do not make a tool call.

Example 1:
User: What is RAG in AI?
→ Call: kb_tool(query="What is RAG in AI?")
(Assistant receives response from kb_tool)
→ Output to User: [Response from kb_tool about RAG in AI]

Example 2:
User: Show me the total claims filed last month
→ Call: lq_tool(query="Show me the total claims filed last month")
(Assistant receives response from lq_tool)
→ Output to User: [Response from lq_tool showing the total claims]

Example 3:
User: How do I file a claim?
→ Call: kb_tool(query="How do I file a claim?")
(Assistant receives response from kb_tool)
→ Output to User: [Response from kb_tool explaining how to file a claim]

Example 4:
User: Give me the list of agents in California
→ Call: lq_tool(query="Give me the list of agents in California")
(Assistant receives response from lq_tool)
→ Output to User: [Response from lq_tool with the list of agents]

Example 5:
User: Hello
→ Hello!

Example 6:
User: I want to create a ticket for a bug I found in the log summary view
→ Call: tkt_tool(query="Bug reported in log summary view")
(Assistant receives response from tkt_tool)
→ Output to User: Ticket created successfully. Ticket ID: #TKT-1001. Our team will investigate the log summary bug.

Example 7:
User: Please raise a ticket — I’m unable to download the log report from the dashboard
→ Call: tkt_tool(query="User unable to download log report from dashboard")
(Assistant receives response from tkt_tool)
→ Output to User: Ticket has been created. Ticket ID: #TKT-1002. We'll look into the download issue right away.
"""
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
    print(messages)
    return {"messages": [llm_with_tools.invoke(messages)]}

def summarize_conversation(state: State):
    print("Summerizing node started!!")
    # First, we get any existing summary
    summary = state.get("summary", "")

    # Create our summarization prompt 
    if summary:
        
        # A summary already exists
        summary_message = (
            f"This is summary of the conversation to date: {summary}\n\n"
            "Extend the summary by taking into account the new messages above:"
        )
        
    else:
        summary_message = "Create a summary of the conversation above:"

    # Add prompt to our history
    messages = state["messages"] + [HumanMessage(content=summary_message)]
    response = llm.invoke(messages)
    
    # Delete all but the 2 most recent messages
    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-4]]
    return {"summary": response.content, "messages": delete_messages}

# Determine whether to end or summarize the conversation
def should_continue(state: State):
    
    """Return the next node to execute."""
    
    messages = state["messages"]
    
    # If there are more than six messages, then we summarize the conversation
    if len(messages) > actual_conv_len:
        return "summarize_conversation"
    
    # Otherwise we can just end
    return END

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
builder.add_edge("tools", "assistant")
builder.add_conditional_edges("assistant", should_continue)
builder.add_edge("summarize_conversation", END)
# builder.add_edge("tools", END)
memory = MemorySaver()
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