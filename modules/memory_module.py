# memory_module.py

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from sentence_transformers import SentenceTransformer
from uuid import uuid4
import os
from dotenv import load_dotenv
load_dotenv()

# Qdrant Cloud setup
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") 
QDRANT_URL = os.getenv("QDRANT_URL") 
COLLECTION_NAME = "agent_memory"
EMBEDDING_DIM = 384  # depends on model

# Initialize embedding model
model = SentenceTransformer("all-MiniLM-L6-v2", token = os.getenv("HF_TOKEN"))

# Initialize Qdrant client
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

# Ensure collection exists
def initialize_memory_collection():
    if COLLECTION_NAME not in [col.name for col in client.get_collections().collections]:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
        )

# Embed and store a memory
def store_text_memory(text: str, metadata: dict = {}):
    vector = model.encode(text).tolist()
    memory_id = str(uuid4())
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[{
            "id": memory_id,
            "vector": vector,
            "payload": {"text": text, **metadata}
        }]
    )
    return memory_id

# Embed and search memory
def search_similar_memory(query: str, top_k=5):
    query_vector = model.encode(query).tolist()
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=5
    )
    return results

# Initialize on import
initialize_memory_collection()
