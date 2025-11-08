from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import Match, User
from src.domain.value_objects import MatchCriteria
from src.infrastructure.repositories import SQLAlchemyMatchRepository


@pytest.mark.asyncio
async def test_create_match_sessions(session):

    repo = SQLAlchemyMatchRepository()
    repo.init(session)

    fake_match_id = 'some_id_ref'
    fake_criteria = MatchCriteria(
        language='english', fluency=0,
        topics=['games', 'art'], dating=True
    )
    fake_user1 = User(
        user_id=123, username='jacob21',
        criteria=fake_criteria, gender='male',
        lang_code='ru', created_at=datetime.now())
    fake_user2 = User(
        user_id=321, username='chloe23',
        criteria=fake_criteria, gender='female',
        lang_code='ru', created_at=datetime.now())
    match = Match(
        match_id=fake_match_id,
        user1=fake_user1,
        user2=fake_user2,
        room_id=fake_match_id,
        created_at=datetime.now(),
        compatibility_score=0.80
    )
    await repo.add(match)
    await session.commit()

    saved_match = await repo.get(fake_match_id)
    assert saved_match is not None



