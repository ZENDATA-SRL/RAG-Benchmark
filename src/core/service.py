## Here I will perform the ingestion of documents. I will have as inputs files that I will process based on the config

# I will load the config from db with the selected id and, with each field of the config I will instantiate the corresponding class


import logging
import time
from datetime import datetime
from uuid import UUID

from src.config.ingestion.chunker.service import build_chunker, get_chunker_by_id
from src.config.ingestion.embedder.service import build_embedder, get_embedder_by_id
from src.config.ingestion.ocr.service import build_ocr, get_ocr_by_id
from src.config.llms.service import build_llm
from src.config.schemas import RAGConfigSchema
from src.config.service import resolve_rag_config
from src.config.solver.service import build_solver
from src.core.models import (
    AnswerChunkORM,
    AnswerORM,
    ChunkORM,
    EmbeddingORM,
    ExperimentORM,
    ScanORM,
)
from src.core.repository import (
    get_chunks as get_chunks_orm,
)
from src.core.repository import (
    get_embeddings as get_embeddings_orm,
)
from src.core.repository import (
    get_experiments as get_experiments_orm,
)
from src.core.repository import get_question_document_chunk_coverage as get_qdcc_orm
from src.core.repository import (
    get_scan as get_scan_orm,
)
from src.core.repository import (
    insert_answer,
    insert_answer_chunks,
    insert_experiment,
    update_experiment,
)
from src.core.repository import (
    insert_chunks as insert_chunks_orm,
)
from src.core.repository import (
    insert_embeddings as insert_embeddings_orm,
)
from src.core.repository import (
    insert_scan as insert_scan_orm,
)
from src.core.schemas import (
    Chunk,
    Embedding,
    Experiment,
    QuestionDocumentChunkCoverage,
    Scan,
)
from src.dataset.repository import (
    get_dataset,
    get_document,
    get_documents_by_dataset,
    get_question,
)
from src.infrastructure.blob_storage.blob import get_blob_from_url
from src.infrastructure.langfuse_client import get_langfuse_client

logger = logging.getLogger(__name__)


async def get_scan(ocr_id: UUID, document_id: UUID) -> Scan | None:
    obj = await get_scan_orm(ocr_id=ocr_id, document_id=document_id)
    if obj is None:
        return None
    return Scan.model_validate(obj)


async def insert_scan(scan: ScanORM) -> None:
    await insert_scan_orm(scan)


async def get_chunks(chunker_id: UUID, scan_id: UUID) -> list[Chunk]:
    rows = await get_chunks_orm(chunker_id=chunker_id, scan_id=scan_id)
    return [Chunk.model_validate(r) for r in rows]


async def insert_chunks(chunker_id: UUID, chunks: list[ChunkORM]) -> None:
    await insert_chunks_orm(chunker_id=chunker_id, chunks=chunks)


async def get_embeddings(
    embedder_id: UUID, chunker_id: UUID, scan_id: UUID
) -> list[Embedding]:
    rows = await get_embeddings_orm(
        embedder_id=embedder_id, chunker_id=chunker_id, scan_id=scan_id
    )
    return [Embedding.model_validate(r) for r in rows]


async def insert_embeddings(embeddings: list[EmbeddingORM]) -> None:
    await insert_embeddings_orm(embeddings=embeddings)


async def get_experiments() -> list[Experiment]:
    rows = await get_experiments_orm()
    return [Experiment.model_validate(r) for r in rows]


async def get_question_document_chunk_coverage(
    experiment_id: UUID,
) -> list[QuestionDocumentChunkCoverage]:
    rows = await get_qdcc_orm(experiment_id)
    result: list[QuestionDocumentChunkCoverage] = []
    for r in rows:
        total = int(r.get("total_answer_chunks") or 0)
        from_doc = int(r.get("answer_chunks_from_document") or 0)
        result.append(
            QuestionDocumentChunkCoverage(
                question_id=r["question_id"],
                question=r["question"],
                document_id=r["document_id"],
                document_name=r["document_name"],
                document_url=r["document_url"],
                total_answer_chunks=total,
                answer_chunks_from_document=from_doc,
                has_document_chunks=from_doc > 0,
            )
        )
    return result


async def process_ingestion(rag_config_schema: RAGConfigSchema, document_id: UUID):
    try:
        await _do_process_ingestion(rag_config_schema, document_id)
    except Exception:
        logger.exception(
            "core.process_ingestion.failed",
            extra={
                "event": "core.process_ingestion.failed",
                "document_id": str(document_id),
            },
        )
        raise


async def _do_process_ingestion(rag_config_schema: RAGConfigSchema, document_id: UUID):
    t0 = time.perf_counter()
    rag_config = await resolve_rag_config(rag_config_schema)
    logger.debug(
        "core.process_ingestion.start",
        extra={
            "event": "core.process_ingestion.start",
            "document_id": str(document_id),
            "rag_config_id": str(rag_config.id),
        },
    )

    ### TODO: Fix the redundant DB calls.
    ocr_config = await get_ocr_by_id(rag_config.ocr_id)
    chunker_config = await get_chunker_by_id(rag_config.chunker_id)
    embedder_config = await get_embedder_by_id(rag_config.embedder_id)
    document = await get_document(document_id)
    document_bytes = await get_blob_from_url(document.blob_url)

    ocr_ms: float | None = None
    scan = await get_scan(ocr_config.id, document_id)
    scan_cache_hit = bool(scan)
    if not scan:
        t_ocr = time.perf_counter()
        ocr = build_ocr(ocr_config)
        scan = ScanORM(
            ocr_id=ocr_config.id,
            text=await ocr.extract_text(document_bytes),
            document_id=document_id,
        )
        await insert_scan(scan)
        ocr_ms = round((time.perf_counter() - t_ocr) * 1000, 2)
        logger.debug(
            "core.process_ingestion.ocr_done",
            extra={
                "event": "core.process_ingestion.ocr_done",
                "document_id": str(document_id),
                "scan_id": str(scan.id),
                "duration_ms": ocr_ms,
            },
        )
    else:
        logger.debug(
            "core.process_ingestion.ocr_skip",
            extra={
                "event": "core.process_ingestion.ocr_skip",
                "document_id": str(document_id),
                "scan_id": str(scan.id),
            },
        )

    ch_ms: float | None = None
    chunks = await get_chunks(chunker_config.id, scan.id)
    chunk_cache_hit = bool(chunks)
    if not chunks:
        t_ch = time.perf_counter()
        chunker = build_chunker(chunker_config)
        extracted: list[Chunk] = chunker.extract_chunks(
            scan.text, scan.id, chunker_config.id
        )
        chunks = [
            ChunkORM(
                id=chunk.id,
                scan_id=chunk.scan_id,
                chunker_id=chunk.chunker_id,
                start_index=chunk.start_index,
                end_index=chunk.end_index,
                text=chunk.text,
            )
            for chunk in extracted
        ]
        await insert_chunks(chunker_config.id, chunks)
        ch_ms = round((time.perf_counter() - t_ch) * 1000, 2)
        logger.debug(
            "core.process_ingestion.chunk_done",
            extra={
                "event": "core.process_ingestion.chunk_done",
                "document_id": str(document_id),
                "scan_id": str(scan.id),
                "chunk_count": len(chunks),
                "duration_ms": ch_ms,
            },
        )
    else:
        logger.debug(
            "core.process_ingestion.chunk_skip",
            extra={
                "event": "core.process_ingestion.chunk_skip",
                "document_id": str(document_id),
                "scan_id": str(scan.id),
                "chunk_count": len(chunks),
            },
        )

    emb_ms: float | None = None
    embedding_count: int
    embedded_chunks = await get_embeddings(
        embedder_config.id, chunker_config.id, scan.id
    )
    embed_cache_hit = bool(embedded_chunks)
    if not embedded_chunks:
        t_emb = time.perf_counter()
        embedder = build_embedder(embedder_config)
        embeddings = []
        for chunk in chunks:
            vectors = await embedder.aembed_query(chunk.text)
            embeddings.append(
                EmbeddingORM(
                    chunk_id=chunk.id,
                    vectors=vectors,
                    embedder_id=embedder_config.id,
                )
            )
        await insert_embeddings(embeddings)
        # Vector DB ingestion is intentionally lazy and happens during retrieval.

        emb_ms = round((time.perf_counter() - t_emb) * 1000, 2)
        embedding_count = len(embeddings)
        logger.debug(
            "core.process_ingestion.embed_done",
            extra={
                "event": "core.process_ingestion.embed_done",
                "document_id": str(document_id),
                "scan_id": str(scan.id),
                "embedding_count": embedding_count,
                "duration_ms": emb_ms,
            },
        )
    else:
        embedding_count = len(embedded_chunks)
        logger.debug(
            "core.process_ingestion.embed_skip",
            extra={
                "event": "core.process_ingestion.embed_skip",
                "document_id": str(document_id),
                "scan_id": str(scan.id),
                "embedding_count": embedding_count,
            },
        )

    total_ms = round((time.perf_counter() - t0) * 1000, 2)
    logger.debug(
        "core.process_ingestion.complete",
        extra={
            "event": "core.process_ingestion.complete",
            "document_id": str(document_id),
            "rag_config_id": str(rag_config.id),
            "scan_id": str(scan.id),
            "duration_ms": total_ms,
            "ocr_ms": ocr_ms,
            "chunk_ms": ch_ms,
            "embed_ms": emb_ms,
            "chunk_count": len(chunks),
            "embedding_count": embedding_count,
            "scan_cache_hit": scan_cache_hit,
            "chunk_cache_hit": chunk_cache_hit,
            "embed_cache_hit": embed_cache_hit,
        },
    )


async def run_process(rag_config_schema: RAGConfigSchema, dataset_id: UUID):
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    documents = await get_documents_by_dataset(dataset_id)
    doc_count = len(documents)
    t_batch = time.perf_counter()
    logger.debug(
        "core.run_process.start",
        extra={
            "event": "core.run_process.start",
            "dataset_id": str(dataset_id),
            "document_count": doc_count,
        },
    )
    for document in documents:
        await process_ingestion(rag_config_schema, document.id)
    batch_ms = round((time.perf_counter() - t_batch) * 1000, 2)
    logger.info(
        "core.run_process.complete",
        extra={
            "event": "core.run_process.complete",
            "dataset_id": str(dataset_id),
            "document_count": doc_count,
            "duration_ms": batch_ms,
        },
    )


async def run_experiment(
    rag_config_schema: RAGConfigSchema, dataset_id: UUID, experiment_name: str
):
    dataset_obj = await get_dataset(dataset_id)
    if dataset_obj is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    rag_config = await resolve_rag_config(rag_config_schema)
    solver = build_solver(rag_config_schema.solver)

    experiment = await insert_experiment(
        ExperimentORM(
            dataset_id=dataset_id,
            ragconfig_id=rag_config.id,
            name=experiment_name,
            created_at=datetime.now(),
        )
    )
    logger.debug(
        "core.run_experiment.start",
        extra={
            "event": "core.run_experiment.start",
            "dataset_id": str(dataset_id),
            "experiment_id": str(experiment.id),
            "experiment_name": experiment_name,
            "rag_config_id": str(rag_config.id),
        },
    )

    async def task_function_call(*, item, **kwargs):
        question_id = item.metadata["id"]
        question = await get_question(question_id)
        if question is None:
            raise ValueError(f"Question {question_id} not found")
        try:
            answer_text, _chunks = await solver.answer_question(
                question=question,
                llm=build_llm(rag_config_schema.llm),
                embedder=build_embedder(rag_config_schema.embedder),
                rag_config=rag_config_schema,
                dataset_id=dataset_id,
                rag_config_record=rag_config,
            )
            answer = AnswerORM(
                experiment_id=experiment.id,
                question_id=question.id,
                answer=answer_text,
            )
            await insert_answer(answer)
            seen_chunk_ids: set[UUID] = set()
            answer_chunks: list[AnswerChunkORM] = []
            for ch in _chunks:
                chunk_id: UUID = getattr(ch, "chunk_id", ch.id)
                if chunk_id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(chunk_id)
                answer_chunks.append(
                    AnswerChunkORM(
                        answer_id=answer.id,
                        chunk_id=chunk_id,
                        text=ch.text,
                    )
                )
            await insert_answer_chunks(answer_chunks)
        except ValueError:
            raise
        except Exception as e:
            logger.exception(
                "core.run_experiment.question_failed",
                extra={
                    "event": "core.run_experiment.question_failed",
                    "experiment_id": str(experiment.id),
                    "question_id": str(question_id),
                },
            )
            raise RuntimeError(
                f"Failed to answer or store question {question_id}: {e}"
            ) from e
        return answer_text

    langfuse_client = get_langfuse_client()
    dataset = langfuse_client.get_dataset(dataset_obj.name)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_obj.name} - {dataset_id} not found")
    t_exp = time.perf_counter()
    try:
        result = dataset.run_experiment(
            name=experiment_name,
            run_name=experiment_name,
            task=task_function_call,
            max_concurrency=1,
        )
        experiment.dataset_run_id = result.dataset_run_id
        experiment.langfuse_experiment_id = result.experiment_id
        await update_experiment(experiment)
    except Exception:
        logger.exception(
            "core.run_experiment.langfuse_or_persist_failed",
            extra={
                "event": "core.run_experiment.langfuse_or_persist_failed",
                "dataset_id": str(dataset_id),
                "experiment_id": str(experiment.id),
                "experiment_name": experiment_name,
            },
        )
        raise
    exp_ms = round((time.perf_counter() - t_exp) * 1000, 2)
    logger.info(
        "core.run_experiment.complete",
        extra={
            "event": "core.run_experiment.complete",
            "dataset_id": str(dataset_id),
            "experiment_id": str(experiment.id),
            "experiment_name": experiment_name,
            "dataset_run_id": str(result.dataset_run_id)
            if result.dataset_run_id
            else None,
            "langfuse_experiment_id": str(result.experiment_id)
            if result.experiment_id
            else None,
            "duration_ms": exp_ms,
        },
    )

    return experiment
