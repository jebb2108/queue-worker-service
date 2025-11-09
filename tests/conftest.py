import pytest

from src.infrastructure.services import PrometheusMetricsCollector


@pytest.fixture
async def container():
    """ Фикстура для создания тестового контейнера """
    from src.container import ServiceContainer
    container = ServiceContainer()

    await container.initialise()

    yield container

    # Очистка после теста
    await container.cleanup()


@pytest.fixture
async def factory():
    """ Фикстура для создания тестовой фабрики """
    from src.container import ServiceFactory
    return ServiceFactory()


@pytest.fixture
def metrics_collector():
    """Фикстура для создания экземпляра PrometheusMetricsCollector"""
    return PrometheusMetricsCollector()



