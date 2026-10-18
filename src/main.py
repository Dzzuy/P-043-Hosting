import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.agents.copilot.runtime import CopilotAdmission, bounded_io
from src.api.auth import CurrentUserDependency, build_auth_service, create_auth_router
from src.api.copilot import router as copilot_router
from src.api.practice_errors import PracticeAPIError, practice_exception_handler
from src.api.recorded_practice import create_recorded_practice_routers
from src.api.routes import router
from src.api.sales_copilot import router as sales_copilot_router
from src.config import get_settings
from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
from src.integrations.practice_records import SQLPracticeRecordsRepository
from src.integrations.practice_runtime import build_practice_service
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.integrations.voice_usage import SQLVoiceUsageRepository
from src.knowledge.index_readiness import check_copilot_index
from src.knowledge.retrieval_service import get_retrieval_service
from src.observability import CopilotTelemetryMiddleware, TelemetryService, configure_logging
from src.roleplay_tracing import get_roleplay_tracing
from src.services.recorded_practice import RecordedPracticeService
from src.services.sales_conversation_service import SalesConversationService
from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer
from src.services.sales_copilot_assistant import SalesCopilotAssistant
from src.services.voice import VoiceService

logger = logging.getLogger(__name__)


class LazyKnowledgeRetriever:
    """Initialize knowledge storage when used, so liveness can report index failures."""

    def retrieve(self, *args, **kwargs):
        return get_retrieval_service().retrieve(*args, **kwargs)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Application starting env=%s", settings.app_env)
    if settings.app_env == "production":
        created = await auth_service.bootstrap_manager(
            username=settings.bootstrap_manager_username,
            display_name=settings.bootstrap_manager_display_name,
            password=settings.bootstrap_manager_password,
        )
        if created:
            logger.info("Created the initial manager account")
    try:
        # Existing data is reused. Replacing an index is an explicit ingestion action.
        retriever = get_retrieval_service()
        if retriever.vector_store.count() == 0:
            count = await asyncio.to_thread(retriever.ingest_corpus, reset=False)
            logger.info("Initialized empty knowledge index with %d chunks", count)
    except Exception:
        logger.exception("Knowledge startup failed")
        if settings.app_env == "production":
            raise
    try:
        await bounded_io(app.state.copilot_readiness, 45)
        logger.info("Copilot index is ready")
    except Exception as exc:
        logger.warning("Knowledge startup failed (%s)", type(exc).__name__)
    try:
        yield
    finally:
        await asyncio.to_thread(app.state.copilot_telemetry.close)
        await asyncio.to_thread(get_roleplay_tracing().close)
        logger.info("Application shutdown")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(PracticeAPIError, practice_exception_handler)

settings = get_settings()
app.state.copilot_telemetry = TelemetryService(settings)
app.add_middleware(CopilotTelemetryMiddleware, service=app.state.copilot_telemetry)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(router, prefix="/api/v1")
auth_service = build_auth_service(settings)
current_user = CurrentUserDependency(auth_service, settings.auth_cookie_name)
app.state.current_user = current_user
app.state.copilot_readiness = check_copilot_index
app.state.copilot_admission = CopilotAdmission(settings)
app.state.copilot_sessions = SQLCopilotSessionsRepository(
    settings.database_url,
    ttl_hours=settings.copilot_session_ttl_hours,
)


recorded_practice = RecordedPracticeService(
    build_practice_service(retrieval_service=LazyKnowledgeRetriever()),
    SQLPracticeRecordsRepository(settings.database_url),
    auth_service,
)
voice_service = VoiceService(recorded_practice, SQLVoiceUsageRepository(settings.database_url), settings)
practice_router, manager_router = create_recorded_practice_routers(recorded_practice, current_user, voice_service)

# Sales Copilot Initialization
sales_copilot_repo = SQLSalesCopilotRepository(settings.database_url)
sales_copilot_repo.ensure_schema()
app.state.sales_copilot_repository = sales_copilot_repo
app.state.sales_conversation_service = SalesConversationService(sales_copilot_repo)
app.state.sales_copilot_analyzer = SalesCopilotAnalyzer(sales_copilot_repo)
app.state.sales_copilot_assistant = SalesCopilotAssistant(sales_copilot_repo)

app.include_router(create_auth_router(auth_service, settings), prefix="/api/v1")
app.include_router(copilot_router, prefix="/api/v1")
app.include_router(sales_copilot_router, prefix="/api/v1")
app.include_router(practice_router, prefix="/api/v1")
app.include_router(manager_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/ready")
async def ready():
    try:
        await bounded_io(app.state.copilot_readiness, 20)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Copilot index is not ready") from exc
    return {"status": "ready"}
