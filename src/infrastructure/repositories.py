import asyncio
import json
import time
from abc import ABC
from asyncio import sleep, CancelledError
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any

import asyncpg
import redis
from redis.asyncio import Redis as aioredis

from src.config import config
from src.domain.entities import User, Match
from src.application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository
)
from src.domain.value_objects import UserState, MatchCriteria
from src.handlers.match_handler import logger

redis_client = aioredis.from_url("redis://", decode=True)


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

    async def find_compatible_users(self, user: User, limit: int = 50) -> List[User]:
        """ Найти совместимых пользователей с использованием Lua скрипта """

        # Lua скрипт для эффективного поиска совместимых пользователей
        lua_script = """
        local queue_key = KEYS[1]
        local user_id = ARGV[1]
        local user_language = ARGV[2]
        local user_fluency = tonumber(ARGV[3])
        local max_candidates = tonumber(ARGV[4])

        local queue_members = redis.call('LRANGE', queue_key, 0, -1)
        local candidates = {}
        local count = 0

        for i, member_id in ipairs(queue_members) do
            if member_id ~= user_id and count < max_candidates then
                local criteria_key = 'criteria:' .. member_id
                local candidate_criteria = redis.call('HGETALL', criteria_key)

                if #candidate_criteria > 0 then
                    local criteria = {}
                    for j = 1, #candidate_criteria, 2 do
                        criteria[candidate_criteria[j]] = candidate_criteria[j + 1]
                    end

                    -- Предварительная фильтрация
                    if criteria['language'] == user_language then
                        local fluency_diff = math.abs(tonumber(criteria['fluency'] or 0) - user_fluency)
                        if fluency_diff <= 2 then
                            table.insert(candidates, member_id)
                            count = count + 1
                        end
                    end
                end
            end
        end

        return candidates
        """

        candidate_ids = await self.redis.eval(
            lua_script, 1, "waiting_queue",
                            str(user.user_id), user.criteria.language, str(user.criteria.fluency), str(limit)
        )

        # Получить полные данные кандидатов
        compatible_users = []
        for candidate_id in candidate_ids:
            candidate = await self.find_by_id(int(candidate_id))
            if candidate and user.is_compatible_with(candidate):
                compatible_users.append(candidate)

        return compatible_users

    async def add_to_queue(self, user: User) -> None:
        """ Добавить пользователя в очередь поиска """
        await self.save(user)  # Сохранить данные пользователя
        await self.redis.lpush("waiting_queue", user.user_id)
        await self.redis.setex(f"searching:{user.user_id}", config.matching.max_wait_time, 1)

    async def remove_from_queue(self, user_id: int) -> None:
        """ Удалить пользователя из очереди """
        async with self.redis.pipeline() as pipe:
            await pipe.lrem("waiting_queue", 0, user_id)
            await pipe.delete(f"searching:{user_id}")
            await pipe.delete(f"user:{user_id}")
            await pipe.delete(f"criteria:{user_id}")
            await pipe.execute()

    async def get_queue_size(self) -> int:
        """ Получить размер очереди """
        return await self.redis.llen("waiting_queue")

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


class PostgresSQLMatchRepository(AbstractMatchRepository, ABC):
    """ Реализация репозитория матчей на PostgreSQL """

    def __init__(self):
        self.pool = None

    @asynccontextmanager
    async def get_connection(self):
        """ Получить соединение с базой данных """
        if self.pool is None:
            self.pool = await asyncpg.create_pool(dsn=config.database.url)
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)

    async def save(self, match: Match) -> None:
        """ Сохранить матч в базу данных """
        async with self.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO match_sessions 
                (session_id, user1_id, user2_id, room_id, compatibility_score, created_at, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                match.match_id,
                match.user1.user_id,
                match.user2.user_id,
                match.room_id,
                match.compatibility_score,
                match.created_at,
                match.status
            )

    async def find_by_id(self, match_id: str) -> Optional[Match]:
        """ Найти матч по ID """
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM match_sessions WHERE session_id = $1",
                match_id
            )

            if not row:
                return None

            return None # TODO: Дописать результат функции

    async def find_by_user_id(self, user_id: int) -> List[Match]:
        """ Найти матчи пользователя """
        async with self.get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM match_sessions
                WHERE user1_id = $1 OR user2_id = $1
                ORDER BY created_at DESC
                """,
                user_id
            )

            return [] # TODO: Дописать результат функции

    async def update_status(self, match_id: str, status: str) -> None:
        """ Обновить статус матча """
        async with self.get_connection() as conn:
            await conn.execute(
                "UPDATE match_sessions SET status = $1 WHERE session_id = $2",
                status, match_id
            )





