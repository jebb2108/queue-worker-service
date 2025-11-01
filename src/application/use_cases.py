from typing import Optional

from src.application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository,
    AbstractMessagePublisher
)
from src.domain.entities import Match
from src.domain.value_objects import MatchRequest


class FindMatchUseCase:
    """ Use case для поиска матча """

    def __init__(
        self,
        user_repository: AbstractUserRepository,
        match_repository: AbstractMatchRepository,
        state_repository: AbstractStateRepository,
    ):
        self.user_repository = user_repository,
        self.match_repository = match_repository,
        self.state_repository = state_repository

    async def execute(self, user_id: int) -> Optional[Match]:
        pass


class ProcessMatchRequestUseCase:
    """ Use case для обработки запросов на матчинг """

    def __init__(
        self,
        find_match_use_case: FindMatchUseCase,
        state_repository: AbstractStateRepository,
        message_publisher: AbstractMessagePublisher
    ):

        self.find_match_use_case = find_match_use_case
        self.state_repository = state_repository
        self.message_publisher = message_publisher

    async def execute(self, request: MatchRequest):
        """ Обработать запрос на матчинг """
        try:
            #  Проверить состояние пользователя
            should_process = await self._should_process(request)

            if not should_process:
                return True # Запрос обработан (отклонен или отложен)

            if await self._should_delay_processing(request):
                await self._schedule_retry(request)
                return True

            # поаытаться найти матч
            match = self.find_match_use_case.execute(request.user_id)

            if match:
                #  Матч найден, обработка завершена
                return True

            # Матч не найден, проверить лимиты и запланировать повтор
            return self._handle_no_match(request)

        except Exception as e:
            # В случае ошибки отправляем в dead letter queue
            await self.message_publisher.publish_to_dead_letter(
                request.to_dict(),
                f"Processing error: {str(e)}"
            )
            return False


    async def _should_process(self, request):
        return True

    async def _should_delay_processing(self, request):
        return True

    async def _schedule_retry(self, request):
        return True
