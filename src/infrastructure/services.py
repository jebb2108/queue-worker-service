import asyncio
import json
import time
from typing import List, Dict

import aio_pika

from logconfig import opt_logger as log
from src.config import config
from src.domain.value_objects import MatchRequest

logger = log.setup_logger(name='match_endpoints')


class CircuitBreakerOpenException(Exception):
    pass


class RateLimiter:

    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # key_id -> list of timestamps

    async def is_allowed(self, key_id=None):
        """Check if request is allowed for the given key_id (or global if None)"""
        import time
        current_time = time.time()
        key = key_id or 'global'

        if key not in self.requests:
            self.requests[key] = []

        # Remove old requests outside the window
        self.requests[key] = [t for t in self.requests[key] if current_time - t < self.window_seconds]

        if len(self.requests[key]) < self.max_requests:
            self.requests[key].append(current_time)
            return True
        return False


class CurcuitBreaker:
    """ Класс для прерывания циклических операций """
    def __init__(self, failure_threshold=3, recovery_timeout=5):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half_open

    async def call(self, func, *args, **kwargs):
        if self.state == 'open':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'half_open'
            else:
                raise CircuitBreakerOpenException("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            if self.state == 'half_open':
                self.state = 'closed'
            self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = 'open'
                self.last_failure_time = time.time()
            raise e


class RabbitMQMessagePublisher:
    """ Класс для отправки сообщений в очередь ожидания """
    def __init__(self):
        self._initialized = False

    async def connect(self):
        """ Установка подключения к RabbitMQ """
        if self._initialized:
            return

        self.connection = await aio_pika.connect_robust(config.rabbitmq.url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=1)
        self._initialized = True

        # Объявляем обменники и очереди при подключении
        await self.declare_exchanges_and_queues()

    async def declare_exchanges_and_queues(self):
        """ Объявление всех обменников и очередей """

        self.default_exchange = await self.channel.declare_exchange(
            name=config.rabbitmq.match_exchange, type="direct"
        )
        main_queue = await self.channel.declare_queue(name=config.rabbitmq.match_queue)
        await main_queue.bind(self.default_exchange, config.rabbitmq.match_queue)


    async def publish_match_request(self, data: MatchRequest, delay: float = 0.0):
        """ Публикация запроса на поиск партнера в основную очередь """

        await self.connect()

        json_message = json.dumps(data.to_dict()).encode()

        if delay > 0:
            # Используем delayed exchange или dead letter exchange для задержки
            # Для простоты используем asyncio.sleep, но в продакшене лучше использовать RabbitMQ delayed message plugin
            await asyncio.sleep(delay)

        await self.default_exchange.publish(
            aio_pika.Message(
                body=json_message, delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=config.rabbitmq.match_queue,
        )

    async def publish_to_dead_letter(self, data: MatchRequest, err_msg: str):
        await self.connect()
        return


    async def disconnect(self):
        """Закрытие подключения"""
        if self.connection:
            await self.connection.close()


class RateLimiter:
    """ Ограничитель частоты запросов для предотвращения злоупотреблений """

    def __init__(self, max_requests: int = 3, time_window: int = 1):
        """
        Инициализация ограничителя частоты
        :param max_requests: Максимальное количество запросов в окне времени
        :param time_window: Окно времени в секундах
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self._requests: Dict[str, List[time.time]] = {}  # key -> list of timestamps

    async def is_allowed(self, key: str) -> bool:
        """
        Проверяет, разрешен ли запрос для данного пользователя
        :param key: Идентификатор пользователя
        :returns  True если запрос разрешен, False если превышен лимит
        """
        import time
        current_time = time.time()

        # Инициализируем список для нового пользователя
        if key not in self._requests:
            self._requests[key] = []

        # Очищаем старые запросы вне окна времени
        self._requests[key] = [
            timestamp for timestamp in self._requests[key]
            if current_time - timestamp < self.time_window
        ]

        # Проверяем лимит
        if len(self._requests[key]) < self.max_requests:
            self._requests[key].append(current_time)
            return True
        else:
            return False
