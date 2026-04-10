import os
from typing import Literal
from uuid import UUID

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from sqlalchemy import select

from src.config.solver.prompts import HYDE_PROMPT
from src.core.models import ChunkORM, ScanORM
from src.core.schemas import Embedding
from src.dataset.models import DocumentORM as DocumentORM
from src.infrastructure.database.db import get_sessionmaker

load_dotenv()


async def _chunk_ids_for_dataset(
    *,
    dataset_id: UUID,
    ocr_id: UUID,
    chunker_id: UUID,
) -> list[str]:
    """
    Return chunk IDs such that:
    - Chunk.scan_id -> Scan.document_id -> Document.dataset_id == dataset_id
    - Scan.ocr_id == ocr_id
    - Chunk.chunker_id == chunker_id

    These chunk IDs are used to build an Azure AI Search filter on `chunk_id`.
    """

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(ChunkORM.id)
            .join(ScanORM, ScanORM.id == ChunkORM.scan_id)
            .join(DocumentORM, DocumentORM.id == ScanORM.document_id)
            .where(DocumentORM.dataset_id == dataset_id)
            .where(ScanORM.ocr_id == ocr_id)
            .where(ChunkORM.chunker_id == chunker_id)
        )
        rows = (await session.scalars(stmt)).all()

    return [str(r) for r in rows]


async def retrieve_chunks(
    embedder: Embeddings,
    llm: BaseChatModel,
    query: str,
    top_k: int,
    hyde: bool,  # hypothetical document embeddings
    hybrid: bool,
    reranking: Literal["llm", "semantic"],
    dataset_id: UUID,
    chunker_id: UUID,
    embedder_id: UUID,
    ocr_id: UUID,
) -> list[Embedding]:
    search_client = get_azure_search_client()
    top = top_k
    chunk_ids = await _chunk_ids_for_dataset(
        dataset_id=dataset_id,
        ocr_id=ocr_id,
        chunker_id=chunker_id,
    )
    if not chunk_ids:
        return []

    # Azure Search supports `search.in(field, 'a,b,c', ',')` for filtering by a set.
    # Assumes your index has a `chunk_id` field matching these UUIDs (stored as strings).
    chunk_id_filter = f"search.in(chunk_id, '{','.join(chunk_ids)}', ',')"

    if hyde:
        hyde_msg = await llm.ainvoke(
            [HumanMessage(content=HYDE_PROMPT.format(query=query))]
        )
        embeddings = await embedder.aembed_query(hyde_msg.content)
    else:
        embeddings = await embedder.aembed_query(query)
    if hybrid:
        chunks = search_client.search(
            search_text=query,
            vector_queries=[VectorizedQuery(vector=embeddings)],
            top=top,
            filter=chunk_id_filter,
        )
    else:
        chunks = search_client.search(
            vector_queries=[VectorizedQuery(vector=embeddings)],
            top=top,
            filter=chunk_id_filter,
        )

    # TODO: implement reranker
    return chunks


def get_azure_search_client() -> SearchClient:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    key = os.getenv("AZURE_SEARCH_KEY")
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME")
    if not endpoint or not key or not index_name:
        raise ValueError(
            "AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, and AZURE_SEARCH_INDEX_NAME must be set"
        )
    return SearchClient(endpoint, key, index_name)
