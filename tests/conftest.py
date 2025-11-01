import pytest

from src.application.use_cases import ProcessMatchRequestUseCase
from src.container import ServiceContainer, ServiceFactory
from src.handlers.match_handler import MatchRequestHandler


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
def message_handler():
    return MatchRequestHandler(ProcessMatchRequestUseCase())
