"""
Domain exceptions - исключения бизнес-логики
"""


class DomainException(Exception):
    """Базовое исключение для domain слоя"""
    pass


class MatchingException(DomainException):
    """Исключения связанные с процессом матчинга"""
    pass


class UserNotFoundException(DomainException):
    """Пользователь не найден"""
    pass


class IncompatibleUsersException(MatchingException):
    """Пользователи несовместимы для матчинга"""
    pass


class InvalidCriteriaException(DomainException):
    """Некорректные критерии поиска"""
    pass


class MatchCreationException(MatchingException):
    """Ошибка создания матча"""
    pass


class UserAlreadyInSearch(Exception):
    pass
