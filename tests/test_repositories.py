import time

import pytest

from src.domain.value_objects import UserState, UserStatus
from src.infrastructure.repositories import MemoryStateRepository


@pytest.mark.asyncio
async def test_creation_memory_state_repository():
    """ Протестировать создание класса """
    repo = MemoryStateRepository()
    assert repo.__class__ == MemoryStateRepository

@pytest.mark.asyncio
async def test_adding_user_state_to_memory():
    """ Протетстировать добавление матч пользователя в память """
    repo = MemoryStateRepository()
    await repo.save_state(UserState(
        user_id=123,
        status=UserStatus.WAITING,
        created_at=time.time()
    ))
    assert len(repo.states) == 1
    assert repo.access_order.pop() == 123


@pytest.mark.asyncio
async def test_getting_user_state_from_memory():
    """ Протестировать извлечение состояния из памяти """
    repo = MemoryStateRepository()
    user_state = UserState(
        user_id=123,
        status=UserStatus.WAITING,
        created_at=time.time()
    )
    await repo.save_state(user_state)
    assert await repo.get_state(123) == user_state


@pytest.mark.asyncio
async def test_deleting_user_state_from_memory():
    """ Протестировать удаление состояния из памяти"""
    repo = MemoryStateRepository()
    user_state = UserState(
        user_id=123,
        status=UserStatus.WAITING,
        created_at=time.time()
    )
    await repo.save_state(user_state)
    assert len(repo.states) == len(repo.access_order) and len(repo.states) == 1

    await repo.delete_state(123)
    assert len(repo.states) == len(repo.access_order) == 0