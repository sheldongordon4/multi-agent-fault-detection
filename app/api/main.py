import asyncio
import logging
from contextlib import asynccontextmanager
from logging.config import fileConfig
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import app_configs, settings
from app.faults.router import router as faults_router
from app.notification.router import router as notification_router
from app.persistence.router import router as tickets_router
from app.streaming.router import router as streaming_router

# Wire logging from app/logging.ini if it's valid; otherwise a sane default.
_LOG_INI = Path(__file__).resolve().parents[1] / "logging.ini"
try:
    fileConfig(_LOG_INI, disable_existing_loggers=False)
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-5s [%(name)s] %(message)s")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic — run `alembic -c app/alembic.ini upgrade head`
    # before starting the app (see README run steps).
    worker_tasks = []

    if settings.KAFKA_ENABLED:
        try:
            from app.kafka.admin import ensure_topics
            from app.kafka.workers import start_workers
            from app.ml.scoring import warm_models

            await asyncio.to_thread(ensure_topics)

            # Load (and if needed train) the models here, in the parent, before any
            # events arrive. Detection scores in a process pool; without warming,
            # several workers could discover a missing model file at once and race
            # to train and write the same artefact.
            try:
                await asyncio.to_thread(warm_models)
            except Exception:
                logger.exception("Model warm-up failed; workers will load on demand")

            worker_tasks = start_workers()

            # Spawn the ML worker processes in the background so the ~4s cold
            # start doesn't land on the first fault event. Not awaited: startup
            # shouldn't block on it, and run_ml works either way.
            from app.kafka.executors import prewarm_ml

            worker_tasks.append(asyncio.create_task(prewarm_ml(), name="ml-prewarm"))
        except Exception:
            logger.exception("Could not start Kafka workers (is Kafka up?); continuing")

    try:
        yield
    finally:
        if worker_tasks:
            from app.kafka.workers import stop_workers

            await stop_workers(worker_tasks)

        # Executors own OS threads and child processes — they must not outlive the
        # app or reload/shutdown hangs.
        from app.kafka.executors import shutdown_executors

        shutdown_executors()


app = FastAPI(lifespan=lifespan, **app_configs)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # No auth/cookies (operator dashboard), and `allow_origins=["*"]` + credentials
    # is rejected by browsers anyway — so credentials stay off.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=settings.CORS_HEADERS,
)

app.include_router(faults_router)
app.include_router(notification_router)
app.include_router(streaming_router)
app.include_router(tickets_router)


@app.get("/health")
async def health_check():
    """Liveness — the process is up."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    """Readiness — Postgres and Kafka are reachable."""
    checks: dict[str, str] = {}

    try:
        from sqlalchemy import text

        from app.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"[:160]

    try:
        from confluent_kafka.admin import AdminClient

        admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
        md = await asyncio.to_thread(admin.list_topics, None, 5)
        checks["kafka"] = "ok" if md.brokers else "no brokers"
    except Exception as exc:  # noqa: BLE001
        checks["kafka"] = f"error: {exc}"[:160]

    ready = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503, content={"ready": ready, "checks": checks}
    )
