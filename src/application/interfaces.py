from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from src.domain.entities import User
from src.domain.value_objects import UserState, MatchRequest


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
    async def is_searching(self, user_id: int) -> bool:
        pass

    @abstractmethod
    async def get_queue_size(self) -> int:
        """Получить размер очереди"""
        pass

    @abstractmethod
    async def update_user_criteria(self, user_id: int, criteria: Dict[str, Any]) -> None:
        """Обновить критерии пользователя"""
        pass

    @abstractmethod
    async def release_reservations(self, user_ids: List[int]) -> None:
        """Освободить резервации пользователей"""
        pass

    def transaction(self):
        """Контекстный менеджер для транзакций"""
        pass


class AbstractMatchRepository(ABC):
    pass


class AbstractStateRepository(ABC):

    @abstractmethod
    async def save_state(self, state: UserState) -> None:
        pass

    @abstractmethod
    async def get_state(self, user_id: int) -> Optional[UserState]:
        pass

    @abstractmethod
    async def delete_state(self, user_id: int) -> None:
        pass


class AbstractMessagePublisher(ABC):

   @abstractmethod
   async def publish_to_dead_letter(self, data: MatchRequest, err_msg: str):
       pass

   @abstractmethod
   async def publish_match_request(self, data: MatchRequest, delay: float = 0.0):
       pass


class AbstractMetricsCollector(ABC):
    """ Интерфейс сборщика метрик """

    @abstractmethod
    async def record_match_attempt(
            self,
            user_id: int,
            processing_time: float,
            candidates_evaluated: int,
            match_found: bool,
            compatibility_score: float = None
    ) -> None:
        """ Записать попытку матчинга """
        pass

    @abstractmethod
    async def record_error(self, error_type: str, user_id: int = None) -> None:
        """ Записать ошибку """
        pass

    @abstractmethod
    async def get_metrics(self) -> Dict[str, Any]:
        """ Получить метрики """
        pass

    @abstractmethod
    async def get_health_status(self) -> Dict[str, Any]:
        """ Получить статус здоровья """
        pass