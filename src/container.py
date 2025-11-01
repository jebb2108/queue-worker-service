import inspect
from typing import Type, Any, Dict, Optional

import asyncpg
import redis
from redis.asyncio import Redis as aioredis

from src.application.interfaces import (
    AbstractUserRepository, AbstractMatchRepository, AbstractStateRepository, AbstractMessagePublisher
)
from src.application.use_cases import FindMatchUseCase, ProcessMatchRequestUseCase
from src.config import config
from src.infrastructure.repositories import (
    RedisUserRepository, MemoryStateRepository, PostgresSQLMatchRepository
)

from src.infrastructure.services import RabbitMQMessagePublisher


class ServiceNotRegisteredError(Exception):
    """Исключение для незарегистрированного сервиса"""
    pass


class ServiceContainer:

    def __init__(self):
        self._services: Dict[Type, tuple] = {}
        self._singletons: Dict[Type, Any] = {}
        self._initialized = False

    def register_singleton(self, interface: Type, implementation: Type = None):
        """
        Зарегистрировать singleton сервис - зависимость, объявляемая
        всего один раз при инициализации контейнера
        :param interface: абстрактный порт для определенного сервиса
        :param implementation: адаптер под него
        """
        if implementation is None:
            # Некоторые интерфейсы не имеют отдельных
            # репозиториев. e.g. DatabaseService
            implementation = interface # Репозиторий = Интерфейс
        self._services[interface] = (implementation, True)

    def register_transient(self, interface: Type, implementation: Type = None):
        """
        Зарегистрировать transient сервис - зависимость, объявляемая
        # в течение всего жизненного цикла
        :param interface: абстрактный порт для определенного сервиса
        :param implementation: адаптер под него
        """
        if implementation is None:
            implementation = interface
        self._services[interface] = (implementation, False)

    def register_instance(self, interface: Type, instance: Any):
        """Зарегистрировать готовый экземпляр"""
        self._singletons[interface] = instance
        self._services[interface] = (type(instance), True)

    async def get(self, interface: Type):
        """Получить экземпляр сервиса"""
        if interface not in self._services:
            raise ServiceNotRegisteredError(f"Service {interface.__name__} not registered")

        implementation, is_singleton = self._services[interface]
        if is_singleton:
            if interface not in self._singletons:
                self._singletons[interface] = await self._create_instance(implementation)
            return self._singletons[interface]
        else:
            return await self._create_instance(implementation)


    async def _create_instance(self, implementation: Type):
        """Создать экземпляр с dependency injection"""

        # Получить параметры конструктора
        sig = inspect.signature(implementation.__init__)
        params = {}

        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue

            # Попытаться разрешить зависимость по типу аннотации
            if param.annotation != inspect.Parameter.empty:
                if param.annotation in self._services:
                    params[param_name] = await self.get(param.annotation)
                elif hasattr(param.annotation, '__origin__'):
                    # Обработка Generic типов (например, Optional[SomeType])
                    continue

        return implementation(**params)


    async def initialise(self):
        """ Инициализировать контейнер и все зависимости """

        if self._initialized:
            return

        # Создать подключения к внешним зависимостям
        await self._setup_external_connections()

        # Зарегистрировать все сервисы
        await self._register_services()

        self._initialized = True


    async def _setup_external_connections(self):
        """ Настроить подключения к внешним сервисам """
        # Redis подключение
        redis_client = await aioredis.from_url(
            url=config.redis.url,
            max_connections=config.redis.max_connections,
            retry_on_timeout=config.redis.retry_on_timeout,
            socket_timeout=config.redis.socket_timeout,
            socket_connect_timeout=config.redis.socket_connect_timeout,
            decode=True
        )
        self.register_instance(redis.Redis, redis_client)

        # PostgreSQL подключение
        db_pool = await asyncpg.create_pool(
            config.database.url,
            min_size=config.database.min_size,
            max_size=config.database.max_size,
            timeout=config.database.timeout,
            command_timeout=config.database.command_timeout
        )
        self.register_instance(asyncpg.Pool, db_pool)


    async def _register_services(self):
        """ Зарегистрировать все сервисы """

        # Repositories
        self.register_singleton(AbstractUserRepository, RedisUserRepository)
        self.register_singleton(AbstractMatchRepository, PostgresSQLMatchRepository)
        self.register_singleton(AbstractStateRepository, MemoryStateRepository)

        # Infrastructure services
        self.register_singleton(AbstractMessagePublisher, RabbitMQMessagePublisher)

        # Use cases
        self.register_transient(FindMatchUseCase, FindMatchUseCase)
        self.register_transient(ProcessMatchRequestUseCase, ProcessMatchRequestUseCase)


    async def cleanup(self):
        """Очистить ресурсы"""

        # Закрыть соединения
        if redis.Redis in self._singletons:
            await self._singletons[redis.Redis].aclose()
        if asyncpg.Pool in self._singletons:
            await self._singletons[asyncpg.Pool].close()

        # Очистить состояния
        self._singletons.clear()
        self._initialized = False


class ServiceFactory:
    """ Фабрика для создания настроенного контейнера """

    @staticmethod
    async def create_container() -> ServiceContainer:
        """Создать и настроить контейнер"""
        container = ServiceContainer()
        await container.initialise()
        return container

    @staticmethod
    async def create_health_checker_dependencies() -> Dict[str, Any]:
        """Создать зависимости для health checker"""
        # Redis
        redis_client = redis.Redis.from_url(config.redis.url)

        # PostgreSQL
        db_pool = await asyncpg.create_pool(config.database.url)

        return { "redis": redis_client, "database": db_pool }


# Глобальный контейнер (Singleton)
_container: Optional[ServiceContainer] = None


async def get_container() -> ServiceContainer:
    """ Получить глобальный контейнер """
    global _container
    if _container is None:
        _container = await ServiceFactory.create_container()

    return _container

async def cleanup_container() -> None:
    """Очистить глобальный контейнер"""
    global _container

    if _container is not None:
        await _container.cleanup()
        _container = None



# УДОБНЫЕ ФУНКЦИИ ДЛЯ ПОЛУЧЕНИЯ СЕРВИСОВ
async def get_user_repository() -> AbstractUserRepository:
    """ Получить репозиторий пользователя """
    container = await get_container()
    return await container.get(AbstractUserRepository)


async def get_match_repository() -> AbstractMatchRepository:
    """ Получить репозиторий матча """
    container = await get_container()
    return await container.get(AbstractMatchRepository)


async def get_state_repository() -> AbstractStateRepository:
    """ Получить репозиторий состояний"""
    container = await get_container()
    return await container.get(AbstractStateRepository)