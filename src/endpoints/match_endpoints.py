from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any
import time

from src.domain.value_objects import MatchRequest
from src.infrastructure.services import RabbitMQMessagePublisher
from src.config import config

router = APIRouter()

@router.post("/match")
async def submit_match_request(
    request_data: dict,
    publisher: RabbitMQMessagePublisher = Depends(lambda: RabbitMQMessagePublisher())
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
            'created_at': datetime.now().isoformat(),
            'status': config.SEARCH_STARTED
        }

        # Отправить в очередь
        await publisher.publish_match_request(MatchRequest.from_dict(match_request))

        return {"status": "accepted", "message": "Match request submitted successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit match request: {str(e)}")

@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Проверка здоровья сервиса
    """
    return {"status": "healthy", "service": "match_worker"}

@router.get("/ready")
async def readiness_check() -> Dict[str, str]:
    """
    Проверка готовности сервиса
    """
    # Здесь можно добавить проверки подключений к Redis, RabbitMQ и т.д.
    return {"status": "ready", "service": "match_worker"}

@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """
    Получить метрики сервиса
    """
    # Заглушка для метрик
    return {
        "uptime": "unknown",
        "requests_processed": 0,
        "queue_size": 0,
        "active_connections": 0
    }