import pytest

from ..container import ServiceContainer, ServiceFactory


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
