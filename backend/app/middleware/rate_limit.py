from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time

from app.core.cache import rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """レート制限ミドルウェア"""

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_day: int = 1000,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_day = requests_per_day

    async def dispatch(self, request: Request, call_next) -> Response:
        # 静的ファイルやヘルスチェックは除外
        if request.url.path.startswith(("/static", "/health", "/docs", "/openapi")):
            return await call_next(request)

        # クライアント識別子を取得
        client_id = self._get_client_id(request)

        # 分単位のレート制限
        minute_key = f"rate_limit:minute:{client_id}"
        minute_allowed, minute_remaining, minute_reset = await rate_limiter.is_allowed(
            minute_key,
            self.requests_per_minute,
            60,
        )

        # 日単位のレート制限
        day_key = f"rate_limit:day:{client_id}"
        day_allowed, day_remaining, day_reset = await rate_limiter.is_allowed(
            day_key,
            self.requests_per_day,
            86400,
        )

        # レート制限ヘッダーを設定
        response = await call_next(request) if (minute_allowed and day_allowed) else None

        if response is None:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(minute_reset if not minute_allowed else day_reset),
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": str(minute_remaining),
                    "X-RateLimit-Reset": str(minute_reset),
                },
            )

        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(minute_remaining)
        response.headers["X-RateLimit-Reset"] = str(minute_reset)

        return response

    def _get_client_id(self, request: Request) -> str:
        """クライアント識別子を取得"""
        # APIキーがあればそれを使用
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key[:10]}"

        # 認証ユーザーIDがあればそれを使用
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"

        # IPアドレスを使用
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """リクエストタイミング計測ミドルウェア"""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        response = await call_next(request)

        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"

        return response
