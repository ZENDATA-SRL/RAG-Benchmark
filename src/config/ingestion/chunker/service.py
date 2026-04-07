from collections.abc import Callable
from uuid import UUID, uuid4

from langchain_text_splitters import (
    CharacterTextSplitter,
    MarkdownTextSplitter,
    RecursiveCharacterTextSplitter,
    TextSplitter,
)

from config.ingestion.chunker.base import BaseChunker
from config.ingestion.chunker.models import ChunkerConfig
from config.ingestion.chunker.repository import get_chunker_repository
from config.ingestion.chunker.schemas import ChunkerConfigSchema
from core.models import Chunk

_SPLITTER_BUILDERS: dict[str, Callable[..., TextSplitter]] = {
    "character": CharacterTextSplitter,
    "markdown": MarkdownTextSplitter,
    "recursive_character": RecursiveCharacterTextSplitter,
    "fixed_size": RecursiveCharacterTextSplitter,
}


class LangChainChunker(BaseChunker):
    """Wraps a LangChain `TextSplitter` as a `BaseChunker`."""

    def __init__(
        self,
        splitter: TextSplitter,
        chunk_size: int,
        overlap_size: int,
    ) -> None:
        super().__init__(chunk_size, overlap_size)
        self._splitter = splitter

    def extract_chunks(self, text: str, scan_id: UUID, chunker_id: UUID) -> list[Chunk]:
        docs = self._splitter.create_documents([text])
        return [
            Chunk(
                id=uuid4(),
                scan_id=scan_id,
                chunker_id=chunker_id,
                start_index=doc.metadata["start_index"],
                end_index=doc.metadata["start_index"] + len(doc.page_content),
                text=doc.page_content,
            )
            for doc in docs
        ]


# This one will be helpful in the CORE layer after the resolution of the conig.
def build_chunker(
    chunker_config: ChunkerConfigSchema,
) -> BaseChunker:
    try:
        splitter_cls = _SPLITTER_BUILDERS[chunker_config.strategy]
    except KeyError as e:
        allowed = ", ".join(sorted(_SPLITTER_BUILDERS))
        msg = f"Unknown chunker {chunker_config.strategy!r}; expected one of: {allowed}"
        raise ValueError(msg) from e
    splitter = splitter_cls(
        chunk_size=chunker_config.chunk_size,
        chunk_overlap=chunker_config.overlap_size,
        add_start_index=True,
    )
    return LangChainChunker(
        splitter, chunker_config.chunk_size, chunker_config.overlap_size
    )


async def resolve_chunker(chunker: ChunkerConfigSchema) -> ChunkerConfig:
    repository = get_chunker_repository()
    chunker_object = await repository.get_chunker_by_config(chunker)
    if chunker_object:
        return chunker_object
    else:
        chunker_config = ChunkerConfigSchema(
            strategy=chunker.strategy,
            chunk_size=chunker.chunk_size,
            overlap_size=chunker.overlap_size,
        )
        return await repository.insert_chunker_config(chunker_config)
