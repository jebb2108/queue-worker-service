from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from src.domain.entities import Message

if TYPE_CHECKING:
    from src.domain.entities import User, Match
    from src.domain.value_objects import UserState, MatchRequest, UserStatus


class AbstractUserRepository(ABC):
    """ Интерфейс репозитория пользователей """

    async def reserve_candidate(self, user_id: int, candidate: int) -> None:
        """ Зарезервировать лучшего кандидата """
        pass

    async def reserve_match_id(self, user_id: int, match_id: str) -> None:
        """ Сохранить match id для ID пользователя """
        pass

    async def get_match_id(self, user_id: int) -> Optional[str]:
        """ Извлечь match id пользователя, если присутсвует """
        pass

    async def find_and_reserve_match(self, user: "User") -> Optional["User"]:
        """Атомарно найти и зарезервировать совместимого пользователя"""
        pass

    @abstractmethod
    async def save(self, user: "User") -> None:
        """ Сохранить пользователя """
        raise NotImplementedError

    @abstractmethod
    async def find_by_id(self, user_id: int) -> Optional["User"]:
        """ Найти пользователя по ID """
        raise NotImplementedError

    @abstractmethod
    async def find_compatible_users(self, user: "User", limit: int = 50) -> List["User"]:
        """ Найти совместимых пользователей """
        raise NotImplementedError

    @abstractmethod
    async def add_to_queue(self, user: "User") -> None:
        """ Добавить пользователя в очередь поиска """
        raise NotImplementedError

    @abstractmethod
    async def remove_from_queue(self, user_id: int) -> None:
        """ Удалить пользователя из очереди """
        raise NotImplementedError

    @abstractmethod
    async def is_searching(self, user_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_queue_size(self) -> int:
        """Получить размер очереди"""
        raise NotImplementedError


    @abstractmethod
    async def update_user_criteria(self, user_id: int, criteria: Dict[str, Any]) -> None:
        """ Обновить критерии пользователя """
        raise NotImplementedError


class AbstractMatchRepository(ABC):

    def __init__(self):
        self._session = None

    def create_session(self, session):
        self._session = session

    @abstractmethod
    async def add(self, match: "Match") -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, match_id: str):
        raise NotImplementedError

    @abstractmethod
    async def update(self, match_id: str, new_status: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def list(self) -> List[str]:
        """Получить список всех match_id из таблицы match_sessions"""
        raise NotImplementedError

class AbstractMessageRepository(ABC):

    def __init__(self):
        self.session = None

    def create_session(self, session):
        self._session = session

    @abstractmethod
    async def add(self, message: "Message") -> None:
        raise NotImplementedError

    @abstractmethod
    async def list(self, room_id: str) -> list:
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
        self.session: Optional[object] = None
        self.matches: Optional[AbstractMatchRepository] = None
        self.states: Optional[AbstractStateRepository] = None
        self.queue: Optional[AbstractUserRepository] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self):
        await self._rollback()

    async def commit(self):
        await self._commit()

    @abstractmethod
    async def _rollback(self):
        raise NotImplementedError

    @abstractmethod
    async def _commit(self):
        raise NotImplementedError


class AbstractNotificationService(ABC):

    @abstractmethod
    async def send_match_id_request(self, user_id: int, match_id: str) -> None:
        raise NotImplementedError