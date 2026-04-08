## Here I will perform the ingestion of documents. I will have as inputs files that I will process based on the config

# I will load the config from db with the selected id and, with each field of the config I will instantiate the corresponding class


from uuid import UUID

from benchmark.repository import get_document
from config.ingestion.chunker.service import build_chunker, get_chunker_by_id
from config.ingestion.embedder.service import build_embedder, get_embedder_by_id
from config.ingestion.ocr.service import build_ocr, get_ocr_by_id
from config.schemas import RAGConfigSchema
from config.service import resolve_rag_config
from core.models import ChunkORM, EmbeddingORM, ScanORM
from core.service import (
    get_chunks,
    get_embeddings,
    get_scan,
    insert_chunks,
    insert_embeddings,
    insert_scan,
)
from infrastructure.blob_storage.blob import get_blob_from_url


async def process_ingestion(rag_config_schema: RAGConfigSchema, document_id: UUID):
    rag_config = await resolve_rag_config(rag_config_schema)

    ### TODO: Fix the redundant DB calls.
    ocr_config = await get_ocr_by_id(rag_config.ocr_id)
    chunker_config = await get_chunker_by_id(rag_config.chunker_id)
    embedder_config = await get_embedder_by_id(rag_config.embedder_id)
    document = await get_document(document_id)
    document_bytes = await get_blob_from_url(document.blob_url)

    scan = await get_scan(ocr_config.id, document_id)
    if not scan:
        ocr = build_ocr(ocr_config)
        scan = ScanORM(
            ocr_id=ocr_config.id,
            text=await ocr.extract_text(document_bytes),
            document_id=document_id,
        )
        await insert_scan(scan)

    chunks = await get_chunks(chunker_config.id, scan.id)
    if not chunks:
        chunker = build_chunker(chunker_config)
        chunks = [
            ChunkORM(
                scan_id=scan.id,
                chunker_id=chunker_config.id,
                start_index=chunk.start_index,
                end_index=chunk.end_index,
                text=chunk.text,
            )
            for chunk in chunker.extract_chunks(scan.text, scan.id, chunker_config.id)
        ]
        await insert_chunks(chunker_config.id, chunks)

    embedded_chunks = await get_embeddings(
        embedder_config.id, chunker_config.id, scan.id
    )
    if not embedded_chunks:
        embedder = build_embedder(embedder_config)
        embeddings = []
        for chunk in chunks:
            vectors = await embedder.aembed_query([chunk.text])
            embeddings.append(
                EmbeddingORM(
                    chunk_id=chunk.id,
                    vectors=vectors,
                    embedder_id=embedder_config.id,
                )
            )
        await insert_embeddings(embeddings)
