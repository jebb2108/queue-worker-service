from abc import ABC

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.interfaces import (
    AbstractUnitOfWork, AbstractUserRepository,
    AbstractStateRepository, AbstractMatchRepository, AbstractMessageRepository
)
from src.infrastructure.repositories import SQLAlchemyMatchRepository, SQLAlchemyMessageRepository
from src.logconfig import opt_logger as log

logger = log.setup_logger(name='use cases')



class SQLAlchemyUnitOfWork(AbstractUnitOfWork, ABC):
    """ Unit Of Work класс для атомарных операуий с sqlalchemy """

    def __init__(
            self,
            session_factory: async_sessionmaker,
            user_repository: AbstractUserRepository,
            state_repository: AbstractStateRepository,
            match_repository: AbstractMatchRepository,
            message_repository: AbstractMessageRepository
    ):
        super().__init__()
        self.session_factory = session_factory
        self.queue = user_repository
        self.states = state_repository
        self.matches = match_repository
        self.messages = message_repository
        logger.debug(f"UoW instance created: {id(self)}")

    async def __aenter__(self):
        self.session = self.session_factory()
        self.matches.create_session(self.session)
        self.messages.create_session(self.session)
        self.committed = False
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await super().__aexit__(exc_type, exc_val, exc_tb)
            
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

