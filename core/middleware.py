"""
Middleware for request/response timing. Logs duration per request for dashboard and monitoring.
"""
import logging
import time

logger = logging.getLogger("pricing_engine.request_timing")


class RequestTimingMiddleware:
    """
    Captures request start time and logs total request/response time (ms)
    with method and path. Attaches request_time_ms to the response for downstream use.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000
        path = request.path or ""
        method = getattr(request, "method", "?")
        logger.info(
            "request_timing path=%s method=%s status=%s duration_ms=%.2f",
            path,
            method,
            getattr(response, "status_code", ""),
            duration_ms,
            extra={
                "request_path": path,
                "request_method": method,
                "response_status_code": getattr(response, "status_code", None),
                "duration_ms": round(duration_ms, 2),
            },
        )
        # Expose for dashboard (e.g. custom header or response payload)
        response["X-Request-Duration-Ms"] = f"{duration_ms:.2f}"
        return response
