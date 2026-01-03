from typing import Dict, Any

from pydantic import BaseModel, Field


class MatchRequestModel(BaseModel):
    """ Модель запроса на поиск матча """
    user_id: int = Field(..., gt=0, description="ID пользователя")
    username: str = Field(..., min_length=1, max_length=100, description="Имя пользователя")
    gender: str = Field(..., min_length=1, max_length=20, description="Пол пользователя")
    criteria: Dict[str, Any] = Field(..., description="Критерии поиска")
    lang_code: str = Field(..., min_length=1, max_length=10, description="Код языка")
    action: str = Field(..., description="Запрос на вступление либо выход из очереди")


class MatchResponse(BaseModel):
    """ Модель ответа на запрос матча """
    status: str = Field(..., description="Статус ответа")
    message: str = Field(..., description="Сообщение")

class MessageModel(BaseModel):
    """ Модель сообщения для запросов """
    sender: str
    text: str
    room_id: str

class HealthResponse(BaseModel):
    """ Модель ответа проверки здоровья """
    status: str = Field(..., description="Статус сервиса")
    queue_size: int = Field(default=0, description="Размер очереди")
    error_rate: float = Field(default=0.0, description="Уровень ошибок")
    timestamp: float = Field(..., description="Временная метка")
