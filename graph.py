from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.prebuilt import ToolNode
from tools.kb_tools.kb_tool import chat_engine
from tools.lq_tools.lq_tool import nl_sql_nl_gemini

llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

def kb_tool(query: str) -> dict:
    """Answer for knowledge-based questions."""
    # answer = chat_engine.chat(query).response
    # return {"messages": [answer]}
    return chat_engine.chat(query).response

def lq_tool(query: str) -> dict:
    """answer for database query related questions.

    Args:
        query: user query
    """
    # return f"[LQ Tool] SQL executed for: {query}"
    return nl_sql_nl_gemini (query)

tools = [kb_tool, lq_tool]
llm_with_tools = llm.bind_tools(tools)


# System message
# sys_msg = SystemMessage(content="You are a helpful assistant whic will decide which tool to use for the user provided query.")
sys_msg = SystemMessage(
    content="""
You are an AI assistant that **only decides which tool to use** for a given user query.

You MUST NOT answer the user's query yourself.

You have access to the following tools:
1. `kb_tool`: Use when the user is asking for knowledge-based answers.
2. `lq_tool`: Use when the user is asking to retrieve data or perform operations on a database.

Always respond with a tool call — even if the query seems simple.

DO NOT respond directly to the user's query under any circumstance other that greetings. it there is greet from the user then don't respond with tool call and just greet back.

Example 1:
User: What is RAG in AI?
→ Call: kb_tool(query="What is RAG in AI?")

Example 2:
User: Show me the total claims filed last month
→ Call: lq_tool(query="Show me the total claims filed last month")

Example 3:
User: How do I file a claim?
→ Call: kb_tool(query="How do I file a claim?")

Example 4:
User: Give me the list of agents in California
→ Call: lq_tool(query="Give me the list of agents in California")
"""
)

# print(sys_msg)
# Node
def assistant(state: MessagesState):
#    print(state["messages"])
   return {"messages": [llm_with_tools.invoke([sys_msg] + state["messages"])]}


# Graph
builder = StateGraph(MessagesState)

# Define nodes: these do the work
builder.add_node("assistant", assistant)
builder.add_node("tools", ToolNode(tools))

# Define edges: these determine how the control flow moves
builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant",
    # If the latest message (result) from assistant is a tool call -> tools_condition routes to tools
    # If the latest message (result) from assistant is a not a tool call -> tools_condition routes to END
    tools_condition,
)
# builder.add_edge("tools", "assistant")
builder.add_edge("tools", END)
react_graph = builder.compile()

