import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.annotations import RabbitMessage
from starlette.middleware.cors import CORSMiddleware

from src.config import config
from src.container import get_container, cleanup_container
from src.handlers.match_handler import MatchRequestHandler
from src.endpoints.match_endpoints import router as match_router
from src.logconfig import opt_logger as log

logger = log.setup_logger(name='use cases')



class WorkerService:
    """ Основной класс Worker Service """

    def __init__(self):
        self.broker: Optional[RabbitBroker] = None
        self.app: Optional[FastStream] = None
        self.container = None
        self.handlers = {}

    async def initialize(self):
        """ Инициализация сервиса """
        logger.debug("Initializing Worker Service ...")

        try:
            # Получить контейнер зависимостей
            self.container = await get_container()

            # Создать брокер сообщений
            self.broker = RabbitBroker(url=config.rabbitmq.url, logger=None)

            # Создать обработчики
            await self._create_handlers()

            # Зарегистрировать обработчики сообщений
            await self._register_message_handlers()

            # Создать FastStream приложение
            self.app = FastStream(self.broker, logger=logger)

            logger.debug("Worker Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Worker Service: {e}")


    async def _create_handlers(self):
        """ Создать обработчики сообщений """

        # Получаем use_cases из контейнера
        from src.application.use_cases import ProcessMatchRequestUseCase
        from src.application.interfaces import AbstractMetricsCollector

        process_match_request_usecase = await self.container.get(ProcessMatchRequestUseCase)
        metrics_collector = await self.container.get(AbstractMetricsCollector)

        self.handlers = {
            'match': MatchRequestHandler(
                process_match_request_usecase,
                metrics_collector
            )
        }

        logger.debug("Match handler created")

    async def _register_message_handlers(self):
        """ Зарегистрировать обрабочики сообщений """


        @self.broker.subscriber(config.rabbitmq.match_queue)
        async def handle_match_request(data: dict, msg: RabbitMessage):
            await self.handlers['match'].handle_message(data, msg)

        logger.debug("Message handlers registered")


    async def start(self):
        """ Запустить Worker Service """
        logger.debug('Starting Worker service ...')

        try:
            # Инициализация
            await self.initialize()

            # Запуск приложения
            if self.app is None:
                raise RuntimeError("Application not initialized")

            await self.app.run()

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            raise
        except Exception as e:
            logger.error(f"Error running Worker Service: {e}")
            raise

        finally:
            await self.cleanup()


    async def cleanup(self):
        """ Очистка ресурсов """
        logger.debug("Cleaning up Worker Service ...")

        try:
            if self.broker:
                await self.broker.stop()

            await cleanup_container()

            logger.debug("Worker Service cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI): # noqa
    """Главная функция"""
    logger.info("Starting Worker Service")
    logger.info(
        f"Configuration: Debug={config.debug},"
        f" Log Level={config.log_level}"
    )
    # Создать и запустить сервисы
    worker_service = WorkerService()
    # Запускаем воркер при старте приложения
    task = asyncio.create_task(worker_service.start(), name='worker_service')
    logger.info("Background worker started")
    yield

    # Останавливаем воркер при завершении
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Background worker stopped")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, # noqa
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(match_router)

if __name__ == "__main__":
    uvicorn.run(
        'main:app',
        host='0.0.0.0',
        port=config.port,
        reload=True
    )