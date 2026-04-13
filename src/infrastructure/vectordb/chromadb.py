import os
from typing import Literal
from uuid import UUID

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from src.config.ingestion.vectordb.schemas import VectorDBConfigSchema
from src.config.solver.prompts import HYDE_PROMPT
from src.infrastructure.vectordb.base import BaseVectorDB
from src.infrastructure.vectordb.models import EmbeddedChunk
from src.infrastructure.vectordb.utils import (
    chunk_ids_for_dataset,
    embedded_chunks_for_chunk_ids,
)

load_dotenv()


class ChromaVectorDB(BaseVectorDB):
    def __init__(self, cfg: VectorDBConfigSchema) -> None:
        self._cfg = cfg

    async def retrieve_chunks(
        self,
        *,
        embedder: Embeddings,
        llm: BaseChatModel,
        query: str,
        top_k: int,
        hyde: bool,
        hybrid: bool,
        reranking: Literal["llm", "semantic"] | None,
        dataset_id: UUID,
        chunker_id: UUID,
        embedder_id: UUID,
        ocr_id: UUID,
    ) -> list[EmbeddedChunk]:
        vector_db: Chroma = _get_vector_db(embedder, self._cfg)

        chunk_ids = await chunk_ids_for_dataset(
            dataset_id=dataset_id,
            ocr_id=ocr_id,
            chunker_id=chunker_id,
        )
        if not chunk_ids:
            return []

        await self._ensure_indexed(
            vector_db=vector_db,
            embedder=embedder,
            chunk_ids=chunk_ids,
            embedder_id=embedder_id,
        )

        filter = {"chunk_id": {"$in": [str(cid) for cid in chunk_ids]}}

        if hyde:
            hyde_msg = await llm.ainvoke(
                [HumanMessage(content=HYDE_PROMPT.format(query=query))]
            )
            docs = vector_db.similarity_search(
                query=hyde_msg.content, k=top_k, filter=filter
            )
        else:
            docs = vector_db.similarity_search(query=query, k=top_k, filter=filter)

        # TODO: implement hybrid + reranking for Chroma
        return [
            EmbeddedChunk(
                id=UUID(doc.id) if not isinstance(doc.id, UUID) else doc.id,
                embedding_id=UUID(doc.id) if not isinstance(doc.id, UUID) else doc.id,
                chunk_id=UUID(doc.metadata.get("chunk_id")),
                text=doc.page_content,
                vectors=[],
            )
            for doc in docs
        ]

    async def upload_chunks(
        self, *, chunks: list[EmbeddedChunk], embedder: Embeddings
    ) -> None:
        if not chunks:
            return
        vector_db: Chroma = _get_vector_db(embedder, self._cfg)
        vector_db._collection.upsert(
            ids=[str(chunk.id) for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "chunk_id": str(chunk.chunk_id),
                    "embedding_id": str(chunk.embedding_id),
                }
                for chunk in chunks
            ],
            embeddings=[chunk.vectors for chunk in chunks],
        )

    async def _ensure_indexed(
        self,
        *,
        vector_db: Chroma,
        embedder: Embeddings,
        chunk_ids: list[UUID],
        embedder_id: UUID,
    ) -> None:
        embedded = await embedded_chunks_for_chunk_ids(
            chunk_ids=chunk_ids, embedder_id=embedder_id
        )
        if not embedded:
            return

        desired_ids = [str(c.id) for c in embedded]
        existing = vector_db._collection.get(ids=desired_ids, include=[])
        existing_ids = set(existing.get("ids") or [])
        missing_ids = [cid for cid in desired_ids if cid not in existing_ids]
        if not missing_ids:
            return

        missing_chunks = [c for c in embedded if str(c.id) in set(missing_ids)]
        await self.upload_chunks(chunks=missing_chunks, embedder=embedder)


def _get_vector_db(embedder: Embeddings, cfg: VectorDBConfigSchema) -> Chroma:
    collection_name = cfg.config.get("collection_name") or os.getenv(
        "VECTORSTORE_COLLECTION_NAME"
    )

    host = cfg.config.get("host") or os.getenv("VECTORSTORE_HOST")
    port_raw = cfg.config.get("port") or os.getenv("VECTORSTORE_PORT")
    port = int(port_raw) if port_raw is not None and str(port_raw).strip() else None

    return Chroma(
        collection_name=collection_name,
        embedding_function=embedder,
        host=host,
        port=port,
        # Default to plain HTTP for local Chroma.
        ssl=False,
    )
