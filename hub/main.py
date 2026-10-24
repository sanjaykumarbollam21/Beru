import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from hub.config import settings
from hub.db import init_db
from hub.registry import registry
from hub.pairing import router as pairing_router
from hub.ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("beru-hub")

async def heartbeat_watcher():
    while True:
        try:
            await asyncio.sleep(5)
            await registry.check_heartbeat_timeouts(settings.HEARTBEAT_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in heartbeat watcher: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Beru database...")
    init_db()
    watcher_task = asyncio.create_task(heartbeat_watcher())
    logger.info("Beru Hub started.")
    try:
        yield
    finally:
        # Shutdown
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass
        logger.info("Beru Hub shut down.")

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

app.include_router(pairing_router)
app.include_router(ws_router)

@app.get("/")
def root():
    return {"status": "ok", "service": settings.APP_NAME}

@app.get("/health")
def health():
    return {"status": "healthy"}
