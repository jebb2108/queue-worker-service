import os
from dataclasses import dataclass
from datetime import timezone, timedelta

from dotenv import load_dotenv

load_dotenv("""../.env""")

@dataclass
class RedisConfig:
    """ Конфигурация Redis """
    url: str = "redis://localhost:6379/0"
    max_connections: int = 20
    retry_on_timeout: bool = True
    socket_timeout: int = 5
    socket_connect_timeout: int = 5


@dataclass
class DatabaseConfig:
    """ Конфигурация PostgresSQL """
    url: str = "postgresql://"
    min_size: int = 5
    max_size: int = 20
    timeout: int = 60
    command_timeout: int = 30


@dataclass
class RabbitMQConfig:
    """ Конфигурация RabbitMQ """
    url: str = "amqp://"

    # Очереди
    match_queue: str =  "match_requests"

@dataclass
class WorkerConfig:

    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    timezone: timezone = timezone(timedelta(hours=3))

    # Конфигурации компонентов
    redis: RedisConfig = None
    database: DatabaseConfig = None
    rabbitmq: RabbitMQConfig = None


    def __post_init__(self):
        if self.redis is None: self.redis = RedisConfig()
        if self.database is None: self.database = DatabaseConfig()
        if self.rabbitmq is None: self.rabbitmq = RabbitMQConfig()



config = WorkerConfig()