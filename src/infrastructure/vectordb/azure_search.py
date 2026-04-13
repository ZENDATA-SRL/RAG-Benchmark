import os
from typing import Literal
from uuid import UUID

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv
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


class AzureSearchVectorDB(BaseVectorDB):
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
        search_client = _get_azure_search_client(self._cfg)

        chunk_ids = await chunk_ids_for_dataset(
            dataset_id=dataset_id,
            ocr_id=ocr_id,
            chunker_id=chunker_id,
        )
        if not chunk_ids:
            return []

        await self._ensure_indexed(
            search_client=search_client,
            embedder=embedder,
            chunk_ids=chunk_ids,
            embedder_id=embedder_id,
        )

        chunk_id_filter = (
            f"search.in(chunk_id, '{','.join([str(x) for x in chunk_ids])}', ',')"
        )

        if hyde:
            hyde_msg = await llm.ainvoke(
                [HumanMessage(content=HYDE_PROMPT.format(query=query))]
            )
            embeddings = await embedder.aembed_query(hyde_msg.content)
        else:
            embeddings = await embedder.aembed_query(query)

        if hybrid:
            results = search_client.search(
                search_text=query,
                vector_queries=[VectorizedQuery(vector=embeddings)],
                top=top_k,
                filter=chunk_id_filter,
            )
        else:
            results = search_client.search(
                vector_queries=[VectorizedQuery(vector=embeddings)],
                top=top_k,
                filter=chunk_id_filter,
            )

        # TODO: implement reranker
        out: list[EmbeddedChunk] = []
        for doc in results:
            emb_id = UUID(str(doc.get("id")))
            out.append(
                EmbeddedChunk(
                    id=emb_id,
                    embedding_id=emb_id,
                    chunk_id=UUID(str(doc.get("chunk_id"))),
                    text=str(doc.get("text") or ""),
                    vectors=[],
                )
            )
        return out

    async def upload_chunks(
        self, *, chunks: list[EmbeddedChunk], embedder: Embeddings
    ) -> None:
        if not chunks:
            return
        search_client = _get_azure_search_client(self._cfg)
        search_client.upload_documents(
            documents=[
                {
                    "id": str(chunk.id),
                    "chunk_id": str(chunk.chunk_id),
                    "embedding_id": str(chunk.embedding_id),
                    "text": chunk.text,
                    "vectors": chunk.vectors,
                }
                for chunk in chunks
            ]
        )

    async def _ensure_indexed(
        self,
        *,
        search_client: SearchClient,
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
        existing_ids = _azure_existing_ids(search_client, desired_ids)
        missing = [x for x in desired_ids if x not in existing_ids]
        if not missing:
            return
        missing_set = set(missing)
        missing_chunks = [c for c in embedded if str(c.id) in missing_set]
        await self.upload_chunks(chunks=missing_chunks, embedder=embedder)


def _azure_existing_ids(search_client: SearchClient, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    # Assumes index has key field named `id`.
    id_filter = f"search.in(id, '{','.join(ids)}', ',')"
    results = search_client.search(
        search_text="*", top=len(ids), filter=id_filter, select=["id"]
    )
    return {str(r.get("id")) for r in results}


def _get_azure_search_client(cfg: VectorDBConfigSchema) -> SearchClient:
    endpoint = cfg.config.get("endpoint") or os.getenv("AZURE_SEARCH_ENDPOINT")
    key = cfg.config.get("key") or os.getenv("AZURE_SEARCH_KEY")
    index_name = cfg.config.get("index_name") or os.getenv(
        "VECTORSTORE_COLLECTION_NAME"
    )
    if not endpoint or not key or not index_name:
        raise ValueError(
            "Azure Search requires endpoint/key/index_name (or env AZURE_SEARCH_ENDPOINT/AZURE_SEARCH_KEY/AZURE_SEARCH_INDEX_NAME)"
        )
    return SearchClient(
        endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(key)
    )
