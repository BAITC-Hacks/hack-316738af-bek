"""Small, public errors. Internal exception text must never reach the client."""


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        super().__init__(code)
        self.status = status
        self.body = {"code": code, "message": message, "retryable": retryable}


def not_found():
    return APIError(404, "not_found", "Талдау немесе сұралған дерек табылмады.")


def conflict(code="revision_conflict", message="Талдау өзгерді. Күйін жаңартып, қайта көріңіз."):
    return APIError(409, code, message, True)
