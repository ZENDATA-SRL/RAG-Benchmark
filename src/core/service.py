## Here I will perform the ingestion of documents. I will have as inputs files that I will process based on the config

# I will load the config from db with the selected id and, with each field of the config I will instantiate the corresponding class


from datetime import datetime
from uuid import UUID

from langfuse import get_client

from src.config.ingestion.chunker.service import build_chunker, get_chunker_by_id
from src.config.ingestion.embedder.service import build_embedder, get_embedder_by_id
from src.config.ingestion.ocr.service import build_ocr, get_ocr_by_id
from src.config.llms.service import build_llm
from src.config.schemas import RAGConfigSchema
from src.config.service import resolve_rag_config
from src.config.solver.service import build_solver
from src.core.models import AnswerORM, ChunkORM, EmbeddingORM, ExperimentORM, ScanORM
from src.core.repository import (
    get_chunks as get_chunks_orm,
)
from src.core.repository import (
    get_embeddings as get_embeddings_orm,
)
from src.core.repository import (
    get_experiments as get_experiments_orm,
)
from src.core.repository import (
    get_scan as get_scan_orm,
)
from src.core.repository import (
    insert_answer,
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
from src.core.schemas import Chunk, Embedding, Experiment, Scan
from src.dataset.repository import get_dataset, get_document, get_question
from src.infrastructure.blob_storage.blob import get_blob_from_url


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


async def run_process(rag_config_schema: RAGConfigSchema, dataset_id: UUID):
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    for document in dataset.documents:
        await process_ingestion(rag_config_schema, document.id)


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

    async def task_function_call(*, item, **kwargs):
        question_id = item.metadata["id"]
        question = await get_question(question_id)
        if question is None:
            raise ValueError(f"Question {question_id} not found")
        answer_text = await solver.answer_question(
            question=question,
            llm=build_llm(rag_config_schema.llm),
            embedder=build_embedder(rag_config_schema.embedder),
            solver_config=rag_config_schema.solver,
        )
        answer = AnswerORM(
            experiment_id=experiment.id,
            question_id=question.id,
            answer=answer_text,
        )

        await insert_answer(answer)
        return answer_text

    langfuse_client = get_client()
    dataset = langfuse_client.get_dataset(dataset_obj.name)
    if dataset is None:
        raise ValueError(f"Dataset {dataset_obj.name} - {dataset_id} not found")
    result = dataset.run_experiment(
        name=experiment_name, task=task_function_call, max_concurrency=1
    )
    experiment.dataset_run_id = result.dataset_run_id
    experiment.langfuse_experiment_id = result.experiment_id
    await update_experiment(experiment)

    return experiment
