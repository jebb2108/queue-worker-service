import logging
from abc import ABC

from sqlalchemy.ext.asyncio import async_sessionmaker
from src.application.interfaces import (
    AbstractUnitOfWork, AbstractUserRepository,
    AbstractStateRepository
)
from src.infrastructure.repositories import SQLAlchemyMatchRepository

logger = logging.getLogger(__name__)
logger.setLevel(config.log_level.strip())


class SQLAlchemyUnitOfWork(AbstractUnitOfWork, ABC):
    """ Unit Of Work класс для атомарных операуий с sqlalchemy """

    def __init__(
            self,
            session_factory: async_sessionmaker,
            user_repository: AbstractUserRepository,
            state_repository: AbstractStateRepository
    ):
        super().__init__()
        self.session_factory = session_factory
        self.queue = user_repository
        self.states = state_repository
        logger.debug(f"UoW instance created: {id(self)}")

    async def __aenter__(self):
        self.session = self.session_factory()
        self.matches = SQLAlchemyMatchRepository(self.session)
        self.committed = False
        return await super().__aenter__()

    async def __aexit__(self, *args):
        try:
            await super().__aexit__()
            
            # Всегда откатываем, если не было явного коммита
            if not self.committed and self.session and self.session.is_active:
                logger.debug(f"UoW {id(self)} - Rolling back uncommitted transaction")
                await self.session.rollback()

        except Exception as e:
            logger.error(f"UoW {id(self)} - Exception in __aexit__: {e}")
            if self.session and self.session.is_active:
                await self.session.rollback()
            raise

        finally:
            if self.session:
                await self.session.close()
                self.session = None

    async def _rollback(self):
        await self.session.rollback()

    async def _commit(self):
        await self.session.commit()
        self.committed = True

