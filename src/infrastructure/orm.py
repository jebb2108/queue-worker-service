from sqlalchemy import MetaData, Table, Column, String, BigInteger, Float, DateTime, Integer, SmallInteger, ARRAY, \
    Boolean, ForeignKey, Enum
from sqlalchemy.orm import registry, Relationship

from src.domain.entities import Match, User
from src.domain.value_objects import MatchCriteria, UserState, UserStatus

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
    Column('id', BigInteger, primary_key=True, autoincrement=True),
    Column('user_id', BigInteger, nullable=False),
    Column('username', String(50), nullable=False),
    Column('criteria_id', ForeignKey('criteria_matches.id'), nullable=False),
    Column('gender', String(50), nullable=False),
    Column('lang_code', String(50), nullable=False),
    Column('created_at', DateTime, nullable=False),
    Column('status', Enum(UserStatus, native_enum=False, length=50), nullable=False)
)

match_sessions = Table(
    'match_sessions',
    metadata,
    Column('id', BigInteger, primary_key=True, autoincrement=True),
    Column('match_id', String(256), nullable=False, unique=True),
    Column('user1_id', ForeignKey('user_infos.id'), nullable=False),
    Column('user2_id', ForeignKey('user_infos.id'), nullable=False),
    Column('room_id', String(256), nullable=False),
    Column('compatibility_score', Float, nullable=False),
    Column('created_at', DateTime, nullable=False),
    Column('status', String(50), nullable=False)
)

def start_mappers():
    from sqlalchemy.orm import clear_mappers
    clear_mappers()
    # Маппинг критериев
    mapper_registry.map_imperatively(MatchCriteria, criteria_matches)
    # Маппинг пользователей
    mapper_registry.map_imperatively(User, user_infos, properties={
        'criteria': Relationship(MatchCriteria)
    })
    # Маппинг матч сессий
    mapper_registry.map_imperatively(Match, match_sessions, properties={
        'user1': Relationship(User, foreign_keys=[match_sessions.c.user1_id]),
        'user2': Relationship(User, foreign_keys=[match_sessions.c.user2_id])
    })