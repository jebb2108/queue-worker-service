from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, status, Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST

from src.application.interfaces import AbstractUserRepository, AbstractMetricsCollector
from src.config import config
from src.container import get_user_repository, get_metrics_collector
from src.domain.entities import User
from src.domain.exceptions import UserAlreadyInSearch
from src.domain.value_objects import MatchRequest
from src.infrastructure.services import RabbitMQMessagePublisher


class MatchRequestModel(BaseModel):
    """Модель запроса на поиск матча"""
    user_id: int = Field(..., gt=0, description="ID пользователя")
    username: str = Field(..., min_length=1, max_length=100, description="Имя пользователя")
    gender: str = Field(..., min_length=1, max_length=20, description="Пол пользователя")
    criteria: Dict[str, Any] = Field(..., description="Критерии поиска")
    lang_code: str = Field(..., min_length=1, max_length=10, description="Код языка")


class MatchResponse(BaseModel):
    """Модель ответа на запрос матча"""
    status: str = Field(..., description="Статус ответа")
    message: str = Field(..., description="Сообщение")


class HealthResponse(BaseModel):
    """Модель ответа проверки здоровья"""
    status: str = Field(..., description="Статус сервиса")
    queue_size: int = Field(default=0, description="Размер очереди")
    error_rate: float = Field(default=0.0, description="Уровень ошибок")
    timestamp: float = Field(..., description="Временная метка")

router = APIRouter()

@router.post("/match", response_model=MatchResponse)
async def submit_match_request(
    request_data: MatchRequestModel,
    publisher: RabbitMQMessagePublisher = Depends(lambda: RabbitMQMessagePublisher()),
    redis_repo: AbstractUserRepository = Depends(get_user_repository),
) -> MatchResponse:
    """
    Принять запрос на поиск матча и отправить в очередь
    """
    try:
        # Подготовить данные для очереди
        match_request = {
            'user_id': request_data.user_id,
            'username': request_data.username,
            'gender': request_data.gender,
            'criteria': request_data.criteria,
            'lang_code': request_data.lang_code,
            'created_at': datetime.now(tz=config.timezone).isoformat(),
            'status': config.SEARCH_STARTED
        }

        # Отправить в очередь ожидания
        await redis_repo.add_to_queue(User.from_dict(match_request))
        await publisher.publish_match_request(MatchRequest.from_dict(match_request))
        return MatchResponse(status="accepted", message="Match request submitted successfully")

    except UserAlreadyInSearch:
        return MatchResponse(status="rejected", message=f"User {request_data.user_id} already in search")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit match request: {str(e)}"
        )

@router.get("/health", response_model=HealthResponse)
async def health_check(
        metrics: AbstractMetricsCollector = Depends(get_metrics_collector)
) -> HealthResponse | dict[str, Any]:
    """
    Проверка здоровья сервиса
    """
    if metrics is None:
        return HealthResponse(
            status="unknown",
            error_rate=0.0,
            queue_size=0,
            timestamp=datetime.now().timestamp()
        )
    return await metrics.get_health_status()


@router.get("/metrics")
async def get_metrics(
    metrics_collector: AbstractMetricsCollector = Depends(get_metrics_collector)
) -> Response:
    """
    Получить метрики сервиса в формате Prometheus
    """
    metrics_data = await metrics_collector.get_metrics()
    content = metrics_data.get('prometheus_metrics', '')
    if not content:
        content = '# No metrics available\n'
    return Response(
        content=content,
        media_type=CONTENT_TYPE_LATEST
    )


# @router.get("/ready")
# async def readiness_check() -> Dict[str, str]:
#     """
#     Проверка готовности сервиса
#     """
#     # Здесь можно добавить проверки подключений к Redis, RabbitMQ и т.д.
#     return {"status": "ready", "service": "match_worker"}
