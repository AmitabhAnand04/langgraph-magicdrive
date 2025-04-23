# 🔍 Tool-Aware Query API using LangGraph

This project provides an intelligent query API built with **FastAPI** and **LangGraph** using **Gemini 1.5 Flash**. The API intelligently routes user queries to the appropriate backend logic/tool — either a **Knowledge Base tool (`kb_tool`)** or a **Database tool (`lq_tool`)** — based on the **intent of the question**.

## 🚀 Overview

When a user sends a query to the `/query` endpoint, the system:

1. Passes the query to a LangGraph ReAct-style graph.
2. The **Gemini LLM acts as a controller**, deciding **which tool** should be used based on the query.
3. Based on this decision:
   - If it’s a **knowledge-based question**, `kb_tool` is invoked.
   - If it’s a **database or data retrieval question**, `lq_tool` is invoked.
4. The tool runs and returns the response — **LLM never directly answers the query, but it can answer greetings (like "hi", "hello", "good morning") without tool invocation.**.

## 🧠 How Tool Selection Works

The Gemini LLM is given a strict system prompt instructing it:

- **NOT to answer any questions directly**
- Only to call one of two tools:
  - `kb_tool(query: str)` – for general knowledge-based answers
  - `lq_tool(query: str)` – for SQL/data queries

It uses a **ReAct agent loop** built with `MessagesState` and `ToolNode` to manage tool calling and processing.

### ✨ Examples of Tool Routing

| User Query                             | Tool Used |
|----------------------------------------|-----------|
| *"What is RAG in AI?"*                 | `kb_tool` |
| *"Show me total claims filed in March"*| `lq_tool` |
| *"How do I reset my password?"*        | `kb_tool` |
| *"Get the list of all agents in Texas"*| `lq_tool` |
| *"Hello there!"*	                     |LLM (no tool used)|

---

## 🧪 API Usage

### Endpoint

```
GET /query
```

### Query Parameter

| Name       | Type   | Required | Description                       |
|------------|--------|----------|-----------------------------------|
| `user_query` | `str` | ✅       | The natural language question to process |

### Example Request

```
GET /query?user_query=What is RAG in AI?
```

### Example Response

```json
{
  "result": {
    "type": "tool",
    "content": "[KB Tool] Answering based on knowledge base: What is RAG in AI?"
  }
}
```

---

## 🛠️ Project Structure

```bash
├── main.py        # FastAPI application
├── graph.py       # LangGraph workflow with LLM + tools
├── README.md      # Project documentation (this file)
```

---

## 🧰 Tech Stack

- [FastAPI](https://fastapi.tiangolo.com/)
- [LangGraph](https://docs.langgraph.dev/)
- [LangChain](https://www.langchain.com/)
- [Gemini 1.5 Flash](https://ai.google.dev/)
- Python 3.10+

---

## 🏁 Running the App

1. Install dependencies:

```bash
pip install fastapi uvicorn langgraph langchain langchain-google-genai
```

2. Start the API server:

```bash
uvicorn main:app --reload
```

3. Hit the `/query` endpoint in your browser or Postman.