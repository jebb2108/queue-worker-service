from abc import ABC
from typing import List

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.interfaces import AbstractUnitOfWork, AbstractUserRepository, AbstractMatchRepository, \
    AbstractStateRepository
from src.config import config
from src.container import get_container
from src.domain.value_objects import UserStatus

DEFAULT_SESSION_FACTORY = async_sessionmaker(
    bind=create_async_engine(
        url=config.database.url,
        isolation_level="REPEATABLE READ"
    )
)


class SQLAlchemyUnitOfWork(AbstractUnitOfWork, ABC):
    """ Unit Of Work класс для атомарных операуий с sqlalchemy """

    def __init__(self):
        self.session_factory = DEFAULT_SESSION_FACTORY


    async def __aenter__(self):

        # Подключаюсь к сессии БД
        self.session = self.session_factory()

        # Вызываю различные зависимости
        container = await get_container()
        self.queue = await container.get(AbstractUserRepository)
        self.matches = await container.get(AbstractMatchRepository)
        self.states = await container.get(AbstractStateRepository)

        # Передаю сессию БД в репозитории
        self.matches.init(self.session)

        # Наследую родительский класс
        return await super().__aenter__()


    async def __aexit__(self, *args):
        await super().__aexit__()
        await self.session.aclose()


    async def _update(self, user_ids: List[int], new_state: UserStatus):
        """ Обновление состояний в оперативной памяти """
        await self.queue.release_reservations(user_ids)
        while user_ids:
            uid = user_ids.pop()
            await self.states.update_state(uid, new_state)
            await self.queue.remove_from_queue(uid)


    async def _commit(self):
        await self.session.commit()


    async def rollback(self):
        await self.session.rollback()

