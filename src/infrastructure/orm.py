import sqlalchemy
from sqlalchemy import (
    MetaData, Table, Column, String, BigInteger,
    Float, DateTime, SmallInteger, ARRAY,
    Boolean, ForeignKey, Enum
)
from sqlalchemy.orm import registry, relationship

from src.domain.entities import Match, User
from src.domain.value_objects import MatchCriteria, UserStatus
from src.logconfig import opt_logger as log

logger = log.setup_logger(name='use cases')


mapper_registry = registry()
metadata = MetaData()

criteria_matches = Table(
    'criteria_matches',
    metadata,
    Column('id', BigInteger, primary_key=True, autoincrement=True),
    Column('language', String(50), nullable=False),
    Column('fluency', SmallInteger, nullable=False),
    Column('topics', ARRAY(String), nullable=False),
    Column('dating', Boolean, nullable=False)
)

user_infos = Table(
    'user_infos',
    metadata,
    Column('merge_key', String(100), primary_key=True),
    Column('user_id', BigInteger, nullable=False),
    Column('username', String(50), nullable=False),
    Column('criteria_id', ForeignKey('criteria_matches.id'), nullable=False),
    Column('gender', String(50), nullable=False),
    Column('lang_code', String(50), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('status', Enum(UserStatus, native_enum=False, length=50), nullable=False)
)

match_sessions = Table(
    'match_sessions',
    metadata,
    Column('id', BigInteger, primary_key=True, autoincrement=True),
    Column('match_id', String(256), nullable=False, unique=True),
    Column('user1_id', ForeignKey('user_infos.merge_key'), nullable=False),
    Column('user2_id', ForeignKey('user_infos.merge_key'), nullable=False),
    Column('room_id', String(256), nullable=False),
    Column('compatibility_score', Float, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('status', String(50), nullable=False)
)

async def create_tables():
    """ Создает таблицы в базе данных """
    from src.container import get_container
    container = await get_container()
    engine = await container.get(sqlalchemy.Engine)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    logger.debug("Database tables created successfully")


# Флаг для отслеживания инициализации мапперов
_mappers_initialized = False


async def start_mappers():
    """ Инициализирует мапперы только один раз """
    global _mappers_initialized
    
    if _mappers_initialized: return

    # Маппинг критериев
    mapper_registry.map_imperatively(MatchCriteria, criteria_matches)
    # Маппинг пользователей
    mapper_registry.map_imperatively(User, user_infos, properties={
        'criteria': relationship(MatchCriteria, lazy='selectin')
    })
    # Маппинг матч сессий
    mapper_registry.map_imperatively(Match, match_sessions, properties={
        'user1': relationship(User, foreign_keys=[match_sessions.c.user1_id], lazy='selectin'),
        'user2': relationship(User, foreign_keys=[match_sessions.c.user2_id], lazy='selectin')
    })

    _mappers_initialized = True

    await create_tables()