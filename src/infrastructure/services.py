class RateLimiter:

    @staticmethod
    def is_allowed():
        return True # Заглушка


class CurcuitBreaker:

    @staticmethod
    async def call(fn1, fn2):
        return True


class RabbitMQMessagePublisher:

    pass