import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from hub.config import settings
from hub.db import init_db
from hub.registry import registry
from hub.pairing import router as pairing_router
from hub.ws import router as ws_router
from hub.commands import router as commands_router
from hub.voice.ws_voice import router as voice_router
from hub.transfer.api import router as transfer_router
from hub.transfer.store import transfer_store
from hub.personalization.api import router as personalization_router
from hub.skills import init_skills

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("beru-hub")

async def transfer_sweeper():
    while True:
        try:
            await asyncio.sleep(60)
            transfer_store.sweep_expired()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in transfer sweeper: {e}")

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
    init_skills()
    watcher_task = asyncio.create_task(heartbeat_watcher())
    sweeper_task = asyncio.create_task(transfer_sweeper())
    logger.info("Beru Hub started.")
    try:
        yield
    finally:
        # Shutdown
        watcher_task.cancel()
        sweeper_task.cancel()
        for t in (watcher_task, sweeper_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
        logger.info("Beru Hub shut down.")

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

from hub.security.api import router as security_router
from hub.reliability.health import router as health_router

app.include_router(pairing_router)
app.include_router(security_router)
app.include_router(health_router)
app.include_router(ws_router)
app.include_router(commands_router)
app.include_router(voice_router)
app.include_router(transfer_router)
app.include_router(personalization_router)

@app.get("/")
def root():
    return {"status": "ok", "service": settings.APP_NAME}
