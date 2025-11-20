import os
from dataclasses import dataclass
from datetime import timezone, timedelta
from typing import Dict

from dotenv import load_dotenv

load_dotenv("""../.env""")

@dataclass
class MatchingConfig:
    """Конфигурация для алгоритма матчинга"""
    max_wait_time: int = 150  # секунды
    initial_delay: int = 1  # секунды
    max_retries: int = 20
    compatibility_threshold: float = 0.7

    # Веса для скоринга совместимости
    scoring_weights: Dict[str, float] = None

    def __post_init__(self):
        if self.scoring_weights is None:
            self.scoring_weights = {
                'language': 0.35,
                'fluency': 0.25,
                'topics': 0.20,
                'dating': 0.10,
                'activity': 0.05,
                'success_rate': 0.05
            }

@dataclass
class RedisConfig:
    """ Конфигурация Redis """
    url: str = os.getenv("REDIS_URL")
    gateway_url: str = os.getenv("GATEWAY_REDIS_URL")
    max_connections: int = 20
    retry_on_timeout: bool = True
    socket_timeout: int = 5
    socket_connect_timeout: int = 5


@dataclass
class DatabaseConfig:
    """ Конфигурация PostgresSQL """
    url: str = os.getenv("DATABASE_URL")
    min_size: int = 5
    max_size: int = 20
    timeout: int = 60
    command_timeout: int = 30


@dataclass
class RabbitMQConfig:
    """ Конфигурация RabbitMQ """
    url: str = os.getenv("RABBITMQ_URL")

    # Очереди
    match_queue: str =  "match_requests"
    match_exchange: str = "users"


@dataclass
class TelegranBotConfig:
    """ Конфигурация Telegram Bot"""
    receive_match_url: str = os.getenv("MATCH_RECEIVE_URL")

@dataclass
class WorkerConfig:

    debug: bool = os.getenv("DEBUG", "TRUE")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    timezone: timezone = timezone(timedelta(hours=3))

    # Конфигурации компонентов
    redis: RedisConfig = None
    database: DatabaseConfig = None
    rabbitmq: RabbitMQConfig = None
    matching: MatchingConfig = None
    tgbot: TelegranBotConfig = None

    cache_ttl: int = 300 # в секундах

    # Статусы поиска
    STARTED: str = 'search_started'
    CANCELED: str = 'search_canceled'
    COMPLETED: str = 'search_completed'
    WAITING_TIME_EXPIRED: str = 'waiting_time_expired'


    def __post_init__(self):
        if self.redis is None: self.redis = RedisConfig()
        if self.database is None: self.database = DatabaseConfig()
        if self.rabbitmq is None: self.rabbitmq = RabbitMQConfig()
        if self.matching is None: self.matching = MatchingConfig()
        if self.tgbot is None: self.tgbot = TelegranBotConfig()



config = WorkerConfig()