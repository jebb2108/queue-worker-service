import time
from datetime import datetime
from typing import Optional, List


from src.application.interfaces import (
    AbstractUserRepository, AbstractStateRepository,
    AbstractMessagePublisher, AbstractMetricsCollector, AbstractUnitOfWork
)
from src.config import config
from src.domain.entities import Match, User, ScoredCandidate
from src.domain.exceptions import UserNotFoundException, MatchingException
from src.domain.value_objects import MatchRequest, UserStatus, UserState

from src.logconfig import opt_logger as log
logger = log.setup_logger(name='use cases')


class FindMatchUseCase:
    """ Use case для поиска матча """

    def __init__(
        self,
        state_repository: AbstractStateRepository,
        metrics_collector: AbstractMetricsCollector
    ):
        self.state_repo = state_repository
        self.metrics = metrics_collector

    async def execute(self, user_id: int, user_repo: AbstractUserRepository) -> Optional[Match]:
        """ Выполнить поиск матча для пользователя """
        start_time = time.time()
        try:
            logger.debug(f"Starting match search for user {user_id}")
            
            # Получить пользователя
            user = await user_repo.find_by_id(user_id)
            if not user:
                logger.error(f"User {user_id} not found in repository")
                raise UserNotFoundException(f"User {user_id} not found")

            logger.debug(f"User {user_id} found, searching for compatible candidates")
            
            # Записать размер очереди
            queue_size = await user_repo.get_queue_size()
            await self.metrics.record_queue_size(queue_size)
            logger.debug(f"Queue size: {queue_size}")
            
            # Найти совместимых кандидатов
            candidates = await user_repo.find_compatible_users(user, limit=50)
            candidates_count = len(candidates)
            
            if not candidates:
                logger.debug(f"No compatible candidates found for user {user_id}")
                await self.metrics.record_match_attempt(
                    user_id, time.time() - start_time, 0, False
                )
                return None
            
            logger.debug(f"Found {candidates_count} compatible candidates for user {user_id}")
            
            # Получить отсортированный список кандидатов
            scored_candidates = await self._select_best_candidates(user, candidates)
            
            if not scored_candidates:
                logger.debug(f"No candidate passed compatibility threshold for user {user_id}")
                await self.metrics.record_match_attempt(
                    user_id, time.time() - start_time, candidates_count, False
                )
                return None
            
            # Попытаться зарезервировать кандидатов по порядку (от лучшего к худшему)
            # Это защищает от race condition, когда лучший кандидат уже занят
            for scored_candidate in scored_candidates:
                candidate_id = scored_candidate.candidate.user_id
                
                # Атомарно зарезервировать кандидата
                reserved = await user_repo.reserve_candidate(user_id, candidate_id)
                
                if reserved:
                    # Успешно зарезервировали - создаем матч
                    match = Match.create(user, scored_candidate.candidate, scored_candidate.score.total_score)
                    logger.info(f"Match created and reserved: {user_id} <-> {candidate_id} (score: {scored_candidate.score.total_score})")
                    
                    # Записать метрики с реальным количеством оцененных кандидатов
                    await self.metrics.record_match_attempt(
                        user_id, time.time() - start_time, candidates_count,
                        True, match.compatibility_score
                    )
                    
                    return match

                else:
                    # Кандидат уже занят, пробуем следующего
                    logger.debug(f"Candidate {candidate_id} already taken, trying next candidate")
                    continue
            
            # Все кандидаты уже заняты
            logger.debug(f"All {len(scored_candidates)} candidates already taken for user {user_id}")
            await self.metrics.record_match_attempt(
                user_id, time.time() - start_time, candidates_count, False
            )
            return None

        except Exception as e:
            logger.error(f"Exception in FindMatchUseCase for user {user_id}: {e}")
            await self.metrics.record_error('match_search_error', user_id)
            raise MatchingException(f"Error finding match for user {user_id}: {str(e)}")


    async def _select_best_candidates(self, user: User, candidates: List[User]) -> List[ScoredCandidate]:
        """
        Выбрать и отсортировать кандидатов по скору совместимости
        
        Возвращает список отсортированных кандидатов (от лучшего к худшему),
        прошедших порог совместимости
        """
        if not candidates:
            return []

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
                    logger.debug(f"Candidate {candidate.user_id} scored {score.total_score}")

            except Exception as e:
                # Логируем ошибку, но продолжаем с другими кандидатами
                await self.metrics.record_error('scoring_error', candidate.user_id)
                logger.error(f"Error while scoring candidates: {e}")
                continue

        if not scored_candidates:
            logger.debug(f"No candidates passed threshold {config.matching.compatibility_threshold}")
            return []

        # Сортировать по скору (от лучшего к худшему)
        scored_candidates.sort(reverse=True)
        logger.debug(f"Selected {len(scored_candidates)} candidates passing threshold, best score: {scored_candidates[0].score.total_score}")
        return scored_candidates



class ProcessMatchRequestUseCase:
    """ Use case для обработки запросов на матчинг """

    def __init__(
        self,
        find_match_use_case: FindMatchUseCase,
        message_publisher: AbstractMessagePublisher,
        metrics_collector: AbstractMetricsCollector
    ):

        self.find_match_use_case = find_match_use_case
        self.message_publisher = message_publisher
        self.metrics = metrics_collector


    async def execute(self, request: MatchRequest, uow: AbstractUnitOfWork):
        """ Обработать запрос на матчинг """
        try:
            logger.debug(f"Processing match request for user {request.user_id}")

            # Проверить состояние пользователя
            should_process = await self._should_process_request(request, uow)
            if not should_process:
                return True

            if await self._should_delay_processing(request):
                await self._schedule_retry(request)
                return True
            
            async with uow:
                # Атомарно найти и зарезервировать матч
                match: Match = await self.find_match_use_case.execute(request.user_id, uow.queue)

                if match:
                    # Пользователи уже зарезервированы в Redis, просто сохраняем в БД
                    await uow.matches.add(match)
                    
                    try:
                        await uow.commit()
                        # Отправляю match_id обратно на фронтенд
                        from src.container import get_notification_service
                        notification_service = await get_notification_service()
                        await notification_service.send_match_id_request(request.user_id, match.match_id)
                        # Логирую найденную пару из пользователей
                        user_ids = [match.user1.user_id, match.user2.user_id]
                        logger.info(f"Match committed for users {user_ids}")
                        return True
                        
                    except Exception as e:
                        # Если коммит не удался, возвращаем пользователей в очередь
                        logger.error(f"Commit failed, returning users to queue: {e}")
                        user_ids = [match.user1.user_id, match.user2.user_id]
                        
                        for user_id in user_ids:
                            user = await uow.queue.find_by_id(user_id)
                            if user:
                                await uow.queue.add_to_queue(user)
                        
                        await self._schedule_retry(request, delay=2.0)
                        await self.metrics.record_error('commit_failed', request.user_id)
                        return False

            # Матч не найден
            return await self._handle_no_match(request, uow)

        except Exception as e:
            logger.error(f"Exception in ProcessMatchRequestUseCase for user {request.user_id}: {e}")
            await self.metrics.record_error('request_processing_error', request.user_id)
            await self.message_publisher.publish_to_dead_letter(
                request.to_dict(), # noqa
                f"Processing error: {str(e)}"
            )
            return False


    async def _should_process_request(self, request: MatchRequest, uow: AbstractUnitOfWork):
        """ Определить, следует ли обрабатывать запрос """

        state: UserState = await uow.states.get_state(request.user_id)

        if state:
            # Проверить статус запроса
            if state.status in [UserStatus.CANCELED, UserStatus.MATCHED]:
                await self._cleanup_user_state(request.user_id, uow)
                logger.info("User %s left queue", request.user_id)
                return False

            # Проверить, не истек ли запрос
            elapsed = datetime.now(tz=config.timezone) - request.created_at
            if elapsed.total_seconds() >= config.matching.max_wait_time:
                await self._handle_timeout(request.user_id, None, uow, elapsed.total_seconds())
                return False

            # Проверить, находится ли пользователь в поиске (единственный источник истины - Redis)
            is_searching = await uow.queue.is_searching(request.user_id)

            if not is_searching:
                logger.debug(f"User {request.user_id} not in search queue, skipping")
                return False

            return True

        else:

            new_state = UserState(
                user_id=request.user_id,
                status=UserStatus.WAITING,
                created_at=time.time()
            )
            await uow.states.save_state(new_state)
            return True


    @staticmethod
    async def _should_delay_processing(request: MatchRequest):
        """ Определить, нужно ли отложить обработку """
        elapsed = datetime.now(tz=config.timezone) - request.created_at
        return elapsed.total_seconds() < config.matching.initial_delay  # 5 секунд

    async def _schedule_retry(self, request,  delay: float = None) -> None:
        """ Запланировать повторную обработку """
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

    async def _handle_no_match(self, request: MatchRequest,  uow: AbstractUnitOfWork):
        """ Обработать случаи, когда матч не найден"""

        # Проверить лимиты времени и попыток
        elapsed = datetime.now(tz=config.timezone) - request.created_at
        if elapsed.total_seconds() >= config.matching.max_wait_time or \
                request.retry_count >= config.matching.max_retries:
            # Превышены лимиты, уведомить о таймауте
            await self._handle_timeout(request.user_id, None, uow, elapsed.total_seconds())
            return True


        # Применить ослабление критериев и запланировать повтор
        await self._relax_criteria_and_retry(request,  uow)
        return True

    async def _relax_criteria_and_retry(self, request: MatchRequest,  uow: AbstractUnitOfWork):
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
        await uow.queue.update_user_criteria(
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
            uow: AbstractUnitOfWork,
            wait_time: float = None
    ) -> None:

        """ Обработать таймаут поиска """
        if wait_time is None and state:
            wait_time = time.time() - state.created_at

        # Записать время ожидания в очереди
        await self.metrics.record_queue_wait_time(wait_time or 0)
        await self.metrics.record_match_attempt(user_id, wait_time or 0, 0, False)
        await self.metrics.record_user_status_change(UserStatus.WAITING, UserStatus.EXPIRED)
        logger.info("Time wait for message % s expired", user_id)
        # Очистить состояние
        await self._cleanup_user_state(user_id, uow)


    async def _cleanup_user_state(self, user_id: int, uow: AbstractUnitOfWork):
        """ Очистить состояние пользователя """
        try:
            await uow.states.delete_state(user_id)
            await uow.queue.remove_from_queue(user_id)

        except Exception as e:
            logger.error(f"Error while cleaning up user state: {e}")
            await self.metrics.record_error('cleanup_error', user_id)


