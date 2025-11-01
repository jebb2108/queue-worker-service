import asyncio
import time
from abc import ABC
from asyncio import sleep, CancelledError
from collections import deque
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

import asyncpg
from redis.asyncio import Redis as aioredis

from src.config import config
from src.domain.entities import User, Match
from src.application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository
)
from src.domain.value_objects import UserState
from src.handlers.match_handler import logger

redis_client = aioredis.from_url("redis://", decode=True)


class RedisUserRepository(AbstractUserRepository, ABC):
    async def save(self, user: User) -> None:
        """Сохранить пользователя"""
        pass

    async def find_by_id(self, user_id: int) -> Optional[User]:
        """Найти пользователя по ID"""
        pass

    async def find_compatible_users(self, user: User, limit: int = 50) -> List[User]:
        """Найти совместимых пользователей"""
        pass

    async def add_to_queue(self, user: User) -> None:
        """Добавить пользователя в очередь поиска"""
        pass

    async def remove_from_queue(self, user_id: int) -> None:
        """Удалить пользователя из очереди"""
        pass

    async def get_queue_size(self) -> int:
        """Получить размер очереди"""
        pass

    async def update_user_criteria(self, user_id: int, criteria: Dict[str, Any]) -> None:
        """Обновить критерии пользователя"""
        pass

class DatabaseMatchRepository(AbstractMatchRepository, ABC):
    pass

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
        self.pool = asyncpg.create_pool(dsn=config.database.url)

    @asynccontextmanager
    async def get_connection(self):
        """ Получить соединение с базой данных """
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
        """ бновить статус матча """
        async with self.get_connection() as conn:
            await conn.execute(
                "UPDATE match_sessions SET status = $1 WHERE session_id = $2",
                status, match_id
            )





