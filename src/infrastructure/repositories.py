import asyncio
import json
import time
from abc import ABC
from asyncio import sleep, CancelledError
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any, Union

import redis
from sqlalchemy import select

from src.application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository
)
from src.config import config
from src.domain.entities import User, Match
from src.domain.exceptions import UserAlreadyInSearch, UserNotFoundException
from src.domain.value_objects import UserState, MatchCriteria, UserStatus
from src.infrastructure.orm import match_sessions as orm_match
from src.logconfig import opt_logger as log

logger = log.setup_logger(name='use cases')



class RedisUserRepository(AbstractUserRepository, ABC):
    """Реализация репозитория пользователей на Redis"""

    def __init__(self, r_client: redis.Redis):
        self.redis = r_client
        
    async def save(self, user: User) -> None:
        """Сохранить пользователя в Redis"""
        user_data = {
            "username": user.username,
            "gender": user.gender,
            "lang_code": user.lang_code,
            "created_at": user.created_at.isoformat()
        }

        criteria_data = {
            "language": user.criteria.language,
            "fluency": str(user.criteria.fluency),
            "topics": json.dumps(user.criteria.topics),
            "dating": str(user.criteria.dating)
        }

        async with self.redis.pipeline() as pipe:
            await pipe.hset(f"user:{user.user_id}", mapping=user_data)
            await pipe.hset(f"criteria:{user.user_id}", mapping=criteria_data)
            await pipe.expire(f"user:{user.user_id}", config.cache_ttl)
            await pipe.expire(f"criteria:{user.user_id}", config.cache_ttl)
            await pipe.execute()

        logger.debug("User criteria saved on Redis repo")

    async def find_by_id(self, user_id: int) -> Optional[User]:
        """Найти пользователя по ID"""
        async with self.redis.pipeline() as pipe:
            await pipe.hgetall(f"user:{user_id}")
            await pipe.hgetall(f"criteria:{user_id}")
            results = await pipe.execute()

        user_data, criteria_data = results

        if not user_data or not criteria_data:
            return None

        try:
            criteria = MatchCriteria(
                language=criteria_data['language'],
                fluency=int(criteria_data['fluency']),
                topics=json.loads(criteria_data['topics']),
                dating=criteria_data['dating'].lower() == 'true'
            )

            return User(
                user_id=user_id,
                username=user_data['username'],
                criteria=criteria,
                gender=user_data['gender'],
                lang_code=user_data['lang_code'],
                created_at=datetime.fromisoformat(user_data['created_at'])
            )
        except (KeyError, ValueError, json.JSONDecodeError):
            return None

        finally:
            logger.debug("Created new User entity ")

    async def find_compatible_users(self, user: User, limit: int = 50) -> List[User]:
        """Найти совместимых пользователей из очереди"""
        logger.debug(f"Finding compatible users for user {user.user_id}, limit={limit}")

        # Lua скрипт для получения списка потенциальных кандидатов
        lua_script = """
        local queue_key = KEYS[1]
        local user_id = ARGV[1]
        local user_language = ARGV[2]
        local limit = tonumber(ARGV[3])
        
        local candidates = {}
        local queue_members = redis.call('LRANGE', queue_key, 0, -1)
        
        -- Собираем кандидатов с базовой проверкой
        for i, member_id in ipairs(queue_members) do
            if member_id ~= user_id and #candidates < limit then
                local criteria_key = 'criteria:' .. member_id
                local candidate_criteria = redis.call('HGETALL', criteria_key)
                
                if #candidate_criteria > 0 then
                    local criteria = {}
                    for j = 1, #candidate_criteria, 2 do
                        criteria[candidate_criteria[j]] = candidate_criteria[j + 1]
                    end
                    
                    -- Базовая проверка: тот же язык
                    if criteria['language'] == user_language then
                        table.insert(candidates, member_id)
                    end
                end
            end
        end
        
        return candidates
        """

        try:
            # Получить ID кандидатов из Redis
            candidate_ids = await self.redis.eval(
                lua_script, 1, "waiting_queue",
                str(user.user_id), user.criteria.language, str(limit)
            )

            if not candidate_ids:
                logger.debug(f"No compatible candidates found for user {user.user_id}")
                return []

            # Загрузить полные данные кандидатов
            candidates = []
            for candidate_id in candidate_ids:
                candidate = await self.find_by_id(int(candidate_id))
                if candidate and user.is_compatible_with(candidate):
                    candidates.append(candidate)

            logger.debug(f"Found {len(candidates)} compatible candidates for user {user.user_id}")
            return candidates

        except Exception as e:
            logger.error(f"Error finding compatible users: {e}")
            return []

    async def reserve_candidate(self, user_id: int, candidate_id: int) -> bool:
        """
        Атомарно зарезервировать пару пользователей
        
        Возвращает True если резервация успешна, False если один из пользователей
        уже не в очереди (был зарезервирован другим матчем)
        """
        reserve_script = """
        local queue_key = KEYS[1]
        local user_id = ARGV[1]
        local candidate_id = ARGV[2]

        -- Проверяем, что оба еще в очереди
        local user_in_queue = false
        local candidate_in_queue = false
        local queue_members = redis.call('LRANGE', queue_key, 0, -1)

        for i, member_id in ipairs(queue_members) do
            if member_id == user_id then user_in_queue = true end
            if member_id == candidate_id then candidate_in_queue = true end
            -- Оптимизация: выходим, если нашли обоих
            if user_in_queue and candidate_in_queue then break end
        end

        if not user_in_queue or not candidate_in_queue then
            return 0
        end

        -- Атомарно удаляем обоих из очереди
        redis.call('LREM', queue_key, 1, user_id)
        redis.call('LREM', queue_key, 1, candidate_id)
        
        -- Удаляем флаги поиска
        redis.call('DEL', 'searching:' .. user_id)
        redis.call('DEL', 'searching:' .. candidate_id)

        return 1
        """

        try:
            reserved = await self.redis.eval(
                reserve_script, 1, "waiting_queue",
                str(user_id), str(candidate_id)
            )

            if reserved:
                logger.debug(f"Successfully reserved match: {user_id} <-> {candidate_id}")
                return True
            else:
                logger.debug(f"Failed to reserve match {user_id} <-> {candidate_id} (already taken)")
                return False

        except Exception as e:
            logger.error(f"Error reserving candidate: {e}")
            return False

    async def find_and_reserve_match(self, user: User) -> Optional[User]:
        """ Атомарно найти и зарезервировать совместимого пользователя """
        logger.debug(f"Finding and reserving match for user {user.user_id}")

        # Lua скрипт для атомарного поиска и резервации
        lua_script = """
        local queue_key = KEYS[1]
        local user_id = ARGV[1]
        local user_language = ARGV[2]
        local user_fluency = tonumber(ARGV[3])

        -- Проверяем, что пользователь еще в очереди
        local user_in_queue = false
        local queue_members = redis.call('LRANGE', queue_key, 0, -1)
        
        for i, member_id in ipairs(queue_members) do
            if member_id == user_id then
                user_in_queue = true
                break
            end
        end
        
        if not user_in_queue then
            return nil
        end

        -- Ищем первого совместимого кандидата (только базовая проверка)
        for i, member_id in ipairs(queue_members) do
            if member_id ~= user_id then
                local criteria_key = 'criteria:' .. member_id
                local candidate_criteria = redis.call('HGETALL', criteria_key)

                if #candidate_criteria > 0 then
                    local criteria = {}
                    for j = 1, #candidate_criteria, 2 do
                        criteria[candidate_criteria[j]] = candidate_criteria[j + 1]
                    end

                    -- Базовая проверка: язык и fluency
                    if criteria['language'] == user_language then
                        local fluency_diff = math.abs(tonumber(criteria['fluency'] or 0) - user_fluency)
                        if fluency_diff <= 2 then
                            -- Возвращаем ID для дальнейшей проверки
                            return member_id
                        end
                    end
                end
            end
        end

        return nil
        """

        reserve_script = """
                local queue_key = KEYS[1]
                local user_id = ARGV[1]
                local candidate_id = ARGV[2]

                -- Проверяем, что оба еще в очереди
                local user_in_queue = false
                local candidate_in_queue = false
                local queue_members = redis.call('LRANGE', queue_key, 0, -1)

                for i, member_id in ipairs(queue_members) do
                    if member_id == user_id then user_in_queue = true end
                    if member_id == candidate_id then candidate_in_queue = true end
                end

                if not user_in_queue or not candidate_in_queue then
                    return 0
                end

                -- Атомарно удаляем обоих
                redis.call('LREM', queue_key, 1, user_id)
                redis.call('LREM', queue_key, 1, candidate_id)
                redis.call('DEL', 'searching:' .. user_id)
                redis.call('DEL', 'searching:' .. candidate_id)

                return 1
                """

        candidate_id = await self.redis.eval(
            lua_script, 1, "waiting_queue",
            str(user.user_id), user.criteria.language, str(user.criteria.fluency)
        )

        if not candidate_id:
            logger.debug(f"No candidate found for user {user.user_id}")
            return None

        # Получить полные данные кандидата и проверить полную совместимость
        candidate = await self.find_by_id(int(candidate_id))

        if not candidate or not user.is_compatible_with(candidate):
            logger.debug(f"Candidate {candidate_id} not fully compatible with user {user.user_id}")
            return None

        # Кандидат подходит! Атомарно резервируем обоих

        reserved = await self.redis.eval(
            reserve_script, 1, "waiting_queue",
            str(user.user_id), str(candidate.user_id)
        )

        if reserved:
            logger.debug(f"Match found and reserved: {user.user_id} <-> {candidate.user_id}")
            return candidate
        else:
            logger.debug(f"Failed to reserve match {user.user_id} <-> {candidate.user_id} (already taken)")
            return None

    async def add_to_queue(self, user: User) -> None:
        """ Добавить пользователя в очередь поиска """

        # Проверка на существующего пользователя в очереди
        is_searching = await self.is_searching(user_id=user.user_id)

        if is_searching and user.status == UserStatus.WAITING:
            raise UserAlreadyInSearch

        await self.save(user)  # Сохранить данные пользователя
        await self.redis.lpush("waiting_queue", user.user_id)
        await self.redis.setex(f"searching:{user.user_id}", config.matching.max_wait_time, 1)
        logger.debug("User %s added to queue", user.user_id)

    async def remove_from_queue(self, user_id: int) -> None:
        """ Удалить пользователя из очереди """
        q = await self.redis.lrange("waiting_queue", 0, -1)
        count = list(map(int, q)).count(user_id)
        async with self.redis.pipeline() as pipe:
            await pipe.lrem("waiting_queue", count, user_id)
            await pipe.delete(f"searching:{user_id}")
            await pipe.delete(f"user:{user_id}")
            await pipe.delete(f"criteria:{user_id}")
            await pipe.execute()

        logger.debug("User %s removed from queue", user_id)

    async def get_queue_size(self) -> int:
        """ Получить размер очереди """
        return await self.redis.llen("waiting_queue")

    async def is_searching(self, user_id: Union[int, str]) -> bool:
        """ Получить булевое состяние поиска пользователя """
        return await self.redis.exists(f"searching:{user_id}")

    async def update_user_criteria(self, user_id: int, criteria: Dict[str, Any]) -> None:
        """ Обновить критерии пользователя """
        criteria_data = {
            "language": criteria.get('language', ''),
            "fluency": str(criteria.get('fluency', 0)),
            "topics": json.dumps(criteria.get('topics', [])),
            "dating": str(criteria.get('dating', False))
        }

        await self.redis.hset(f"criteria:{user_id}", mapping=criteria_data)
        await self.redis.expire(f"criteria:{user_id}", config.cache_ttl)
        logger.debug("Criteria updated: %s", criteria_data)

    async def reserve_match_id(self, user_id: int, match_id: str) -> None:
        await self.redis.setex(f"match_id:{user_id}", config.matching.max_wait_time, match_id)

    async def get_match_id(self, user_id: int) -> Optional[str]:
        return await self.redis.get(f'match_id:{user_id}')

    @asynccontextmanager
    async def transaction(self):
        """Простая реализация транзакции через pipeline"""
        async with self.redis.pipeline() as pipe:
            try:
                yield pipe
                await pipe.execute()
            except Exception:
                # В случае ошибки pipeline автоматически отменяется
                raise


class MemoryStateRepository(AbstractStateRepository, ABC):
    """ Реализация репозитория состояний в памяти с TTL """
    def __init__(self, max_size: int = 10_000):
        self.states = {}
        self.access_order: deque = deque(maxlen=max_size)
        self.max_size = max_size
        self.lock = asyncio.Lock()
        self.cleanup_task: Optional[asyncio.Task] = None

        # Запустить фоновую задачу очистки
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def save_state(self, state: UserState) -> None:
        """ Сохранить состояние пользователя """
        async with self.lock:
            #  Удалить из старой позиции, если существует
            if state.user_id in self.states:
                try:
                    self.access_order.remove(state.user_id)
                except ValueError:
                    pass

            # Добавить в новую позицию
            self.states[state.user_id] = state
            self.access_order.append(state.user_id)

            # Проверить лимит размера
            if len(self.states) > self.max_size:
                oldest_user_id = self.access_order.popleft()
                self.states.pop(oldest_user_id, None)

    async def get_state(self, user_id: int) -> Optional[UserState]:
        """ Получить состояние пользователя """
        async with self.lock:
            state = self.states.get(user_id)

            if state and not state.is_expired():
                # Обновить порядок доступа
                try:
                    self.access_order.remove(user_id)
                    self.access_order.append(user_id)
                except ValueError:
                    pass
                return state

            elif state and state.is_expired():
                # Удалить истекшее состояние
                self.states.pop(user_id, None)
                try:
                    self.access_order.remove(user_id)
                except ValueError:
                    pass

            return None

    async def update_state(self, user_id: int, new_status: UserStatus) -> None:
        """ Обновить состояние пользователя """
        async with self.lock:
            state = await self.get_state(user_id)

            if state:
                updated_state = UserState(
                    user_id=user_id,
                    status=new_status,
                    created_at=state.created_at,
                    retry_count=state.retry_count,
                    last_updated=time.time()
                )
                await self.save_state(updated_state)

            return None


    async def delete_state(self, user_id: int) -> None:
        """Удалить состояние пользователя"""
        async with self.lock:
            self.states.pop(user_id, None)
            try:
                self.access_order.remove(user_id)
            except ValueError:
                pass

    async def cleanup_expired_states(self, ttl: int = 300):
        """ Очистить истекшее состояние """

        current_time = time.time()
        expired_account = 0

        async with self.lock:
            expired_users = [
                user_id for user_id, state in self.states.items() if \
                    current_time - state.created_at > ttl
            ]
            for user_id in expired_users:
                self.states.pop(user_id, None)
                try:
                    self.access_order.remove(user_id)
                except ValueError:
                    pass
                expired_account += 1

        return expired_account


    async def _cleanup_loop(self):
        """ Фоновая задача для периодической очистки """
        while True:
            try:
                await sleep(60)
                await self.cleanup_expired_states()
            except CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background task in MemoryStateRepository: {e}")
                pass #  Логирую ошибку, но не прекращаю работу


    def __del__(self):
        """Остановить фоновую задачу при удалении объекта"""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()


class SQLAlchemyMatchRepository(AbstractMatchRepository, ABC):

    def __init__(self, session):
        super().__init__()
        self._session = session

    async def add(self, match: Match) -> None:
        try:
            match.user1 = await self._session.merge(match.user1)
            match.user2 = await self._session.merge(match.user2)
            # Flush, чтобы убедиться, что добавление возможно
            await self._session.flush()
        except:
            logger.debug(f"Match {match.match_id} didn`t merge")
            raise
        else:
            self._session.add(match)
            logger.debug(f"Match {match.match_id} added to session")

    async def get(self, match_id: str):
        stmt = select(Match).where(Match.match_id == match_id)  # noqa
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self) -> List[str]:
        """ Получить список всех match_id из таблицы match_sessions """
        stmt = select(orm_match.c.match_id) # noqa
        result = await self._session.execute(stmt)
        match_ids = result.scalars().all()
        logger.debug(f"Found {len(match_ids)} match_ids: {match_ids}")
        return list(match_ids)