from abc import ABC
from typing import List, Optional, Dict, Any

from redis.asyncio import Redis as aioredis

from ..domain.entities import User
from ..application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository
)

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
    pass




