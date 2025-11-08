import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from src.application.use_cases import ProcessMatchRequestUseCase
from src.config import config
from src.container import ServiceContainer, ServiceFactory, get_container
from src.handlers.match_handler import MatchRequestHandler
from src.infrastructure.services import PrometheusMetricsCollector


@pytest.fixture
async def container():
    """ Фикстура для создания тестового контейнера """
    container = ServiceContainer()

    await container.initialise()

    yield container

    # Очистка после теста
    await container.cleanup()


@pytest.fixture
async def factory():
    """ Фикстура для создания тестовой фабрики """
    return ServiceFactory()


@pytest.fixture
def metrics_collector():
    """Фикстура для создания экземпляра PrometheusMetricsCollector"""
    return PrometheusMetricsCollector()

@pytest.fixture
async def engine():
    from src.infrastructure.orm import start_mappers, metadata
    engine = create_async_engine(url="postgresql+asyncpg://")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    start_mappers()

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)


@pytest.fixture
async def session(engine):
    async with AsyncSession(engine) as session:
        yield session

@pytest.fixture
async def message_handler(metrics_collector):
    # return MatchRequestHandler(ProcessMatchRequestUseCase())
    container = await get_container()
    process_match_request_use_case = await container.get(ProcessMatchRequestUseCase)
    return MatchRequestHandler(process_match_request_use_case, metrics_collector)





