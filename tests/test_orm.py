import uuid
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domain.entities import Match, User
from src.domain.value_objects import MatchCriteria
from src.infrastructure.repositories import SQLAlchemyMatchRepository
from src.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from src.logconfig import opt_logger as log
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = log.setup_logger(name="TEST_ORM")

fake_match_id = None


def create_mtach() -> Match:
    global fake_match_id

    # Используем уникальный ID для каждого теста
    if not fake_match_id:
        fake_match_id = str(uuid.uuid4())

    fake_criteria = MatchCriteria(
        language='english', fluency=0,
        topics=['games', 'art'], dating=True
    )

    # Используем уникальные user_id для каждого теста
    fake_user1 = User(
        user_id=int(str(uuid.uuid4().int)[:10]), username=f'jacob_{uuid.uuid4().hex[:6]}',
        criteria=fake_criteria, gender='male',
        lang_code='ru', created_at=datetime.now())
    fake_user2 = User(
        user_id=int(str(uuid.uuid4().int)[:10]), username=f'chloe_{uuid.uuid4().hex[:6]}',
        criteria=fake_criteria, gender='female',
        lang_code='ru', created_at=datetime.now())

    match = Match(
        match_id=fake_match_id,
        user1=fake_user1,
        user2=fake_user2,
        room_id=str(uuid.uuid4()),  # Уникальный room_id
        created_at=datetime.now(),
        compatibility_score=0.80
    )
    return match

@pytest.mark.asyncio
async def test_unit_of_work_with_adding_match():

    uow = SQLAlchemyUnitOfWork()

    async with uow:
        match = create_mtach()
        await uow.matches.add(match)
        await uow.commit()

    async with uow:
        match = create_mtach()
        this_match = await uow.matches.get(match.match_id)

    assert this_match is not None


@pytest.mark.asyncio
async def test_db_version_by_adding_match_to_repository():

    uow = SQLAlchemyUnitOfWork()

    async with uow:
        match = create_mtach()
        initial_version = await uow.matches.version()
        await uow.matches.add(match)
        await uow.commit()

    async with uow:
        curr_version = await uow.matches.version()

    assert initial_version + 1 == curr_version