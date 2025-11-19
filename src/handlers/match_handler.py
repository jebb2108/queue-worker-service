import time
from typing import Dict, Any

from faststream.rabbit.annotations import RabbitMessage

from src.application.interfaces import AbstractMetricsCollector, AbstractUnitOfWork
from src.application.use_cases import ProcessMatchRequestUseCase
from src.container import get_container
from src.domain.exceptions import DomainException
from src.domain.value_objects import MatchRequest
from src.infrastructure.services import RateLimiter, CurcuitBreaker
from src.logconfig import opt_logger as log

logger = log.setup_logger(name='use cases')


class MatchRequestHandler:
    """Обработчик запросов на поиск собеседника"""

    def __init__(
            self,
            process_match_use_case: ProcessMatchRequestUseCase,
            metrics_collecter: AbstractMetricsCollector,
            rate_limiter: RateLimiter = None,
            curcuit_breaker: CurcuitBreaker = None
    ):
        self.process_match_use_case = process_match_use_case
        self.metrics = metrics_collecter
        self.curcuit_breaker = curcuit_breaker or CurcuitBreaker()
        self.rate_limiter = rate_limiter or RateLimiter()

    async def handle_message(self, data: Dict[str, Any], msg: RabbitMessage) -> None:
        """ Обрабатывать сообщения с запросом на матчинг """
        start_time = time.time()
        user_id = data.get('user_id', 0)

        logger.info("Message received w/ user %s", data.get('user_id'))

        try:
            # Валидация входящих данных
            if not self._validate_message(data):
                return await msg.ack()

            # Проверка на задержку времени
            if not await self.rate_limiter.is_allowed(
                    key=f'user_{data.get('user_id', 0)}'
            ):
                await msg.nack()
                return

            # Создание объекта запроса
            try:
                match_request = MatchRequest.from_dict(data)
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to create MatchRequest from data: {e}")
                await msg.ack()
                return

            # Безопасная обработка запроса с прерыванием циклического замыкания
            success = await self.curcuit_breaker.call(
                self._process_request_safely, match_request
            )

            if success:
                await msg.ack()
                return

            else:
                # Записать метрики
                logger.warning(f"Failed to process match request for user {user_id}")
                processing_time = time.time() - start_time
                await self.metrics.record_match_attempt(
                    user_id, processing_time, 0, success
                )
                await msg.nack()
                return

        except Exception as e:
            logger.error(f"Critical error processing match request: {e}")
            await self.metrics.record_error('critical_processing_error', user_id)
            await msg.nack()

    async def _process_request_safely(self, match_request: MatchRequest):
        """ Безопасная обработка запроса с обработкой исключений """
        try:
            container = await get_container()
            unit_of_work = await container.get(AbstractUnitOfWork)
            logger.debug(f"Starting to process match request for user {match_request.user_id}")
            result = await self.process_match_use_case.execute(match_request, unit_of_work)
            logger.debug(f"Successfully processed match request for user {match_request.user_id}, result: {result}")
            return result

        except DomainException as e:
            # Доменные исключения - логируем как предупреждения
            logger.warning(f"Domain error processing request for user {match_request.user_id}: {e}")
            await self.metrics.record_error('domain_error', match_request.user_id)
            return False

        except Exception as e:
            # Неожиданные исключения - логируем как ошибки
            logger.error(f"Unexpected error processing request for user {match_request.user_id}: {e}")
            await self.metrics.record_error('unexpected_error', match_request.user_id)
            raise # Перебрасываем для circuit breaker

    @staticmethod
    def _validate_message(message: Dict[str, Any]) -> bool:
        """ Валидация структуры сообщения """

        required_fields = [
            'user_id', 'username', 'gender', 'criteria',
            'lang_code', 'created_at'
        ]

        # Проверить наличие обязателльных ключей
        for field in required_fields:
            if field not in message:
                return False

        # Проверить структуру критерием
        criteria = message.get('criteria')
        if not isinstance(criteria, dict):
            return False

        criteria_fields = ['language', 'fluency', 'topics', 'dating']
        for field in criteria_fields:
            if field not in criteria:
                return False

        # Проверить типы данных
        try:
            int(message.get('user_id'))
            int(criteria.get('fluency'))


            valid_dating = True if isinstance(criteria.get('dating'), bool) else \
                    criteria.get('dating').lower() in ['true', 'false']

            if not valid_dating:
                return False

            if not isinstance(criteria.get('topics'), list):
                return False

        except (ValueError, TypeError):
            return False

        return True


