"""
Import all ORM models so SQLAlchemy sees them on metadata creation.

Alembic's env.py can import this module to ensure `Base.metadata` is populated.
"""

# Dataset models
# Config models
from src.config.ingestion.chunker.models import ChunkerConfigORM  # noqa: F401
from src.config.ingestion.embedder.models import EmbeddingConfigORM  # noqa: F401
from src.config.ingestion.ocr.models import OCRConfigORM  # noqa: F401
from src.config.ingestion.vectordb.models import VectorDBConfigORM  # noqa: F401
from src.config.llms.models import LLMConfigORM  # noqa: F401
from src.config.models import RAGConfigORM  # noqa: F401
from src.config.solver.models import SolverConfigORM  # noqa: F401

# Core artifact + experiment models
from src.core.models import (  # noqa: F401
    AnswerChunkORM,
    AnswerORM,
    ChunkORM,
    EmbeddingORM,
    ExperimentORM,
    ScanORM,
)
from src.dataset.models import (  # noqa: F401
    DatasetORM,
    DocumentORM,
    QuestionORM,
)

# Evals models
