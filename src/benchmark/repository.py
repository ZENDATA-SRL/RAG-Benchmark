from uuid import UUID

from benchmark.models import Benchmark, Document, Question


async def get_document(document_id: UUID) -> Document | None:
    pass


async def find_document_by_name_and_url(name: str, url: str, benchmark_id: UUID) -> Document | None:
    pass


async def insert_document(document: Document) -> None:
    pass

async def get_benchmark(benchmark_id: UUID) -> Benchmark | None:
    pass

async def get_question(question_id: UUID) -> Question | None:
    pass

async def insert_benchmark(benchmark: Benchmark) -> None:
    pass


async def insert_question(question: Question) -> None:
    pass
