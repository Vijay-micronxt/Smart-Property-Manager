def ok(data=None, message=None):
    """Standard success response envelope for all customer-facing API endpoints."""
    return {"status": "ok", "message": message, "data": data}


def err(message, code=None):
    """Standard error response envelope for all customer-facing API endpoints."""
    return {"status": "error", "code": code, "message": message}
