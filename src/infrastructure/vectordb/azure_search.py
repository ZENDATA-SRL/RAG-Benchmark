import os
from typing import Literal
from uuid import UUID

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from src.config.solver.prompts import HYDE_PROMPT
from src.dataset.models import DocumentORM as Document

load_dotenv()


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
) -> list[Document]:
    search_client = get_azure_search_client()
    top = top_k
    # TODO: build vector DB filter (chunks from dataset docs with chosen configs)

    if hyde:
        hyde = await llm.ainvoke(
            [HumanMessage(content=HYDE_PROMPT.format(query=query))]
        )
        embeddings = await embedder.aembed_query(hyde)
    if hybrid:
        chunks = search_client.search(
            search_text=query,
            vector_queries=[VectorizedQuery(vector=embeddings)],
            top=top,
        )
    else:
        chunks = search_client.search(
            vector_queries=[VectorizedQuery(vector=embeddings)], top=top
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
