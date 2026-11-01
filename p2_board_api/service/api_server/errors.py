from datetime import datetime, timezone


class ApiError(Exception):
    def __init__(self, status, code, message, details=None, request_id=None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details = details or {}
        self.request_id = request_id


def error_body(code, message, details=None, request_id=None):
    return {
        "success": False,
        "error": {"code": code, "message": message, "details": details or {}},
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
