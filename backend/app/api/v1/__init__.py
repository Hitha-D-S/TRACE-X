"""API v1 router aggregator."""
from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.transactions import router as tx_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.graph import router as graph_router
from app.api.v1.entities import router as entities_router
from app.api.v1.replay import router as replay_router
from app.api.v1.investigation import router as investigation_router
from app.api.v1.evaluation import router as evaluation_router
from app.api.v1.websocket import router as ws_router
from app.api.v1.upload import router as upload_router
from app.api.v1.datasets import router as datasets_router

router = APIRouter()
router.include_router(health_router, tags=["System"])
router.include_router(tx_router, prefix="/transactions", tags=["Transactions"])
router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
router.include_router(graph_router, prefix="/graph", tags=["Graph"])
router.include_router(entities_router, prefix="/entities", tags=["Entities"])
router.include_router(replay_router, prefix="/replay", tags=["Replay"])
router.include_router(investigation_router, prefix="/investigations", tags=["Investigation"])
router.include_router(evaluation_router, prefix="/evaluation", tags=["Evaluation"])
router.include_router(ws_router, tags=["Streaming"])
router.include_router(upload_router, prefix="/transactions", tags=["Upload"])
router.include_router(datasets_router, prefix="/datasets", tags=["Datasets"])
