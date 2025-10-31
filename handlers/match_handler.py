from faststream.rabbit.message import RabbitMessage

from application.use_cases import ProcessMatchRequestUseCase

import logging

logger = logging.getLogger(name='match_handler')


class MatchRequestHandler:
    """Обработчик запросов на поиск собеседника"""

    def __init__(
            self,
            process_match_use_case: ProcessMatchRequestUseCase,
    ):
        self.process_match_use_case = process_match_use_case
        self.count =0


    async def handle_message(self, data: dict, msg: RabbitMessage):
        logger.info(f"data recieved: {data}")
        self.count += 1
        await msg.nack()