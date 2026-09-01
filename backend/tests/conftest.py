from __future__ import annotations

import dataclasses
import io
from collections.abc import AsyncGenerator
from typing import IO, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from src.infrastructure.temporal import StartedWorkflow
from src.settings import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Application settings, read from the same `.env` the app uses."""
    return get_settings()


@pytest_asyncio.fixture
async def engine(settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """Engine bound to the dedicated test database.

    Per-test and with `NullPool` on purpose: pytest-asyncio gives each test its own event
    loop, and an asyncpg connection cannot be shared across loops. Pooling here would leak
    a connection from one loop into the next test and fail with "another operation is in
    progress".

    A separate database and not a separate schema: the migration creates PostgreSQL ENUM
    types, which are database-wide, so sharing one with the development data would let a
    test teardown break the dev environment.
    """
    created = create_async_engine(settings.test_database_url, poolclass=NullPool)
    try:
        async with created.connect():
            pass
    except Exception as error:  # pragma: no cover - environment problem, not a test failure
        await created.dispose()
        pytest.skip(f"test database not reachable: {error}")
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def connection(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """Open a connection with an outer transaction that is always rolled back."""
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture
async def session(connection: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    """Session joined to the test transaction.

    Everything the test writes is discarded by the outer rollback, so tests neither need
    cleanup code nor see each other's rows, even when the code under test commits: the
    commit only releases the nested transaction, never the outer one.
    """
    factory = async_sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)
    async with factory() as test_session:
        yield test_session


class FakeObjectStorage:
    """In-memory `ObjectStorage`, so upload tests exercise the orchestration and not boto3.

    `fail_on_keys` reproduces a storage backend that refuses a write, which is the only way
    to test that a document ends up `failed` without breaking the rest of the batch.
    """

    def __init__(self, bucket: str = "test-bucket") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.fail_on_keys: set[str] = set()
        self.put_calls: list[str] = []

    def put_stream(self, key: str, stream: IO[bytes], content_type: str) -> str:
        self.put_calls.append(key)
        if key in self.fail_on_keys:
            raise RuntimeError("storage unavailable")
        self.objects[key] = stream.read()
        self.content_types[key] = content_type
        return self.build_uri(key)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        self.put_calls.append(key)
        if key in self.fail_on_keys:
            raise RuntimeError("storage unavailable")
        self.objects[key] = data
        self.content_types[key] = content_type
        return self.build_uri(key)

    def get_stream(self, key: str) -> IO[bytes]:
        return io.BytesIO(self.objects[key])

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def build_uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"


@pytest.fixture
def fake_storage() -> FakeObjectStorage:
    """Fresh in-memory storage for one test."""
    return FakeObjectStorage()


@dataclasses.dataclass(frozen=True)
class StartedCall:
    """One recorded launch, so a test can assert what would have reached Temporal."""

    workflow: str
    arg: Any
    workflow_id: str
    task_queue: str


class FakeWorkflowClient:
    """In-memory `WorkflowClient`, so API tests need no Temporal server.

    Records every launch, and reproduces the one behaviour the API depends on: a second
    start with an id already running reports `started=False` instead of raising, which is
    how Temporal's duplicate-id rejection reaches the caller (RT-O01). The real workflows
    are covered by `temporal/tests`.
    """

    def __init__(self) -> None:
        self.started: list[StartedCall] = []
        self.cancelled: list[str] = []
        self._running: set[str] = set()

    async def start(
        self, workflow: str, *, arg: Any, workflow_id: str, task_queue: str
    ) -> StartedWorkflow:
        self.started.append(
            StartedCall(
                workflow=workflow, arg=arg, workflow_id=workflow_id, task_queue=task_queue
            )
        )
        if workflow_id in self._running:
            return StartedWorkflow(workflow_id=workflow_id, started=False)
        self._running.add(workflow_id)
        return StartedWorkflow(workflow_id=workflow_id, started=True)

    async def cancel(self, workflow_id: str) -> bool:
        self.cancelled.append(workflow_id)
        was_running = workflow_id in self._running
        self._running.discard(workflow_id)
        return was_running


@pytest.fixture
def fake_workflows() -> FakeWorkflowClient:
    """Fresh in-memory workflow client for one test."""
    return FakeWorkflowClient()


@pytest_asyncio.fixture
async def client(
    session: AsyncSession,
    fake_storage: FakeObjectStorage,
    fake_workflows: FakeWorkflowClient,
) -> AsyncGenerator[AsyncClient, None]:
    """`AsyncClient` on the app, with the session dependency bound to the test transaction."""
    from src.dependencies import get_storage, get_workflows
    from src.infrastructure.database.session import get_session
    from src.main import create_app

    app = create_app()
    # Built without running `lifespan`, so the startup seed does not fire: a test that
    # needs the registry seeds it explicitly and the others start from an empty table.
    app.dependency_overrides[get_session] = lambda: session
    # Storage is faked so an API test neither needs MinIO nor leaves objects behind; the
    # real client is exercised end to end by `test_storage.py`.
    app.dependency_overrides[get_storage] = lambda: fake_storage
    # Temporal likewise: the API test asserts what would have been launched, the workflow
    # itself is covered by `temporal/tests`.
    app.dependency_overrides[get_workflows] = lambda: fake_workflows

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client

