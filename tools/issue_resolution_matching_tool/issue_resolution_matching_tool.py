import os
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core import Settings
import os
import io
import pandas as pd
import shutil
from azure.storage.blob import ContainerClient
from llama_index.core.schema import Document
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.readers.azstorage_blob import AzStorageBlobReader


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


def clean_document_metadata(document):
    """Clean document metadata to remove non-serializable objects"""
    if hasattr(document, 'metadata') and document.metadata:
        cleaned_metadata = {}
        for key, value in document.metadata.items():

            if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                cleaned_metadata[key] = value
            else:
                
                cleaned_metadata[key] = str(value)
        document.metadata = cleaned_metadata
    return document


def load_documents_from_azure_with_reader(connection_string: str, container_name: str, prefix: str = ISSUE_UPLOADS_BLOB_PREFIX):
    """
    Loads documents from Azure Blob Storage and parses CSV content into individual documents
    for each issue-resolution pair.
    Assumes the CSV has columns: 'issue', 'category', 'resolution'.
    """
    print(f"Attempting to load documents from Azure Blob: Container='{container_name}', Prefix='{prefix}'")
    
    try:
        blob_service_client = ContainerClient.from_connection_string(
            conn_str=connection_string,
            container_name=container_name
        )
    except Exception as e:
        print(f"Error connecting to Azure Blob Storage: {e}")
        return []

    all_parsed_documents = []
    
    blob_list = blob_service_client.list_blobs(name_starts_with=prefix)
    
    for blob in blob_list:
        if blob.name.endswith('.csv'):
            print(f"Processing CSV blob: {blob.name}")
            try:
                blob_client = blob_service_client.get_blob_client(blob.name)
                download_stream = blob_client.download_blob()
                csv_content = download_stream.readall().decode('utf-8')

                df = pd.read_csv(io.StringIO(csv_content))
                print(f"DataFrame loaded. Number of rows: {len(df)}")

                
                required_columns = ['issue', 'resolution']
                if not all(col in df.columns for col in required_columns):
                    print(f"Warning: CSV '{blob.name}' missing expected columns ('issue', 'resolution'). Skipping.")
                    continue

                for index, row in df.iterrows():
                    issue_text = row['issue']
                    resolution_text = row['resolution']
                    category_text = row['category'] if 'category' in df.columns else None 

                    doc = Document(
                        text=resolution_text,
                        metadata={
                            "issue": issue_text,
                            "category": category_text,
                            "source_file": blob.name,
                            "row_number": index
                        }
                    )
                    all_parsed_documents.append(clean_document_metadata(doc))

            except Exception as e:
                print(f"Error processing blob '{blob.name}': {e}")
                continue

    print(f"Successfully loaded and parsed {len(all_parsed_documents)} documents from Azure Blob Storage.")
    if all_parsed_documents:
        print(f"First parsed document text snippet: {all_parsed_documents[0].text[:200]}...")
        print(f"First parsed document metadata: {all_parsed_documents[0].metadata}")
    return all_parsed_documents


def build_index(container_client, delete_old_index=True):
    global index, chat_engine

    print("Loading documents from Azure blob for reindexing Issue Resolution...")

    documents = load_documents_from_azure_with_reader(
        connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
        container_name=os.getenv("AZURE_CONTAINER_NAME"),
        prefix=ISSUE_UPLOADS_BLOB_PREFIX
    )

    if not documents:
        print("No documents found in Azure blob folder for Issue Resolution, skipping index build.")
        index = None
        chat_engine = None

        if delete_old_index and os.path.exists(index_storage_dir):
            shutil.rmtree(index_storage_dir)

        return False

    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=index_storage_dir)

    memory = ChatMemoryBuffer.from_defaults(token_limit=4000)
    chat_engine = index.as_chat_engine(
        chat_mode="context",
        memory=memory,
       system_prompt=(
    """You are a highly specialized document assistant. Your only task is to precisely extract and return the 'resolution' section from the provided context.
    
    **Crucial Rules to Follow Meticulously:**
    1.  **Extract ONLY the resolution.** Do not include the issue description, category, summaries, or any introductory/concluding sentences.
    2.  Return the resolution text exactly as it appears in the source, word for word, including any numbering or formatting.
    3.  **STRICTLY, IF THE PROVIDED CONTEXT DOES NOT CONTAIN A CLEAR, DIRECT RESOLUTION TO THE USER'S EXACT QUESTION, YOUR ONLY RESPONSE MUST BE: "No resolution found in the documents."** Do not attempt to guess, summarize, or create any other text.
    4.  Strictly avoid hallucination or generating any text not present in the original resolution.
    
    **Example of desired behavior (if no resolution is found):**
    User Query: "How do I fix issues with my new biometric scanner?"
    (If no resolution for biometric scanners is in your documents)
    Your Response: "No resolution found in the documents."
    """
)
    )
    print("Index completed successfully for Issue Resolution.")
    return True


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
    """You are a highly specialized document assistant. Your only task is to precisely extract and return the 'resolution' section from the provided context.
    
    **Crucial Rules to Follow Meticulously:**
    1.  **Extract ONLY the resolution.** Do not include the issue description, category, summaries, or any introductory/concluding sentences.
    2.  Return the resolution text exactly as it appears in the source, word for word, including any numbering or formatting.
    3.  **STRICTLY, IF THE PROVIDED CONTEXT DOES NOT CONTAIN A CLEAR, DIRECT RESOLUTION TO THE USER'S EXACT QUESTION, YOUR ONLY RESPONSE MUST BE: "No resolution found in the documents."** Do not attempt to guess, summarize, or create any other text.
    4.  Strictly avoid hallucination or generating any text not present in the original resolution.
    
    **Example of desired behavior (if no resolution is found):**
    User Query: "How do I fix issues with my new biometric scanner?"
    (If no resolution for biometric scanners is in your documents)
    Your Response: "No resolution found in the documents."
    """
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