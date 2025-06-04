import os
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core import Settings
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.core.memory import ChatMemoryBuffer


api_key = os.getenv("GOOGLE_API_KEY")
current_dir = os.path.dirname(os.path.abspath(__file__))
index_storage_dir = os.path.join(current_dir, "ir_index_storage")
data_dir = os.path.join(current_dir, "ir_data")
safety_settings = [
    {
        "category": "HARM_CATEGORY_DANGEROUS",
        "threshold": "BLOCK_LOW_AND_ABOVE",
    },
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_LOW_AND_ABOVE",
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_LOW_AND_ABOVE",
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_LOW_AND_ABOVE",
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_LOW_AND_ABOVE",
    },
]

Settings.embed_model = GeminiEmbedding(
    model_name=os.getenv('RAG_EMBEDDING_MODEL'), api_key=api_key
)

Settings.llm = Gemini(model_name=os.getenv('RAG_LLM'), api_key=api_key,safety_settings=safety_settings, temperature=0)


if not os.path.exists(index_storage_dir):
    print("Creating new index...")
    # load the documents and create the index
    documents = SimpleDirectoryReader(input_dir=data_dir).load_data()
    index = VectorStoreIndex.from_documents(documents)
    # store it for later
    index.storage_context.persist(persist_dir=index_storage_dir)
else:
    # load the existing index
    print("Loading existing index...")
    storage_context = StorageContext.from_defaults(persist_dir=index_storage_dir)
    index = load_index_from_storage(storage_context)
    
print("Index loaded successfully.")

memory = ChatMemoryBuffer.from_defaults(token_limit=4000)

chat_engine = index.as_chat_engine(
    chat_mode="context",
    memory=memory,
    system_prompt=(
    """You are a document assistant that retrieves only the 'Resolution' section from provided documents.
    Do not return any summaries, issues, causes, or extra text.
    Only return the resolution as it appears in the source documents, word for word.
    If no resolution is found, reply: "No resolution found." 
    Remember: Do not hallucinate. Follow the instructions properly. """
)
)
