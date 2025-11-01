from src.domain.value_objects import MatchRequest


class RateLimiter:

    @staticmethod
    def is_allowed():
        return True # Заглушка


class CurcuitBreaker:

    @staticmethod
    async def call(fn1, fn2):
        return True


class RabbitMQMessagePublisher:

    async def publish_to_dead_letter(self, data: MatchRequest, err_msg: str):
        pass

    async def publish_match_request(self, data: MatchRequest, delay: float = 0.0):
        pass