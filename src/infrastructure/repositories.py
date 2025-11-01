import asyncio
import time
from abc import ABC
from asyncio import sleep, CancelledError
from collections import deque
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from redis.asyncio import Redis as aioredis

from src.domain.entities import User
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





