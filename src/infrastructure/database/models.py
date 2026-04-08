"""
Import all ORM models so SQLAlchemy sees them on metadata creation.

Alembic's env.py can import this module to ensure `Base.metadata` is populated.
"""

# Dataset models (includes scan/chunk/embedding artifacts)
from src.dataset.models import (  # noqa: F401
    ChunkORM,
    DatasetORM,
    DocumentORM,
    EmbeddingORM,
    QuestionORM,
    ScanORM,
)

# Config models
from src.config.ingestion.chunker.models import ChunkerConfigORM  # noqa: F401
from src.config.ingestion.embedder.models import EmbeddingConfigORM  # noqa: F401
from src.config.ingestion.ocr.models import OCRConfigORM  # noqa: F401
from src.config.llms.models import LLMConfigORM  # noqa: F401
from src.config.models import RAGConfigORM  # noqa: F401
from src.config.solver.models import SolverConfigORM  # noqa: F401
