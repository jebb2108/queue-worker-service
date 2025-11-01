import pytest

from src.application.use_cases import ProcessMatchRequestUseCase, FindMatchUseCase
from src.container import ServiceContainer, ServiceFactory, get_container
from src.handlers.match_handler import MatchRequestHandler
from src.infrastructure.repositories import DatabaseMatchRepository, RedisUserRepository, PostgresSQLMatchRepository, \
    MemoryStateRepository
from src.infrastructure.services import RabbitMQMessagePublisher


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
async def message_handler():
    # return MatchRequestHandler(ProcessMatchRequestUseCase())
    container = await get_container()
    process_match_request_use_case = await container.get(ProcessMatchRequestUseCase)
    return MatchRequestHandler(process_match_request_use_case)


