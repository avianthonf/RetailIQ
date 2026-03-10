from datetime import datetime, timezone
from flask import jsonify

class APIError(Exception):
    """Generates a standard error payload that the global handler can catch."""
    def __init__(self, message, status_code=400, errors=None, meta=None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.errors = errors
        self.meta = meta

def standard_json(success=True, message="Success", data=None, error=None, meta=None, status_code=200):
    """
    Standard Response Envelope.
    All modules should use this to ensure consistent frontend payload parsing.
    """
    payload = {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": meta,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    response = jsonify(payload)
    response.status_code = status_code
    return response
