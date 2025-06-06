import os
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core import Settings
import os
import shutil
from azure.storage.blob import ContainerClient
from llama_index.core.schema import Document
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.core.memory import ChatMemoryBuffer


api_key = os.getenv("GOOGLE_API_KEY")
current_dir = os.path.dirname(os.path.abspath(__file__))
index_storage_dir = os.path.join(current_dir, "issue_resolution_indexing")
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

ISSUE_UPLOADS_BLOB_PREFIX = "issue_resolution_data_uploads/"

index = None
chat_engine = None


def load_documents_from_azure(container_client: ContainerClient, prefix=ISSUE_UPLOADS_BLOB_PREFIX):
    documents = []
    blobs = container_client.list_blobs(name_starts_with=prefix)

    ALLOWED_EXTENSIONS = {".csv"}
    for blob in blobs:
        ext = os.path.splitext(blob.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            print(f"Skipping unsupported extension: {blob.name}")
            continue

        blob_client = container_client.get_blob_client(blob.name)
        try:
            content = blob_client.download_blob().readall().decode('utf-8')
            documents.append(Document(text=content, metadata={"filename": blob.name}))
        except UnicodeDecodeError:
            print(f"Skipping non-text or corrupted file: {blob.name}")
            continue

    return documents


def build_index(container_client, delete_old_index=True):
    global index, chat_engine

    print("Loading documents from Azure blob for reindexing Issue Resolution...")

    documents = load_documents_from_azure(container_client)
    if not documents:
        print("No documents found in Azure blob folder for Issue Resolution, skipping index build.")
        index = None
        chat_engine = None
        return False

    if delete_old_index and os.path.exists(index_storage_dir):
        shutil.rmtree(index_storage_dir)

    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=index_storage_dir)

    memory = ChatMemoryBuffer.from_defaults(token_limit=4000)
    chat_engine = index.as_chat_engine(
        chat_mode="context",
        memory=memory,
        system_prompt=(
            """You are a document assistant that retrieves only the 'Resolution' section from provided documents.
            Do not return any summaries, issues, causes, or extra text.
            Only return the resolution as it appears in the source documents, word for word.
            If no resolution is found, reply: "No resolution found."""
        )
    )
    print("Index completed successfully for Issue Resolution.")


def load_existing_index(container_client):
    global index, chat_engine

    blobs = list(container_client.list_blobs(name_starts_with=ISSUE_UPLOADS_BLOB_PREFIX))
    if not blobs:
        print("No files found in Azure blob storage folder in Issue Resolution, skipping loading existing index.")
        index = None
        chat_engine = None
        return

    if os.path.exists(index_storage_dir) and os.listdir(index_storage_dir):
        try:
            print("Loading existing index from local storage for Issue Resolution...")
            storage_context = StorageContext.from_defaults(persist_dir=index_storage_dir)
            index = load_index_from_storage(storage_context)

            memory = ChatMemoryBuffer.from_defaults(token_limit=4000)
            chat_engine = index.as_chat_engine(
                chat_mode="context",
                memory=memory,
                system_prompt=(
                    """You are a document assistant that retrieves only the 'Resolution' section from provided documents.
                    Do not return any summaries, issues, causes, or extra text.
                    Only return the resolution as it appears in the source documents, word for word.
                    If no resolution is found, reply: "No resolution found."""
                )
            )
            print("Index and chat engine loaded successfully for Issue Resolution.")
        except Exception as e:
            print(f"Failed to load index for Issue Resolution: {e}")
            index = None
            chat_engine = None
    else:
        print("No existing local index found for Issue Resolution. Please run build_index() first.")
        index = None
        chat_engine = None


def get_issue_chat_engine():
    global chat_engine
    return chat_engine


def delete_blob_from_azure(blob_name, container_client):
    try:
        full_blob_name = f"issue_resolution_data_uploads/{blob_name}"
        blob_client = container_client.get_blob_client(full_blob_name)
        blob_client.delete_blob()
        print(f"Deleted blob: {full_blob_name}")
        return True
    except Exception as e:
        print(f"Error deleting blob: {e}")
        return False

