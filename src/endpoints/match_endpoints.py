from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from src.application.interfaces import AbstractUserRepository, AbstractMetricsCollector
from src.config import config
from src.container import get_user_repository, get_metrics_collector
from src.domain.entities import User
from src.domain.exceptions import UserAlreadyInSearch
from src.domain.value_objects import MatchRequest
from src.infrastructure.services import RabbitMQMessagePublisher

router = APIRouter()

@router.post("/match")
async def submit_match_request(
    request_data: dict,
    publisher: RabbitMQMessagePublisher = Depends(lambda: RabbitMQMessagePublisher()),
    redis_repo: AbstractUserRepository = Depends(get_user_repository),
) -> Dict[str, str]:
    """
    Принять запрос на поиск матча и отправить в очередь
    """
    try:
        # Подготовить данные для очереди
        match_request = {
            'user_id': request_data.get('user_id'),
            'username': request_data.get('username'),
            'gender': request_data.get('gender'),
            'criteria': request_data.get('criteria'),
            'lang_code': request_data.get('lang_code'),
            'created_at': datetime.now(tz=config.timezone).isoformat(),
            'status': config.SEARCH_STARTED
        }

        # Отправить в очередь ожидания
        await redis_repo.add_to_queue(User.from_dict(request_data))
        await publisher.publish_match_request(MatchRequest.from_dict(match_request))
        return {"status": "accepted", "message": "Match request submitted successfully"}

    except UserAlreadyInSearch:
        return {"status": "rejected", "message": f"User {request_data.get('user_id')} already in search"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit match request: {str(e)}")

@router.get("/health")
async def health_check(
        metrics: AbstractMetricsCollector = Depends(get_metrics_collector)
) -> Dict[str, str]:
    """
    Проверка здоровья сервиса
    """
    return await metrics.get_health_status()


@router.get("/metrics")
async def get_metrics(
    metrics: AbstractMetricsCollector = Depends(get_metrics_collector)
) -> str:
    """
    Получить метрики сервиса в формате Prometheus
    """
    result = await metrics.get_metrics()
    return result.get('prometheus_metrics', '')


# @router.get("/ready")
# async def readiness_check() -> Dict[str, str]:
#     """
#     Проверка готовности сервиса
#     """
#     # Здесь можно добавить проверки подключений к Redis, RabbitMQ и т.д.
#     return {"status": "ready", "service": "match_worker"}
