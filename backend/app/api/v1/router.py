from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.transcriptions import router as transcriptions_router
from app.api.v1.upload import router as upload_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.ai import router as ai_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.teams import router as teams_router
from app.api.v1.admin import router as admin_router
from app.api.v1.vocabulary import router as vocabulary_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.developer import router as developer_router
from app.api.v1.translation import router as translation_router
from app.api.v1.realtime import router as realtime_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(transcriptions_router)
api_router.include_router(upload_router)
api_router.include_router(websocket_router)
api_router.include_router(webhooks_router)
api_router.include_router(ai_router)
api_router.include_router(integrations_router)
api_router.include_router(teams_router)
api_router.include_router(admin_router)
api_router.include_router(vocabulary_router)
api_router.include_router(analytics_router)
api_router.include_router(developer_router)
api_router.include_router(translation_router)
api_router.include_router(realtime_router)
