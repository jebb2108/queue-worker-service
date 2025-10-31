from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from ..domain.entities import User


class AbstractUserRepository(ABC):
    """Интерфейс репозитория пользователей"""

    @abstractmethod
    async def save(self, user: User) -> None:
        """Сохранить пользователя"""
        pass

    @abstractmethod
    async def find_by_id(self, user_id: int) -> Optional[User]:
        """Найти пользователя по ID"""
        pass

    @abstractmethod
    async def find_compatible_users(self, user: User, limit: int = 50) -> List[User]:
        """Найти совместимых пользователей"""
        pass

    @abstractmethod
    async def add_to_queue(self, user: User) -> None:
        """Добавить пользователя в очередь поиска"""
        pass

    @abstractmethod
    async def remove_from_queue(self, user_id: int) -> None:
        """Удалить пользователя из очереди"""
        pass

    @abstractmethod
    async def get_queue_size(self) -> int:
        """Получить размер очереди"""
        pass

    @abstractmethod
    async def update_user_criteria(self, user_id: int, criteria: Dict[str, Any]) -> None:
        """Обновить критерии пользователя"""
        pass


class AbstractMatchRepository(ABC):
    pass


class AbstractStateRepository(ABC):
    pass