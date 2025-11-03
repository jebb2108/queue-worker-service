import pytest
import time
from src.infrastructure.services import CurcuitBreaker, CircuitBreakerOpenException


@pytest.mark.asyncio
async def test_curcuit_breaker_stops_function_accordingly():
    curcuit_breaker = CurcuitBreaker()

    async def success_func():
        return "success"

    async def fail_func():
        raise ValueError("failure")

    # Успешные вызовы функции держат атрибут state закрытым
    for _ in range(5):
        result = await curcuit_breaker.call(success_func)
        assert result == "success"
        assert curcuit_breaker.state == 'closed'
        assert curcuit_breaker.failure_count == 0

    # Неудачные вызовы функции все еще держат этот атрибут открытым
    for i in range(2):
        with pytest.raises(ValueError):
            await curcuit_breaker.call(fail_func)
        assert curcuit_breaker.state == 'closed'
        assert curcuit_breaker.failure_count == i + 1

    # Треться неудача должна прервать цикличность
    with pytest.raises(ValueError):
        await curcuit_breaker.call(fail_func)
    assert curcuit_breaker.state == 'open'
    assert curcuit_breaker.failure_count == 3

    # Вызовы поднимают исключение CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException):
        await curcuit_breaker.call(success_func)

    # Ждет некоторое время перед обновлением таймера
    time.sleep(6)  # recovery_timeout - 5 секунд

    # Сейчас в half_open, успешный вызов должен закрыть его
    result = await curcuit_breaker.call(success_func)
    assert result == "success"
    assert curcuit_breaker.state == 'closed'
    assert curcuit_breaker.failure_count == 0

    # Заново открывает открытое состояние для прерывания
    for _ in range(3):
        with pytest.raises(ValueError):
            await curcuit_breaker.call(fail_func)
    assert curcuit_breaker.state == 'open'

    # В half_open, неудачный вызов открывает его сразу
    time.sleep(6)
    with pytest.raises(ValueError):
        await curcuit_breaker.call(fail_func)
    assert curcuit_breaker.state == 'open'



