import asyncio
import json
import time
from typing import List, Dict, Any

import aio_pika
from prometheus_client import Counter, Gauge, Histogram, CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from redis.asyncio import Redis as redis

from src.application.interfaces import AbstractMetricsCollector
from src.logconfig import opt_logger as log

logger = log.setup_logger(name='services')


from src.logconfig import opt_logger as log
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

        # Основной exchange и очередь
        self.default_exchange = await self.channel.declare_exchange(
            name=config.rabbitmq.match_exchange, type="direct"
        )
        main_queue = await self.channel.declare_queue(name=config.rabbitmq.match_queue)
        await main_queue.bind(self.default_exchange, config.rabbitmq.match_queue)

        # Exchange для задержки сообщений
        self.delay_exchange = await self.channel.declare_exchange(
            name="delay_exchange", type="direct"
        )


    async def publish_match_request(self, data: MatchRequest, delay: float = 0.0):
        """ Публикация запроса на поиск партнера в основную очередь """

        await self.connect()

        json_message = json.dumps(data.to_dict()).encode()

        if delay > 0:
            # Используем dead letter exchange для задержки
            # Создаем временную очередь с TTL и dead letter exchange
            delay_queue_name = f"delay_queue_{int(delay)}_{data.user_id}"

            # Объявляем временную очередь с TTL
            delay_queue = await self.channel.declare_queue(
                name=delay_queue_name,
                arguments={
                    "x-message-ttl": int(delay * 1000),  # TTL в миллисекундах
                    "x-dead-letter-exchange": config.rabbitmq.match_exchange,  # Куда отправить после TTL
                    "x-dead-letter-routing-key": config.rabbitmq.match_queue,  # Routing key для основной очереди
                    "x-expires": int(delay * 1000) + 5000  # Очередь удалится через TTL + 5 сек
                }
            )

            # Привязываем delay exchange к delay очереди
            await delay_queue.bind(self.delay_exchange, delay_queue_name)

            # Публикуем в delay exchange, который маршрутизирует в delay очередь
            await self.delay_exchange.publish(
                aio_pika.Message(
                    body=json_message,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=delay_queue_name,  # Routing key совпадает с именем очереди
            )
        else:
            # Публикуем напрямую в основную очередь
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


class PrometheusMetricsCollector(AbstractMetricsCollector):
    """
    Сборщик метрик для Prometheus с фокусом на метрики очереди ожидания
    """

    def __init__(self):
        """
        Инициализация сборщика метрик
        """
        self.redis_client = redis.from_url(config.redis.gateway_url, decode_responses=True)
        self.metrics_key = "worker_service:metrics"
        self.registry = CollectorRegistry()

        # Инициализация метрик
        self._init_metrics()

    def _init_metrics(self):
        """ Инициализировать все метрики """

        # Метрики очереди ожидания
        self.queue_size = Gauge(
            'matching_queue_size',
            'Current size of the matching queue',
            registry=self.registry
        )

        self.queue_wait_time = Histogram(
            'matching_queue_wait_time_seconds',
            'Time users spend waiting in the matching queue',
            buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),  # от 1 сек до 1 часа
            registry=self.registry
        )

        # Метрики попыток матчинга
        self.match_attempts_total = Counter(
            'matching_attempts_total',
            'Total number of matching attempts',
            ['result', 'user_gender', 'criteria_language'],
            registry=self.registry
        )

        self.matches_found_total = Counter(
            'matches_found_total',
            'Total number of successful matches',
            ['compatibility_range', 'processing_time_range'],
            registry=self.registry
        )

        # Метрики совместимости
        self.compatibility_score = Histogram(
            'matching_compatibility_score',
            'Distribution of compatibility scores for found matches',
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=self.registry
        )

        # Метрики производительности
        self.processing_time = Histogram(
            'matching_processing_time_seconds',
            'Time spent processing matching requests',
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self.registry
        )

        self.candidates_evaluated = Histogram(
            'matching_candidates_evaluated',
            'Number of candidates evaluated per matching attempt',
            buckets=(1, 5, 10, 25, 50, 100, 250, 500),
            registry=self.registry
        )

        # Метрики ошибок
        self.errors_total = Counter(
            'matching_errors_total',
            'Total number of errors by type',
            ['error_type', 'user_id_present'],
            registry=self.registry
        )

        # Метрики retry логики
        self.retry_attempts_total = Counter(
            'matching_retry_attempts_total',
            'Total number of retry attempts',
            ['retry_count', 'delay_range'],
            registry=self.registry
        )

        self.retry_delay = Histogram(
            'matching_retry_delay_seconds',
            'Delay between retry attempts',
            buckets=(1, 5, 10, 30, 60, 120, 300),
            registry=self.registry
        )

        # Метрики пользователей
        self.active_users = Gauge(
            'matching_active_users',
            'Number of currently active users in matching process',
            ['status'],  # waiting, matched, timed_out
            registry=self.registry
        )

        # Метрики по критериям поиска
        self.criteria_usage = Counter(
            'matching_criteria_usage_total',
            'Usage statistics for different matching criteria',
            ['criteria_type', 'value'],
            registry=self.registry
        )


    async def record_match_attempt(
        self,
        user_id: int,
        processing_time: float,
        candidates_evaluated: int,
        match_found: bool,
        compatibility_score: float = None
    ) -> None:
        """
        Записать попытку матчинга
        :param user_id: ID пользователя
        :param processing_time: Время обработки в секундах
        :param candidates_evaluated: Количество оцененных кандидатов
        :param match_found: Найден ли матч
        :param compatibility_score: Скор совместимости (если найден)
        """
        try:
            # Записываем время обработки
            self.processing_time.observe(processing_time)

            # Записываем количество оцененных кандидатов
            self.candidates_evaluated.observe(candidates_evaluated)

            # Определяем лейблы для счетчика попыток
            result = 'success' if match_found else 'failure'
            user_gender = 'unknown'  # В будущем можно получать из контекста
            criteria_language = 'unknown'  # В будущем можно получать из контекста

            self.match_attempts_total.labels(
                result=result,
                user_gender=user_gender,
                criteria_language=criteria_language
            ).inc()

            if match_found and compatibility_score is not None:
                # Записываем совместимость
                self.compatibility_score.observe(compatibility_score)

                # Определяем диапазоны для классификации
                if compatibility_score >= 0.8:
                    comp_range = 'high'
                elif compatibility_score >= 0.6:
                    comp_range = 'medium'
                else:
                    comp_range = 'low'

                if processing_time <= 1.0:
                    time_range = 'fast'
                elif processing_time <= 5.0:
                    time_range = 'medium'
                else:
                    time_range = 'slow'

                self.matches_found_total.labels(
                    compatibility_range=comp_range,
                    processing_time_range=time_range
                ).inc()

            # Сохранить метрики в Redis
            await self._save_metrics_to_redis()

        except Exception as e:
            logger.error(f"Error recording match attempt metrics: {e}")
            raise

    async def record_error(self, error_type: str, user_id: int = None) -> None:
        """
        Записать ошибку

        :param error_type: Тип ошибки
        :param user_id: ID пользователя (опционально)
        """
        try:
            user_id_present = 'true' if user_id is not None else 'false'
            self.errors_total.labels(
                error_type=error_type,
                user_id_present=user_id_present
            ).inc()

            await self._save_metrics_to_redis()

        except Exception as e:
            logger.error(f"Error recording error metrics: {e}")

    async def record_queue_size(self, size: int) -> None:
        """
        Записать размер очереди
        :param size: Текущий размер очереди
        """
        try:

            self.queue_size.set(size)

            await self._save_metrics_to_redis()

        except Exception as e:
            logger.error(f"Error recording queue size: {e}")

    async def record_queue_wait_time(self, wait_time: float) -> None:
        """
        Записать время ожидания в очереди
        :param wait_time: Время ожидания в секундах
        """
        try:

            self.queue_wait_time.observe(wait_time)

            await self._save_metrics_to_redis()

        except Exception as e:
            logger.error(f"Error recording queue wait time: {e}")

    async def record_retry_attempt(self, retry_count: int, delay: float) -> None:
        """
        Записать попытку retry
        :param retry_count: Номер попытки retry
        :param delay: Задержка перед следующей попыткой
        """
        try:
            # Классифицируем retry count
            if retry_count <= 1:
                retry_range = '1'
            elif retry_count <= 3:
                retry_range = '2-3'
            else:
                retry_range = '4+'

            # Классифицируем задержку
            if delay <= 5:
                delay_range = 'short'
            elif delay <= 30:
                delay_range = 'medium'
            else:
                delay_range = 'long'

            self.retry_attempts_total.labels(
                retry_count=retry_range,
                delay_range=delay_range
            ).inc()

            self.retry_delay.observe(delay)
            await self._save_metrics_to_redis()

        except Exception as e:
            logger.error(f"Error recording retry metrics: {e}")

    async def record_user_status_change(self, old_status: str, new_status: str) -> None:
        """
        Записать изменение статуса пользователя
        :param old_status: Предыдущий статус
        :param new_status: Новый статус
        """
        try:
            # Уменьшаем счетчик старого статуса
            if old_status:
                self.active_users.labels(status=old_status).dec()

            # Увеличиваем счетчик нового статуса
            self.active_users.labels(status=new_status).inc()
            await self._save_metrics_to_redis()

        except Exception as e:
            logger.error(f"Error recording user status change: {e}")

    async def record_criteria_usage(self, criteria_type: str, value: str) -> None:
        """
        Записать использование критерия поиска
        :param criteria_type: Тип критерия (language, fluency, etc.)
        :param value: Значение критерия
        """
        try:
            self.criteria_usage.labels(
                criteria_type=criteria_type,
                value=str(value)
            ).inc()

            await self._save_metrics_to_redis()

        except Exception as e:
            logger.error(f"Error recording criteria usage: {e}")

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Получить метрики из Redis
        """
        try:
            metrics_data = await self.redis_client.get(self.metrics_key)
            return {
                'prometheus_metrics': metrics_data or '',
                'content_type': CONTENT_TYPE_LATEST,
                'timestamp': time.time()
            }

        except Exception as e:
            logger.error(f"Error fetching metrics from Redis: {e}")
            await self.record_error('metrics_fetch_error')
            return {
                'error': 'Failed to fetch metrics from Redis',
                'timestamp': time.time()
            }


    async def _save_metrics_to_redis(self) -> None:
        """ Сохранить метрики в Redis """
        metrics_data = generate_latest(self.registry).decode('utf-8')
        await self.redis_client.set(self.metrics_key, metrics_data)



    async def get_health_status(self) -> Dict[str, Any]:
        """
        Получить статус здоровья системы на основе метрик
        :returns Словарь со статусом здоровья
        """
        try:
            metrics = await self.get_metrics()

            # Простая логика определения здоровья
            queue_size = metrics.get('queue_size', 0)
            error_rate = 0  # В будущем можно рассчитать на основе ошибок

            health_status = 'healthy'
            if queue_size > 1000:
                health_status = 'warning'
            if error_rate > 0.1:  # 10% ошибок
                health_status = 'critical'

            return {
                'status': health_status,
                'queue_size': queue_size,
                'error_rate': error_rate,
                'timestamp': time.time()
            }

        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {
                'status': 'unknown',
                'error': str(e),
                'timestamp': time.time()
            }
