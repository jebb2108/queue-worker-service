import asyncio
import logging
import sys
from typing import Optional

from faststream import FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.message import RabbitMessage

from config import config
from container import get_container, cleanup_container
from handlers.match_handler import MatchRequestHandler

logger = logging.getLogger('main')

class WorkerService:
    """ Основной класс Worker Service """

    def __init__(self):
        self.broker: Optional[RabbitBroker] = None
        self.app: Optional[FastStream] = None
        self.container = None
        self.handlers = {}

    async def initialize(self):
        """ Инициализация сервиса """
        logger.info("Initializing Worker Service ...")

        try:
            # Получить контейнер зависимостей
            self.container = await get_container()

            # Создать брокер сообщений
            self.broker = RabbitBroker()

            # Создать обработчики
            await self._create_handlers()

            # Зарегистрировать обработчики сообщений
            await self._register_message_handlers()

            # Создать FastStream приложение
            self.app = FastStream(self.broker)

            logger.info("Worker Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Worker Service: {e}")


    async def _create_handlers(self):
        """ Создать обработчики сообщений """

        # Получаем use_cases из контейнера
        from application.use_cases import ProcessMatchRequestUseCase

        process_match_request_usecase = await self.container.get(ProcessMatchRequestUseCase)

        self.handlers = {
            'match': MatchRequestHandler(process_match_request_usecase)
        }

        logger.info("Match handler created")

    async def _register_message_handlers(self):
        """ Зарегистрировать обрабочики сообщений """


        @self.broker.subscriber(config.rabbitmq.match_queue)
        async def handle_match_request(data: dict, msg: RabbitMessage):
            await self.handlers['match'].handle_message(data, msg)

        logger.info("Message handlers registered")


    async def start(self):
        """ Запусть Worker Service """
        logger.info('Starting Worker service ...')

        try:
            # Инициализация
            await self.initialize()

            # Запуск приложения
            await self.app.run()

        except KeyboardInterrupt:
            logger.info("Recieved keyboard interrupt")
            raise
        except Exception as e:
            logger.error(f"Error running Worker Service: {e}")
            raise

        finally:
            await self.cleanup()


    async def cleanup(self):
        """ Очистка ресурсов """
        logger.info("Cleaning up Worker Service ...")

        try:

            if self.broker:
                await self.broker.start()

            await cleanup_container()

            logger.info("Worker Service cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


async def main():
    """Главная функция"""
    logger.info("Starting English Tutor Worker Service")
    logger.info(f"Configuration: Debug={config.debug}, Log Level={config.log_level}")

    # Создать и запустить сервисы
    worker_service = WorkerService()

    tasks = [
        asyncio.create_task(worker_service.start(), name='worker_service')
    ]

    try:
        # Ждать завершения всез задач
        await asyncio.gather(*tasks)

    except KeyboardInterrupt:

        # Отменить все задачи
        for task in tasks:
            if not task.done():
                task.cancel()


        # Ждать завершения отмены задач
        await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

    logger.info("Worker Service stopped")


if __name__ == '__main__':
    # Запуск сервиса
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("Service interrupted by admin")
    except Exception as e:
        logger.error(f"Service failed: {e}")