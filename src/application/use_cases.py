import time
from datetime import datetime
from typing import Optional, List

from src.logconfig import opt_logger as log
from src.application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository,
    AbstractMessagePublisher, AbstractMetricsCollector, AbstractUnitOfWork
)
from src.config import config
from src.domain.entities import Match, User, ScoredCandidate
from src.domain.exceptions import UserNotFoundException, MatchingException
from src.domain.value_objects import MatchRequest, UserStatus, UserState

logger = log.setup_logger(name='use cases')


class FindMatchUseCase:
    """ Use case для поиска матча """

    def __init__(
        self,
        user_repository: AbstractUserRepository,
        match_repository: AbstractMatchRepository,
        state_repository: AbstractStateRepository,
        metrics_collector: AbstractMetricsCollector
    ):
        self.user_repo = user_repository
        self.match_repo = match_repository
        self.state_repo = state_repository
        self.metrics = metrics_collector

    async def execute(self, user_id: int) -> Optional[Match]:
        """Выполнить поиск матча для пользователя"""
        start_time = time.time()
        try:
            logger.debug(f"Starting match search for user {user_id}")
            # Получить пользователя
            user = await self.user_repo.find_by_id(user_id)
            if not user:
                logger.error(f"User {user_id} not found in repository")
                raise UserNotFoundException(f"User {user_id} not found")

            logger.debug(f"User {user_id} found, searching for compatible users")
            # Найти совместимых кандидатов
            candidates = await self.user_repo.find_compatible_users(user)
            candidates_evaluated = len(candidates)
            logger.debug(f"Found {candidates_evaluated} compatible candidates for user {user_id}")

            # Записать размер очереди
            queue_size = await self.user_repo.get_queue_size()
            await self.metrics.record_queue_size(queue_size)
            logger.debug(f"Queue size: {queue_size}")

            if not candidates:
                logger.debug(f"No candidates found for user {user_id}")
                await self.metrics.record_match_attempt(
                    user_id, time.time() - start_time, candidates_evaluated, False
                )
                return None

            # Выбрать лучшего кандидата
            best_candidate = await self._select_best_candidate(user, candidates)
            logger.debug(f"Best candidate for user {user_id}: {best_candidate.candidate.user_id if best_candidate else None}")

            if not best_candidate:
                await self.user_repo.release_reservations([c.user_id for c in candidates])
                await self.metrics.record_match_attempt(
                    user_id, time.time() - start_time, candidates_evaluated, False
                )
                return None

            # Очищаем из резерва IDs текущего участника и партнера
            await self.user_repo.release_reservations([user_id, best_candidate.candidate.user_id])

            # Создать матч
            match = Match.create(
                user, best_candidate.candidate, best_candidate.score.total_score
            )
            logger.debug(f"Match created for users {user_id} and {best_candidate.candidate.user_id}")

            # Записать метрики
            await self.metrics.record_match_attempt(
                user_id, time.time() - start_time, candidates_evaluated,
                True, match.compatibility_score
            )

            # Освободить резервации остальных кандидатов
            other_candidates = [
                c.user_id for c in candidates if
                c.user_id != best_candidate.candidate.user_id
            ]
            if other_candidates:
                await self.user_repo.release_reservations(other_candidates)

            return match

        except Exception as e:
            logger.error(f"Exception in FindMatchUseCase for user {user_id}: {e}")
            await self.metrics.record_error('match_search_error', user_id)
            raise MatchingException(f"Error finding match for user {user_id}: {str(e)}")


    async def _select_best_candidate(self, user: User, candidates: List[User]) -> Optional[ScoredCandidate]:
        """Выбрать лучшего кандидата из списка"""
        if not candidates:
            return None

        # Рассчитать скоры для всех кандидатов
        scored_candidates = []

        for candidate in candidates:
            try:
                score = user.calculate_compatibility_score(
                    candidate,
                    config.matching.scoring_weights
                )

                if score.total_score >= config.matching.compatibility_threshold:
                    scored_candidates.append(ScoredCandidate(candidate, score))

            except Exception as e:
                # Логируем ошибку, но продолжаем с другими кандидатами
                await self.metrics.record_error('scoring_error', candidate.user_id)
                logger.error(f"Error while picking best candidates: {e}")
                continue

        if not scored_candidates:
            return None

        # Сортировать по скору и вернуть лучшего
        scored_candidates.sort(reverse=True)
        return scored_candidates[0]



class ProcessMatchRequestUseCase:
    """ Use case для обработки запросов на матчинг """

    def __init__(
        self,
        find_match_use_case: FindMatchUseCase,
        message_publisher: AbstractMessagePublisher,
        redis_repo: AbstractUserRepository,
        state_repo: AbstractStateRepository,
        unit_of_work: AbstractUnitOfWork,
        metrics_collector: AbstractMetricsCollector
    ):

        self.find_match_use_case = find_match_use_case
        self.message_publisher = message_publisher
        self.redis_repo = redis_repo
        self.state_repo = state_repo
        self.uow = unit_of_work
        self.metrics = metrics_collector


    async def execute(self, request: MatchRequest):
        """ Обработать запрос на матчинг """
        try:
            logger.debug(f"Processing match request for user {request.user_id}")

            #  Проверить состояние пользователя
            should_process = await self._should_process_request(request)
            logger.debug(f"Should process request for user {request.user_id}: {should_process}")

            if not should_process:
                logger.debug("Request either proccessed or rejected")
                return True # Запрос обработан (отклонен или отложен)

            if await self._should_delay_processing(request):
                logger.debug(f"Delaying processing for user {request.user_id}")
                await self._schedule_retry(request)
                logger.debug('Msg after scheduled retry processed')
                return True

            async with (self.uow): # обеспечивает атомарность
                logger.info(f"Entering UoW for user {request.user_id}")

                # поаытаться найти матч
                match: Match = await self.find_match_use_case.execute(request.user_id)
                logger.info(f"Match result for user {request.user_id}: {match is not None}")

                if match:
                    # Сохраняет матч в репозиторий
                    res = await self.uow.matches.list()
                    logger.debug(f"All matches rn: {res}")
                    await self.uow.matches.add(match)
                    # Сверяет версии БД и UoW, чтобы исключить параллелизм
                    try:
                        current_version = await self.uow.matches.version()
                        logger.info(f"Version check for user {request.user_id}: current={current_version}, expected={self.uow.db_version + 1}")
                        if current_version == self.uow.db_version + 1:
                            # Производит фианльный комит в БД
                            await self.uow.commit()
                            # Сохраняет изменения в репозиториях
                            user_ids = [match.user1.user_id, match.user2.user_id]
                            await self.uow.update(user_ids, UserStatus.MATCHED)
                            logger.debug(f"Match committed for user {request.user_id}")
                            return True  # Матч найден, обработка завершена
                        else:
                            # Пессемистичный сценарий параллелизма,
                            # при котором никакие изменения в БД не записываются
                            self.uow.db_version = current_version
                            logger.warning(f"Version mismatch for user {request.user_id}, rolling back")
                    except Exception as e:
                        # В случае ошибки при работе с версиями, откатываем транзакцию
                        logger.error(f"Version check error for user {request.user_id}: {e}")
                        raise

            # Матч не найден, проверить лимиты и запланировать повтор
            logger.debug(f"No match found for user {request.user_id}, handling no match")
            return await self._handle_no_match(request)

        except Exception as e:
            logger.error(f"Exception in ProcessMatchRequestUseCase for user {request.user_id}: {e}")
            await self.metrics.record_error('request_processing_error', request.user_id)
            # В случае ошибки отправляем в dead letter queue
            await self.message_publisher.publish_to_dead_letter(
                request.to_dict(), # noqa
                f"Processing error: {str(e)}"
            )
            return False


    async def _should_process_request(self, request: MatchRequest):
        """ Определить, следует ли обрабатывать запрос """
        logger.debug(f"Checking if should process request for user {request.user_id}")

        # Проверить статус запроса
        if request.status in [config.SEARCH_CANCELED, config.SEARCH_COMPLETED]:
            logger.debug(f"Request for user {request.user_id} is canceled or completed")
            # Запрос отменен или завершен
            await self._cleanup_user_state(request.user_id)
            return False

        # Получить состояние пользователя
        state = await self.state_repo.get_state(request.user_id)
        logger.debug(f"State for user {request.user_id}: {state}")

        if state:

            logger.debug(
                "user id: %s, their state: %s",
                state.user_id, state.status
            )

            # Проверить, не истек ли запрос
            if state.is_expired(config.matching.max_wait_time):
                logger.debug(f"Request for user {request.user_id} has expired")
                await self._handle_timeout(request.user_id, state)
                return False

            # Проверить, не обработан ли запрос
            is_searching = await self.redis_repo.is_searching(request.user_id)
            logger.debug(f"User {request.user_id} is_searching: {is_searching}, state.status: {state.status}")
            if not is_searching and state.status == UserStatus.MATCHED:
                logger.debug(f"Request for user {request.user_id} already processed")
                return False

        else:
            logger.debug(f"Creating new state for user {request.user_id}")
            new_state = UserState(
                user_id=request.user_id,
                status=UserStatus.WAITING,
                created_at=time.time()
            )
            await self.state_repo.save_state(new_state)

        return True


    @staticmethod
    async def _should_delay_processing(request: MatchRequest):
        """Определить, нужно ли отложить обработку"""
        elapsed = datetime.now(tz=config.timezone) - request.created_at
        return elapsed.total_seconds() < config.matching.initial_delay  # 5 секунд

    async def _schedule_retry(self, request, delay: float = None) -> None:
        """Запланировать повторную обработку"""
        if delay is None:
            elapsed = datetime.now(tz=config.timezone) - request.created_at
            delay = max(0, config.matching.initial_delay - elapsed.total_seconds())

        # Обновить время для повтора
        updated_request = MatchRequest(
            user_id=request.user_id,
            username=request.username,
            criteria=request.criteria,
            gender=request.gender,
            lang_code=request.lang_code,
            status=request.status,
            created_at=request.created_at,
            current_time=datetime.now(tz=config.timezone),
            source=request.source,
            retry_count=request.retry_count
        )

        await self.message_publisher.publish_match_request(updated_request, delay)

    async def _handle_no_match(self, request: MatchRequest):
        """ Обработать случаи, когда матч не найден"""

        # Проверить лимиты времени и попыток
        elapsed = datetime.now(tz=config.timezone) - request.created_at
        if elapsed.total_seconds() >= config.matching.max_wait_time or \
                request.retry_count >= config.matching.max_retries:
            # Превышены лимиты, уведомить о таймауте
            await self._handle_timeout(request.user_id, None, elapsed.total_seconds())
            return True


        # Применить ослабление критериев и запланировать повтор
        await self._relax_criteria_and_retry(request)
        return True

    async def _relax_criteria_and_retry(self, request: MatchRequest):
        """ Ослабить критерии и запланировать повтор """

        # Ослабить критерии на основое количества повторов
        relaxed_criteria = request.criteria.relax(request.retry_count)

        if request.retry_count in [3, 5, 8]:
            logger.debug("Criteria for user %s relaxed", request.user_id)

        # Создать новый запрос с ослабленными критериями
        updated_request = MatchRequest(
            user_id=request.user_id,
            username=request.username,
            criteria=relaxed_criteria,
            gender=request.gender,
            lang_code=request.lang_code,
            status=request.status,
            created_at=request.created_at,
            current_time=datetime.now(tz=config.timezone),
            source=request.source,
            retry_count=request.retry_count + 1
        )

        # Обновить критерии в репозитории
        await self.find_match_use_case.user_repo.update_user_criteria(
            request.user_id,
            {
                'language': relaxed_criteria.language,
                'fluency': relaxed_criteria.fluency,
                'topics': relaxed_criteria.topics,
                'dating': relaxed_criteria.dating
            }
        )

        # Запланировать повтор с задержкой
        delay = min(30.0, 2.0 * (updated_request.retry_count + 1)) # Линейная задержка
        await self.message_publisher.publish_match_request(updated_request, delay)

        # Записать метрику retry
        await self.metrics.record_retry_attempt(updated_request.retry_count, delay)



    async def _handle_timeout(
            self,
            user_id: int,
            state: Optional[UserState],
            wait_time: float = None
    ) -> None:

        """Обработать таймаут поиска"""
        if wait_time is None and state:
            wait_time = time.time() - state.created_at

        # Записать время ожидания в очереди
        await self.metrics.record_queue_wait_time(wait_time or 0)
        await self.metrics.record_match_attempt(user_id, wait_time or 0, 0, False)
        await self.metrics.record_user_status_change(UserStatus.WAITING, UserStatus.EXPIRED)
        logger.debug("Time wait for message % s expired", user_id)
        # Очистить состояние
        await self._cleanup_user_state(user_id)


    async def _cleanup_user_state(self, user_id: int):
        """Очистить состояние пользователя"""
        try:
            await self.state_repo.delete_state(user_id)
            await self.find_match_use_case.user_repo.remove_from_queue(user_id)

        except Exception as e:
            logger.error(f"Error while cleaning up user state: {e}")
            await self.metrics.record_error('cleanup_error', user_id)


