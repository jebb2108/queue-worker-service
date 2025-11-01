from typing import Awaitable

import asyncpg
import pytest
import redis

from src.application.interfaces import AbstractUserRepository
from src.application.use_cases import FindMatchUseCase
from src.container import ServiceContainer
from src.container import get_user_repository, get_state_repository, get_match_repository
from src.infrastructure.repositories import RedisUserRepository, DatabaseMatchRepository, MemoryStateRepository, \
    PostgresSQLMatchRepository


@pytest.mark.asyncio
async def test_create_service_container(container: Awaitable[ServiceContainer]):
    """ Тест с созданием экземляра контейнера"""
    assert hasattr(container, '_services')
    assert hasattr(container, '_singletons')
    assert hasattr(container, '_initialized')


@pytest.mark.asyncio
async def test_with_container_fixture(container):
    """ Тест с извлечением зависимости """
    use_case = await container.get(FindMatchUseCase)
    assert use_case is not None

@pytest.mark.asyncio
async def test_all_services_created_according_to_type(container):
    """ Тест с извлечением репозиториев """
    assert (await get_user_repository()).__class__ == RedisUserRepository
    assert (await get_match_repository()).__class__ == PostgresSQLMatchRepository
    assert (await get_state_repository()).__class__ == MemoryStateRepository
    assert await container.get(redis.Redis) is not None
    assert await container.get(asyncpg.Pool) is not None

@pytest.mark.asyncio
async def test_cleanup_method(container):
    """ Тест с очисткой контейнера """
    await container.cleanup()
    assert not container._singletons
    assert not container._initialized

@pytest.mark.asyncio
async def test_factory_creation(factory):
    """ Тестирую фабрику с ее статикой """
    # Статический метод на создание рабочего контейнера
    c = await factory.create_container()
    assert hasattr(c, '_services')
    assert await c.get(AbstractUserRepository) is not None
    # Статический метод на hralth check зависимости
    assert hasattr(factory, 'create_health_checker_dependencies')
    d = await factory.create_health_checker_dependencies()
    assert d.get("redis") is not None and d.get("database") is not None
