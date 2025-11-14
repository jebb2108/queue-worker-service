import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities import User, Match
    from src.domain.value_objects import UserState, MatchRequest, UserStatus


class AbstractUserRepository(ABC):
    """Интерфейс репозитория пользователей"""

    @abstractmethod
    async def save(self, user: "User") -> None:
        """Сохранить пользователя"""
        pass

    @abstractmethod
    async def find_by_id(self, user_id: int) -> Optional["User"]:
        """Найти пользователя по ID"""
        pass

    @abstractmethod
    async def find_compatible_users(self, user: "User", limit: int = 50) -> List["User"]:
        """Найти совместимых пользователей"""
        pass

    @abstractmethod
    async def add_to_queue(self, user: "User") -> None:
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

    def __init__(self):
        self._session = None

    async def pass_session(self, session):
        self._session = session

    @abstractmethod
    def add(self, macth: "Match"):
        raise NotImplementedError

    @abstractmethod
    def get(self, session_id: str):
        raise NotImplementedError

    @abstractmethod
    async def list(self) -> List[str]:
        """Получить список всех match_id из таблицы match_sessions"""
        raise NotImplementedError


class AbstractStateRepository(ABC):

    @abstractmethod
    async def get_state(self, user_id: int) -> Optional["UserState"]:
        raise NotImplementedError

    @abstractmethod
    async def update_state(self, user_id: int, new_state: "UserStatus"):
        raise NotImplementedError

    @abstractmethod
    async def save_state(self, state: "UserState") -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_state(self, user_id: int) -> None:
        raise NotImplementedError


class AbstractMessagePublisher(ABC):

   @abstractmethod
   async def publish_to_dead_letter(self, data: "MatchRequest", err_msg: str):
       pass

   @abstractmethod
   async def publish_match_request(self, data: "MatchRequest", delay: float = 0.0):
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
    async def record_queue_wait_time(self, wait_time: int) -> None:
        """Записать время ожидания в очереди"""
        pass

    @abstractmethod
    async def record_retry_attempt(self, retry_count: int, delay: float) -> None:
        """ Записать количество повторов"""
        pass

    @abstractmethod
    async def record_queue_size(self, queue_size: int) -> None:
        """ Записать размер очереди ожидания"""
        pass

    @abstractmethod
    async def record_error(self, error_type: str, user_id: int = None) -> None:
        """ Записать ошибку """
        pass

    @abstractmethod
    async def record_user_status_change(self, old_status: "UserStatus", new_status: "UserStatus") -> None:
        """ Записать изменения в статусе поиска """
        pass

    @abstractmethod
    async def record_criteria_usage(self, criteria_type: str, value: str) -> None:
        """ Заполнить измения в критериях """
        pass

    @abstractmethod
    async def get_metrics(self) -> Dict[str, Any]:
        """ Получить метрики """
        pass

    @abstractmethod
    async def get_health_status(self) -> Dict[str, Any]:
        """ Получить статус здоровья """
        pass


class AbstractUnitOfWork(ABC):

    def __init__(self):
        """ Дефолтные атрибуты """
        self.matches = None
        self.states = None
        self.queue = None
        # Счетчик версий БД
        self.db_version = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self):
        await self._rollback()

    async def update(self, user_ids: List[int], new_state: "UserStatus"):
        await self._update(user_ids, new_state)

    async def commit(self):
        self.db_version += 1
        await self._commit()

    @abstractmethod
    async def _rollback(self):
        raise NotImplementedError

    @abstractmethod
    async def _commit(self):
        raise NotImplementedError

    @abstractmethod
    async def _update(self, user_ids, new_state):
        raise NotImplementedError