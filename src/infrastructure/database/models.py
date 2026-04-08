"""
Import all ORM models so SQLAlchemy sees them on metadata creation.

Alembic's env.py can import this module to ensure `Base.metadata` is populated.
"""

# Config models
from config.ingestion.chunker.models import ChunkerConfigORM  # noqa: F401
from config.ingestion.embedder.models import EmbeddingConfigORM  # noqa: F401
from config.ingestion.ocr.models import OCRConfigORM  # noqa: F401
from config.llms.models import LLMConfigORM  # noqa: F401
from config.models import RAGConfigORM  # noqa: F401
from config.solver.models import SolverConfigORM  # noqa: F401

# Core + benchmark models
from benchmark.models import BenchmarkORM, DocumentORM, QuestionORM  # noqa: F401
from core.models import ChunkORM, EmbeddingORM, ScanORM  # noqa: F401

