"""
API-level rate limit middleware

Supports two modes:
1. Redis distributed rate limiting (production)
2. In-memory rate limiting (development/test)
"""

from collections import defaultdict, deque
import logging
import time
from typing import Deque, Dict, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from config import settings

logger = logging.getLogger(__name__)

PUBLIC_RATE_LIMIT_PATH_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/contexts",
    "/api/v1/config:public",
)


def _append_vary_header(response: Response, value: str) -> None:
    """Append a value to the Vary header without duplicating it."""
    existing = response.headers.get("Vary")
    if not existing:
        response.headers["Vary"] = value
        return

    values = [item.strip() for item in existing.split(",") if item.strip()]
    if value not in values:
        response.headers["Vary"] = ", ".join([*values, value])


def apply_cors_headers(request: Request, response: Response) -> Response:
    """Apply CORS headers for early middleware responses that bypass CORSMiddleware."""
    origin = request.headers.get("origin")

    # No Origin header -> no CORS needed (non-browser/server-to-server requests)
    if origin is None or origin == "":
        return response

    # Handle Origin: null (e.g., file:// protocol) only if explicitly allowed
    if origin == "null":
        if settings.cors_allow_null_origin:
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = settings.allowed_methods
            response.headers["Access-Control-Allow-Headers"] = settings.allowed_headers
        return response

    allowed_origins = settings.cors_origins_list
    if "*" in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = settings.allowed_methods
        response.headers["Access-Control-Allow-Headers"] = settings.allowed_headers
        return response

    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = settings.allowed_methods
        response.headers["Access-Control-Allow-Headers"] = settings.allowed_headers
        _append_vary_header(response, "Origin")

    return response


def get_request_client_ip(request: Request) -> str:
    """Get the originating client IP, preferring the first forwarded IP."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        for candidate in forwarded.split(","):
            candidate = candidate.strip()
            if candidate:
                return candidate

    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def should_apply_rate_limit(request: Request) -> bool:
    """Apply rate limiting only to public client-facing endpoints."""
    if request.method == "OPTIONS":
        return False

    path = request.url.path
    return path.startswith(PUBLIC_RATE_LIMIT_PATH_PREFIXES)


def check_memory_sliding_window(
    history_map: Dict[str, Deque[float]],
    key: str,
    *,
    max_requests: int,
    window_seconds: int,
) -> Tuple[bool, int]:
    """Shared in-memory sliding-window limiter.

    Keeps only timestamps inside the window and returns remaining capacity.
    """
    now = time.time()
    history = history_map.get(key)
    if history is None:
        history = deque()
        history_map[key] = history

    while history and now - history[0] >= window_seconds:
        history.popleft()

    if not history:
        history_map.pop(key, None)
        history = deque()
        history_map[key] = history

    if len(history) >= max_requests:
        return False, 0

    history.append(now)
    remaining = max(0, max_requests - len(history))
    return True, remaining


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limit middleware

    Supports both Redis distributed and in-memory rate limiting
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        use_redis: bool = True,
    ):
        """
        Initialize rate limit middleware

        Args:
            app: FastAPI application instance
            requests_per_minute: Maximum requests allowed per minute
            burst_size: Number of burst requests allowed in a short period
            use_redis: Whether to use Redis (recommended for production)
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.use_redis = use_redis

        self.request_history: Dict[str, Deque[float]] = defaultdict(deque)
        self.burst_counters: Dict[str, int] = defaultdict(int)
        self.last_burst_reset: float = time.time()

        self._redis_service = None
        self._redis_loop_id: Optional[int] = None

    async def _get_redis(self):
        """Get Redis service (lazy initialization)"""
        if not self.use_redis:
            return None

        try:
            import asyncio
            from services.redis_service import get_redis

            loop_id = id(asyncio.get_running_loop())
            if self._redis_service is None or self._redis_loop_id != loop_id:
                self._redis_service = await get_redis()
                self._redis_loop_id = loop_id
        except Exception as e:
            logger.warning(f"Redis not available, falling back to memory: {e}")
            self.use_redis = False
            self._redis_service = None
            self._redis_loop_id = None

        return self._redis_service

    async def dispatch(self, request: Request, call_next):
        """Process each request"""
        if not should_apply_rate_limit(request):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        allowed, remaining = await self._check_rate_limit(client_ip)

        if not allowed:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests, please try again later",
                    "error": "rate_limit_exceeded",
                },
            )
            response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = "0"
            return apply_cors_headers(request, response)

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        return get_request_client_ip(request)

    async def _check_rate_limit(self, ip: str) -> Tuple[bool, int]:
        """
        Check whether rate limit is exceeded

        Args:
            ip: Client IP address

        Returns:
            (allowed, remaining_requests)
        """
        redis = await self._get_redis()
        if redis:
            try:
                key = f"rate:ip:{ip}"
                allowed, remaining = await redis.check_rate_limit(
                    key,
                    max_requests=self.requests_per_minute,
                    window_seconds=60,
                )
                return allowed, remaining
            except Exception as e:
                logger.warning(f"Redis rate limit error, falling back to memory: {e}")

        return self._check_memory_rate_limit(ip)

    def _check_memory_rate_limit(self, ip: str) -> Tuple[bool, int]:
        """
        In-memory rate limiting (fallback)

        Args:
            ip: Client IP address

        Returns:
            (allowed, remaining_requests)
        """
        current_time = time.time()

        if current_time - self.last_burst_reset > 1:  # Reset burst count every second
            self.burst_counters.clear()
            self.last_burst_reset = current_time

        if self.burst_counters[ip] >= self.burst_size:
            logger.debug(f"Burst rate limit exceeded for IP: {ip}")
            return False, 0

        allowed, remaining = check_memory_sliding_window(
            self.request_history,
            ip,
            max_requests=self.requests_per_minute,
            window_seconds=60,
        )
        if not allowed:
            logger.debug(f"Minute rate limit exceeded for IP: {ip}")
            return False, 0

        self.burst_counters[ip] += 1
        return True, remaining
