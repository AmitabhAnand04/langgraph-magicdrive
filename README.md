# 🧠 magicSupport API Documentation

This API leverages **FastAPI** and **LangGraph** with **Gemini 1.5 Flash** to intelligently route user queries to the appropriate backend tools: `kb_tool`, `lq_tool`, or `tkt_tool`.

## 📌 Overview

* **`/api/query`**: Processes user queries and routes them to the appropriate tool.
* **`/api/sendchat`**: Sends the conversation history to Chatwoot based on a provided `thread_id` and `source_id`.

---

## 🔧 Tools

| Tool Name  | Purpose                                       |
| ---------- | --------------------------------------------- |
| `kb_tool`  | Handles general knowledge-based questions.    |
| `lq_tool`  | Processes database or data retrieval queries. |
| `tkt_tool` | Manages ticket creation-related queries.      |

---

## 📬 Endpoints

### 1. `GET /api/query`

**Description**: Processes a user query and returns the appropriate response based on the tool invoked.

**Query Parameters**:

* `user_query` (string, required): The user's natural language question.
* `thread_id` (string, optional): Unique identifier for the conversation thread.
  * It is generated during the initial request and must be included in subsequent calls to continue the same conversation. If not provided, a new conversation thread will be created for each request.

**Response Structure**:

The response varies based on the tool invoked:

#### a. `kb_tool` or `tkt_tool` Response:

```json
{
  "result": "string",  // Direct answer from the tool.
  "thread_id": "string"
}
```

* **`result`**: Contains the direct answer as a string.
* **`thread_id`**: Unique identifier for the conversation thread.

#### b. `lq_tool` Response:

```json
{
  "result": {
    "tool_name": "lq_tool",
    "content": {
      "sql_string": "string",       // The SQL query executed.
      "sql_result": [               // Results from the SQL query.
        {
          "column1": "value1",
          "column2": "value2"
          // ...additional columns
        }
        // ...additional rows
      ],
      "explain_result": "string",   // Explanation of the SQL result.
      "result_list": null           // Reserved for future use.
    }
  },
  "thread_id": "string"
}
```

* **`tool_name`**: Indicates the tool used (`lq_tool`).
* **`content`**:

  * `sql_string`: The SQL query that was executed.
  * `sql_result`: An array of objects representing the query results.
  * `explain_result`: A textual explanation of the results.
  * `result_list`: Currently null; reserved for future enhancements.
* **`thread_id`**: Unique identifier for the conversation thread.

**Frontend Handling**:

* Check if `result` is a string:

  * If yes, display it directly as the answer.
* If `result` is an object:

  * Use `result.content.explain_result` for the answer.
  * Display `result.content.sql_result` in a tabular format.

---

### 2. `POST /api/sendchat`

**Description**: Sends the conversation history associated with a specific `thread_id` to Chatwoot, linked via a `source_id`.

**Request Body**:

```json
{
  "thread_id": "string",  // Unique identifier for the conversation thread.
  "source_id": "string"   // Identifier linking to Chatwoot's conversation.
}
```

**Response Structure**:

```json
{
  "thread_id": "string",
  "conversation_id": "string",
  "message_sent": "string",  // The formatted conversation history.
  "message": "Messages sent to Chatwoot!!"
}
```

* **`thread_id`**: The provided thread identifier.
* **`conversation_id`**: The corresponding Chatwoot conversation ID.
* **`message_sent`**: The formatted conversation history that was sent.
* **`message`**: Confirmation message indicating successful transmission.

---

## 🧪 Examples

### a. Knowledge-Based Query

**Request**:

```
GET /api/query?user_query=What is RAG in AI?
```

**Possible Response**:

```json
{
  "result": "RAG stands for Retrieval-Augmented Generation...",
  "thread_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### b. Data Retrieval Query

**Request**:

```
GET /api/query?user_query=Show me total claims filed in March
```

**Possible Response**:

```json
{
  "result": {
    "tool_name": "lq_tool",
    "content": {
      "sql_string": "SELECT COUNT(*) FROM claims WHERE month = 'March';",
      "sql_result": [
        {
          "total_claims": 150
        }
      ],
      "explain_result": "There were 150 claims filed in March.",
      "result_list": null
    }
  },
  "thread_id": "123e4567-e89b-12d3-a456-426614174001"
}
```

### c. Ticket Creation Query

**Request**:

```
GET /api/query?user_query=I need to create a support ticket
```

**Possible Response**:

```json
{
  "result": "A support ticket has been created with ID #456789.",
  "thread_id": "123e4567-e89b-12d3-a456-426614174002"
}
```

---

## 🧰 Tech Stack
* Python 3.10+
* [FastAPI](https://fastapi.tiangolo.com/)
* [LangGraph](https://docs.langgraph.dev/)
* [LangChain](https://www.langchain.com/)
* [LlamaIndex](https://www.llamaindex.ai/)
* [Gemini 1.5 Flash](https://ai.google.dev/)
* [Zoho Desk API](https://www.zoho.com/desk/)
* [Chatwoot API](https://www.chatwoot.com/)
* [MS SQL Server](https://www.microsoft.com/en-us/sql-server/)

---

## 🏁 Running the Application

### 1. **Install Dependencies**

```bash
pip install -r requirements.txt
```

Make sure your `requirements.txt` includes:

```text
llama-index
llama-index-core
llama-index-llms-gemini
llama-index-embeddings-gemini
langchain-core
langchain-google-genai
langgraph
python-dotenv
fastapi
uvicorn
pyodbc
```

### 2. **Set Up Environment Variables**

Create a `.env` file in the root directory with the following:

```env
# Zoho Credentials
ZOHO_REFRESH_TOKEN=your_refresh_token
ZOHO_CLIENT_ID=your_client_id
ZOHO_CLIENT_SECRET=your_client_secret
ZOHO_DEPARTMENT_ID=your_department_id
ZOHO_CONTACT_ID=your_contact_id
ZOHO_ORG_ID=your_org_id

# Gemini API
GOOGLE_API_KEY=your_gemini_api_key

# SQL Server DB
DB_SERVER=your_sql_server
DB_DATABASE=your_database_name
DB_USERNAME=your_db_username
DB_PASSWORD=your_db_password

# Chatwoot Creds
CHATWOOT_BASE_URL=your_chatwoot_baseurl
CHATWOOT_API_TOKEN=your_chatwoot_api_key
```

### 3. **Start the API Server**

```bash
uvicorn main:app --reload
```

### 4. **Access the Endpoints**:

* Use tools like Postman, cURL, or a browser to interact with:

  * `GET /api/query`
  * `POST /api/sendchat`
