from typing import Dict, Any

from faststream.rabbit.annotations import RabbitMessage

from logconfig import opt_logger as log
from src.application.use_cases import ProcessMatchRequestUseCase
from src.domain.exceptions import DomainException
from src.domain.value_objects import MatchRequest
from src.infrastructure.services import RateLimiter, CurcuitBreaker

logger = log.setup_logger(name='match_handler')


class MatchRequestHandler:
    """Обработчик запросов на поиск собеседника"""

    def __init__(
            self,
            process_match_use_case: ProcessMatchRequestUseCase,
            rate_limiter: RateLimiter = None,
            curcuit_breaker: CurcuitBreaker = None
    ):
        self.process_match_use_case = process_match_use_case
        self.curcuit_breaker = curcuit_breaker or CurcuitBreaker()
        self.rate_limiter = rate_limiter or RateLimiter()

    async def handle_message(self, data: Dict[str, Any], msg: RabbitMessage) -> None:
        """ Обрабатывать сообщения с запросом на матчинг """

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

            logger.debug('Success data after processing: %s', success)

            if success:
                await msg.ack()
                return
            else:
                await msg.nack()
                return

        except Exception as e:
            logger.critical(f"Critical error processing match request: {e}")
            await msg.nack()

    async def _process_request_safely(self, match_request: MatchRequest):
        try:

            return await self.process_match_use_case.execute(match_request)

        except DomainException:
            return False
        except Exception as e:
            logger.error(f"Error while safe processing message: {e}")

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


