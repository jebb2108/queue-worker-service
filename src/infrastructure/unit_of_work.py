from abc import ABC
from typing import List

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.interfaces import AbstractUnitOfWork, AbstractUserRepository, AbstractMatchRepository, \
    AbstractStateRepository
from src.container import get_container
from src.domain.value_objects import UserStatus


class SQLAlchemyUnitOfWork(AbstractUnitOfWork, ABC):
    """ Unit Of Work класс для атомарных операуий с sqlalchemy """

    def __init__(self):
        super().__init__()
        self._initialized = False

    async def initialize(self):
        """ Инициализирует необходимые ресурсы """
        # Вызывает контейнер
        container = await get_container()
        # Вызывает различные репозитории
        self.queue = await container.get(AbstractUserRepository)
        self.matches = await container.get(AbstractMatchRepository)
        self.states = await container.get(AbstractStateRepository)
        self.session_factory = await container.get(async_sessionmaker)
        # Помечает UoW инициированным
        self._initialized = True

    async def __aenter__(self):
        # Вызываю различные зависимости
        if not self._initialized: await self.initialize()
        # Получаю фабрику сессии из контейнера (уже настроенную)
        self.session = self.session_factory()
        # Передаю сессию репозиторию, ответсвенному за БД
        await self.matches.pass_session(self.session)
        # Наследую родительский класс
        return await super().__aenter__()

    async def __aexit__(self, *args):
        try:
            # Сначала пытается выполнить
            # rollback из родительского класса
            await super().__aexit__()
        finally:
            # Закрытие сессии при любом исходе
            await self.session.close()


    async def _update(self, user_ids: List[int], new_state: UserStatus):
        """ Обновление состояний в оперативной памяти """
        while user_ids:
            uid = user_ids.pop()
            await self.states.update_state(uid, new_state)
            await self.queue.remove_from_queue(uid)


    async def _rollback(self):
        await self.session.rollback()


    async def _commit(self):
        await self.session.commit()

