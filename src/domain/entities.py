import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4

from src.domain.exceptions import IncompatibleUsersException
from src.domain.value_objects import MatchCriteria, UserStatus, CompatibilityScore


@dataclass
class User:
    """Пользователь в системе матчинга"""
    user_id: int
    username: str
    criteria: MatchCriteria
    gender: str
    lang_code: str
    created_at: datetime
    status: UserStatus = UserStatus.WAITING

    def __post_init__(self):
        if not isinstance(self.criteria, MatchCriteria):
            raise ValueError("Criteria must be a MatchCriteria instance")

    def is_compatible_with(self, other: 'User') -> bool:
        """Проверка базовой совместимости с другим пользователем"""
        if self.user_id == other.user_id:
            return False

        return self.criteria.is_compatible_with(other.criteria)

    def calculate_compatibility_score(self, other: 'User', weights: dict = None) -> CompatibilityScore:
        """Расчет детального скора совместимости"""
        if weights is None:
            weights = {
                'language': 0.35,
                'fluency': 0.25,
                'topics': 0.20,
                'dating': 0.10,
                'activity': 0.05,
                'success_rate': 0.05
            }

        scores = dict()

        # 1. Совместимость языка (точное определение)
        scores['language'] = 1.0 if \
            self.criteria.language == other.criteria.language else 0.0

        # 2. Совместимость уровня владения языком
        scores['fluency'] = 0.8 # заглушка

        # 3. Совместимость тем
        scores['topics'] = 0.8 # заглушка

        # 4. Совместимость предпочтений по знакомствам
        scores['dating'] = 0.8 # заглушка

        # 5. Активность (заглушка для будущего ML)
        scores['activity'] = 0.7

        # 6. Исторический успех (заглушка для будущего ML)
        scores['success_rate'] = 0.7

        # Расчет общего скора
        total_score = sum(scores[key] * weights[key] for key in scores)

        # Расчет уверенности
        confidence = self._calculate_confidence(scores)

        # Генерация объяснения
        explanation = self._generate_explanation(scores, weights)

        return CompatibilityScore(
            total_score=total_score,
            component_scores=scores,
            confidence=confidence,
            explanation=explanation
        )

    @staticmethod
    def _calculate_confidence(scores: dict) -> float:
        """Расчет уверенности в скоре"""
        # Простая логика: чем больше высоких скоров, тем выше уверенность
        high_scores = sum(1 for score in scores.values() if score > 0.7)
        return min(1.0, high_scores / len(scores) + 0.2)

    @staticmethod
    def _generate_explanation(scores: dict, weights: dict) -> str:
        """Генерация объяснения скора"""
        explanations = []

        if scores['language'] == 1.0:
            explanations.append("одинаковый язык общения")

        if scores['fluency'] > 0.8:
            explanations.append("схожий уровень владения языком")

        if scores['topics'] > 0.5:
            explanations.append("общие интересы")

        if scores['dating'] == 1.0:
            explanations.append("совпадающие предпочтения по знакомствам")

        if explanations:
            return f"Высокая совместимость: {', '.join(explanations)}"
        else:
            return "Базовая совместимость"

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Создание пользователя из словаря"""
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
            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00')),
            status=UserStatus(data.get('status', 'waiting'))
        )


@dataclass
class Match:
    """Матч между двумя пользователями"""
    match_id: str
    user1: User
    user2: User
    room_id: str
    # TODO: Усовершенствовать
    #  расчет очков по критериям
    compatibility_score: float
    created_at: datetime
    status: str = "active"

    def __post_init__(self):
        if self.user1.user_id == self.user2.user_id:
            raise ValueError("Cannot match user with themselves")

        if not (0.0 <= self.compatibility_score <= 1.0):
            raise ValueError("Compatibility score must be between 0.0 and 1.0")

    @classmethod
    def create(cls, user1: User, user2: User, compatibility_score: float = None) -> 'Match':
        """Фабричный метод для создания матча"""
        if not user1.is_compatible_with(user2):
            raise IncompatibleUsersException(
                f"Users {user1.user_id} and {user2.user_id} are not compatible"
            )

        if compatibility_score is None:
            score_obj = user1.calculate_compatibility_score(user2)
            compatibility_score = score_obj.total_score

        return cls(
            match_id=str(uuid4()),
            user1=user1,
            user2=user2,
            room_id=str(uuid4()),
            compatibility_score=compatibility_score,
            created_at=datetime.now()
        )

    def get_partner(self, user_id: int) -> Optional[User]:
        """Получить партнера для указанного пользователя"""
        if self.user1.user_id == user_id:
            return self.user2
        elif self.user2.user_id == user_id:
            return self.user1
        return None

    def contains_user(self, user_id: int) -> bool:
        """Проверить, участвует ли пользователь в матче"""
        return user_id in (self.user1.user_id, self.user2.user_id)

    def to_dict(self) -> dict:
        """Преобразование в словарь"""
        return {
            'match_id': self.match_id,
            'user1_id': self.user1.user_id,
            'user2_id': self.user2.user_id,
            'room_id': self.room_id,
            'compatibility_score': self.compatibility_score,
            'created_at': self.created_at.isoformat(),
            'status': self.status
        }