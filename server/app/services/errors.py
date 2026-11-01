"""Доменные ошибки: сервисный слой бросает их, а main.py превращает в единый JSON-ответ."""


class DomainError(Exception):
    """Базовая ошибка бизнес-логики. status_code и code попадают в ответ API."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    """Операция невозможна в текущем состоянии объекта (409)."""

    status_code = 409
    code = "conflict"


class RuleViolationError(DomainError):
    """Данные корректны по формату, но нарушают бизнес-правило (422)."""

    status_code = 422
    code = "rule_violation"
