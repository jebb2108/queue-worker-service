from datetime import datetime
from typing import Any
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Depends, status, Response, Query
from prometheus_client import CONTENT_TYPE_LATEST

from src.application.interfaces import AbstractUserRepository, AbstractMetricsCollector, AbstractUnitOfWork
from src.config import config
from src.container import get_user_repository, get_metrics_collector, get_container
from src.domain.entities import User, Match
from src.domain.exceptions import UserAlreadyInSearch
from src.domain.value_objects import MatchRequest, UserStatus
from src.infrastructure.services import RabbitMQMessagePublisher
from src.logconfig import opt_logger as log
from src.models import MatchRequestModel, MatchResponse, HealthResponse

if TYPE_CHECKING:
    from src.container import ServiceContainer


logger = log.setup_logger('match_endpoints')


router = APIRouter(prefix="/api/v0")

@router.post("/match/toggle", response_model=MatchResponse)
async def submit_match_request(
    request_data: MatchRequestModel,
    publisher: RabbitMQMessagePublisher = Depends(lambda: RabbitMQMessagePublisher()),
    user_repo: AbstractUserRepository = Depends(get_user_repository)
) -> MatchResponse:
    """
    Принять запрос на поиск матча и отправить в очередь
    """

    user_status = UserStatus.CANCELED if \
        await user_repo.is_searching(request_data.user_id) else UserStatus.WAITING

    try:
        # Подготовить данные для очереди
        match_request = {
            'user_id': request_data.user_id,
            'username': request_data.username,
            'gender': request_data.gender,
            'criteria': request_data.criteria,
            'lang_code': request_data.lang_code,
            'created_at': datetime.now(tz=config.timezone).isoformat(),
            'status': user_status.value
        }

        # Отправить в очередь ожидания
        await user_repo.add_to_queue(User.from_dict(match_request))
        await publisher.publish_match_request(MatchRequest.from_dict(match_request))
        return MatchResponse(status="accepted", message="Match request submitted successfully")

    except UserAlreadyInSearch:
        return MatchResponse(status="rejected", message=f"User {request_data.user_id} already in search")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit match request: {str(e)}"
        )

@router.get("/check_match")
async def check_match_id(
        user_id: int = Query(..., description="ID пользователя для проверки", example=123),
        user_repo: AbstractUserRepository = Depends(get_user_repository),
        container: "ServiceContainer" = Depends(get_container)
):
    """ Обработчик, отвечающий за отслеживанием состания поиска матча """
    try:
        # Пытается извлечь match id пользователя
        match_id = await user_repo.get_match_id(user_id)
        if match_id:
            uow = await container.get(AbstractUnitOfWork)
            async with uow:
                match: Match = await uow.matches.get(match_id)
                return { 'match_id': match_id, 'room_id': match.room_id }

        return { 'match_id': None, 'room_id': None }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get match id: {str(e)}"
        )


@router.get("/queue/status")
async def get_queue_status(
        user_repo: AbstractUserRepository = Depends(get_user_repository)
):
    queue_size = await user_repo.get_queue_size()
    return { "queue_size": queue_size }

@router.get("/queue/{user_id}/status")
async def get_user_queue_status(
        user_id: int,
        user_repo: AbstractUserRepository = Depends(get_user_repository)
):
    # Проверка, если пользователь в очереди ожидания
    in_queue = await user_repo.is_searching(user_id)
    queue_size = await user_repo.get_queue_size()
    return {
        "user_id": user_id,
        "in_queue": in_queue,
        "position": queue_size
    }

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
