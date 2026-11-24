"""
services/kb_loader.py - ChromaDB knowledge base loader for KisaanBot.

Loads application documentation into ChromaDB using the
sentence-transformers/all-MiniLM-L6-v2 embedding model.  Provides a
singleton ChromaDB collection so that duplicate instances are never created.

The knowledge base covers:
- Application overview and modules
- Crop recommendation workflow
- Crop suitability analysis workflow
- Plant disease detection workflow
- Cultivation guide functionality
- History and saved records
- UI navigation
- Account functionality
- KisaanBot functionality
- FAQs and troubleshooting
- Feature availability / development status
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "chromadb",
)
COLLECTION_NAME = "kisaanbot_app_knowledge"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Singleton instances
_chroma_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[Any] = None
_embedding_fn: Optional[Any] = None


def _get_chroma_client() -> chromadb.PersistentClient:
    """Return a singleton ChromaDB PersistentClient."""
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        logger.info("ChromaDB client initialised at %s", CHROMA_PERSIST_DIR)
    return _chroma_client


def _get_embedding_function() -> Any:
    """Return the sentence-transformers embedding function for ChromaDB."""
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
        )
        logger.info("Embedding function initialised: %s", EMBEDDING_MODEL)
    return _embedding_fn


def get_collection() -> Any:
    """Return the singleton ChromaDB collection, creating it if needed."""
    global _collection
    if _collection is None:
        client = _get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=_get_embedding_function(),
            metadata={"description": "Kisaan Suvidha application knowledge base"},
        )
        logger.info("ChromaDB collection '%s' ready", COLLECTION_NAME)
    return _collection


# ---------------------------------------------------------------------------
# Knowledge document loading
# ---------------------------------------------------------------------------
def load_knowledge_documents(documents_path: Optional[str] = None) -> List[Dict[str, str]]:
    """Load knowledge documents from a JSON file.

    Each document must have: id, title, content, category.
    """
    if documents_path is None:
        documents_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "kb_documents.json",
        )

    if not os.path.exists(documents_path):
        logger.warning("Knowledge documents file not found: %s", documents_path)
        return []

    with open(documents_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    docs = data.get("documents", [])
    logger.info("Loaded %d knowledge documents from %s", len(docs), documents_path)
    return docs


def initialise_knowledge_base(documents_path: Optional[str] = None, force_reload: bool = False) -> int:
    """Initialise (or re-initialise) the ChromaDB knowledge base.

    Returns the number of documents added.
    """
    collection = get_collection()

    # Check if already populated
    if not force_reload:
        try:
            existing = collection.count()
            if existing > 0:
                logger.info("Knowledge base already has %d documents, skipping reload", existing)
                return existing
        except Exception as e:
            logger.debug("Could not count collection: %s", e)

    documents = load_knowledge_documents(documents_path)
    if not documents:
        logger.warning("No knowledge documents to load")
        return 0

    ids: List[str] = []
    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for doc in documents:
        ids.append(doc["id"])
        # Combine title + content for richer embedding
        texts.append(f"{doc.get('title', '')}\n\n{doc.get('content', '')}")
        metadatas.append({
            "title": doc.get("title", ""),
            "category": doc.get("category", "general"),
        })

    try:
        collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("Added %d documents to ChromaDB collection", len(ids))
        return len(ids)
    except Exception as e:
        logger.error("Failed to add documents to ChromaDB: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Query / retrieval
# ---------------------------------------------------------------------------
def query_knowledge_base(
    query: str,
    n_results: int = 5,
    category_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query the ChromaDB knowledge base for relevant documents.

    Returns a list of dicts with keys: id, content, title, category, distance.
    """
    collection = get_collection()

    where: Optional[Dict[str, Any]] = None
    if category_filter:
        where = {"category": category_filter}

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("ChromaDB query failed: %s", e)
        return []

    docs: List[Dict[str, Any]] = []
    if not results or not results.get("ids"):
        return docs

    ids_list = results["ids"][0]
    documents_list = results.get("documents", [[]])[0]
    metadatas_list = results.get("metadatas", [[]])[0]
    distances_list = results.get("distances", [[]])[0]

    for i, doc_id in enumerate(ids_list):
        docs.append({
            "id": doc_id,
            "content": documents_list[i] if i < len(documents_list) else "",
            "title": metadatas_list[i].get("title", "") if i < len(metadatas_list) else "",
            "category": metadatas_list[i].get("category", "") if i < len(metadatas_list) else "",
            "distance": distances_list[i] if i < len(distances_list) else 1.0,
        })

    return docs


def is_knowledge_base_empty() -> bool:
    """Return True if the knowledge base has no documents."""
    try:
        return get_collection().count() == 0
    except Exception:
        return True
