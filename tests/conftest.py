import pytest

from src.application.use_cases import ProcessMatchRequestUseCase
from src.container import get_container

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
async def message_handler():
    from src.handlers.match_handler import MatchRequestHandler
    from src.infrastructure.services import PrometheusMetricsCollector, RateLimiter, CurcuitBreaker
    container = await get_container()
    process_match_handler = await container.get(ProcessMatchRequestUseCase)
    metrics_handler = PrometheusMetricsCollector()
    rate_limiter, curcuit_breaker = RateLimiter(), CurcuitBreaker()
    return MatchRequestHandler(process_match_handler, metrics_handler, rate_limiter, curcuit_breaker)


@pytest.fixture
def metrics_collector():
    """Фикстура для создания экземпляра PrometheusMetricsCollector"""
    return PrometheusMetricsCollector()



