from abc import ABC
from typing import List, Dict, Any

from redis.asyncio import Redis as aioredis

from application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository
)

redis_client = aioredis.from_url("redis://", decode=True)


class RedisUserRepository(AbstractUserRepository, ABC):
    pass

class DatabaseMatchRepository(AbstractMatchRepository, ABC):
    pass

class MemoryStateRepository(AbstractStateRepository, ABC):
    pass




