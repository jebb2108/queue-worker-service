import logging
import sys

from colorama import init, Fore, Style
from src.config import config


class RootLogger:
    """Простой логгер, работающий с корневым регистром"""

    def __init__(self):
        # Базовая конфигурация корневого логгера
        logging.basicConfig(
            level=self.convert_level(config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
        self.root_logger = logging.getLogger()


    def setup_logger(self, name: str, level: str | int = config.log_level):
        """Добавляет логгер с указанным именем и уровнем"""
        logger = logging.getLogger(name)
        logger.setLevel(self.convert_level(level))
        return logger

    @staticmethod
    def convert_level(level: str | int):
        """Возвращает числовое значение"""
        if isinstance(level, str):
            level = level.strip().upper()
        return logging.getLevelName(level)


class CustomLogger:
    """ Класс для отображения кастомного логера"""

    init()      # Инициализация colorama для
                # кроссплатформенной поддержки цветов

    class ColorFormatter(logging.Formatter):
        """Кастомный форматтер с цветовым выделением только уровней логирования"""
        # Цвета для разных уровней логирования
        LEVEL_COLORS = {
            "DEBUG": Fore.CYAN,
            "INFO": Fore.GREEN,
            "WARNING": Fore.YELLOW,
            "ERROR": Fore.RED,
            "CRITICAL": Fore.RED + Style.BRIGHT,
        }

        # Фиксированная ширина для уровней логирования (по самому длинному слову "CRITICAL")
        LEVEL_WIDTH = 8

        def __init__(self, fmt=None, datefmt=None):
            # Базовый формат с фиксированными расстояниями (уровень ДО имени)
            # Добавлена дата и центрирование названия модуля
            base_fmt = (
                f"%(asctime)s - %(levelname){self.LEVEL_WIDTH}s - %(name)-20s - %(message)s"
            )
            super().__init__(fmt or base_fmt, datefmt)

        def format(self, record):
            # Сохраняем оригинальный уровень
            original_levelname = record.levelname

            # Выравниваем уровень по ширине перед добавлением цвета
            padded_levelname = original_levelname.ljust(self.LEVEL_WIDTH)

            # Добавляем цвет только к уровню логирования
            colored_levelname = (
                self.LEVEL_COLORS.get(record.levelname, "")
                + padded_levelname
                + Style.RESET_ALL
            )

            # Центрируем имя модуля
            name = record.name
            name_width = 20  # Ширина для центрирования
            if len(name) > name_width:
                name = name[: name_width - 3] + "..."
            centered_name = name.center(name_width)

            # Временно заменяем уровень на цветную версию, а имя - на центрированное
            record.levelname = colored_levelname
            record.name = centered_name

            # Форматируем запись (остальной текст будет белым по умолчанию)
            formatted = super().format(record)

            # Восстанавливаем оригинальный уровень и имя
            record.levelname = original_levelname
            record.name = name

            return formatted


    def setup_logger(self, name=None, level: str | int = config.log_level, name_width=20):
        """Настройка логгера с цветным выводом только уровней"""

        # Создаем логгер
        logger = logging.getLogger(name)

        # Устанавливаем уровень
        logger.setLevel(self.convert_level(level))

        # Очищаем существующие обработчики
        logger.handlers.clear()

        # Создаем консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)

        # Устанавливаем уровень
        console_handler.setLevel(self.convert_level(level))

        # Настраиваем форматтер с датой и центрированным именем
        # Добавляем дату в формат времени и центрируем имя модуля
        formatter = self.ColorFormatter(
            fmt=f"%(asctime)s - %(levelname){self.ColorFormatter.LEVEL_WIDTH}s - %(name)-{name_width}s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",  # Добавлена дата к времени
        )
        console_handler.setFormatter(formatter)

        # Добавляем обработчик к логгеру
        logger.addHandler(console_handler)

        return logger

    @staticmethod
    def convert_level(level):
        """Возвращает числовое значение"""
        if isinstance(level, str):
            level = level.strip().upper() # Форматирую dEbUG -> DEBUG
        return logging.getLevelName(level)


opt_logger = RootLogger() if config.debug else  CustomLogger()
