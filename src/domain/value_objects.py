import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Dict

from src.logconfig import opt_logger as log

logger = log.setup_logger(name='use cases')



class UserStatus(Enum):
    """Статусы пользователя в системе матчинга"""
    WAITING = "waiting"
    MATCHED = "matched"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass(frozen=False)
class MatchCriteria:
    """ Критерии поиска собеседника """
    language: str
    fluency: int
    topics: List[str]
    dating: bool

    def __post_init__(self):
        # Валидация критериев
        if not isinstance(self.language, str) or not self.language:
            raise ValueError("Language must be a non-empty string")

        if not isinstance(self.fluency, int) or not (0 <= self.fluency <= 10):
            raise ValueError("Fluency must be an integer between 0 and 10")

        if not isinstance(self.topics, list) or not self.topics:
            raise ValueError("Topics must be a non-empty list")

        if not isinstance(self.dating, bool):
            raise ValueError("Dating must be a boolean")

    def is_compatible_with(self, other: 'MatchCriteria') -> bool:
        """Базовая проверка совместимости критериев"""
        # Язык должен совпадать
        if self.language != other.language:
            return False

        # Уровень владения языком не должен сильно отличаться
        if abs(self.fluency - other.fluency) > 1:
            return False

        # Должны быть общие темы
        common_topics = set(self.topics).intersection(set(other.topics))
        if not common_topics:
            return False

        return True

    def relax(self, step: int) -> 'MatchCriteria':
        """ Ослабление критериев для увеличения шансов найти пару """
        relaxed_topics = list(self.topics)
        relaxed_dating = self.dating
        relaxed_fluency = self.fluency

        if step == 3:
            relaxed_dating = False

        if step == 5:
            relaxed_topics.append('general')

        if step == 8 and relaxed_fluency > 0:
            relaxed_fluency -= 1

        return MatchCriteria(
            language=self.language,
            fluency=relaxed_fluency,
            topics=relaxed_topics,
            dating=relaxed_dating
        )

@dataclass(frozen=True)
class MatchRequest:
    """ Запрос на поиск собеседника """
    user_id: int
    username: str
    criteria: MatchCriteria
    gender: str
    lang_code: str
    status: str
    created_at: datetime
    current_time: datetime
    source: str = "worker_service"
    retry_count: int = 0

    @classmethod
    def from_dict(cls, data: Dict) -> 'MatchRequest':
        """ Создание объекта из словаря """
        criteria_data = data.get('criteria', {})
        criteria = MatchCriteria(
            language=criteria_data.get('language', ''),
            fluency=int(criteria_data.get('fluency', 0)),
            topics=criteria_data.get('topics', []),
            dating=criteria_data.get('dating', False)
        )


        return cls(
            user_id=int(data['user_id']),
            username=data['username'],
            criteria=criteria,
            gender=data['gender'],
            lang_code=data['lang_code'],
            status=data.get('status', 'search_started'),
            created_at=datetime.fromisoformat(data['created_at']),
            current_time=datetime.fromisoformat(data.get('current_time', data['created_at'])),
            source=data.get('source', 'worker_service'),
            retry_count=data.get('retry_count', 0)
        )

    def to_dict(self) -> Dict:
        """ Преобразование в словарь """
        return {
            'user_id': self.user_id,
            'username': self.username,
            'criteria': {
                'language': self.criteria.language,
                'fluency': self.criteria.fluency,
                'topics': self.criteria.topics,
                'dating': self.criteria.dating
            },
            'gender': self.gender,
            'lang_code': self.lang_code,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'current_time': self.current_time.isoformat(),
            'source': self.source,
            'retry_count': self.retry_count
        }


@dataclass(frozen=True)
class CompatibilityScore:
    """Оценка совместимости между пользователями"""
    total_score: float
    component_scores: Dict[str, float]
    confidence: float
    explanation: str

    def __post_init__(self):
        if not (0.0 <= self.total_score <= 1.0):
            raise ValueError("Total score must be between 0.0 and 1.0")

        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")


@dataclass
class UserState:
    """Состояние пользователя в системе матчинга"""
    user_id: int
    status: UserStatus
    created_at: float
    retry_count: int = 0
    last_updated: float = None

    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = time.time()

    def is_expired(self, ttl: int = 300) -> bool:
        """Проверка истечения времени жизни состояния"""
        return time.time() - self.created_at > ttl

    def increment_retry(self) -> 'UserState':
        """Увеличение счетчика попыток"""
        return UserState(
            user_id=self.user_id,
            status=self.status,
            created_at=self.created_at,
            retry_count=self.retry_count + 1,
            last_updated=time.time()
        )

    def update_status(self, new_status: UserStatus) -> 'UserState':
        """Обновление статуса пользователя"""
        return UserState(
            user_id=self.user_id,
            status=new_status,
            created_at=self.created_at,
            retry_count=self.retry_count,
            last_updated=time.time()
        )