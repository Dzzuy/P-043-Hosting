"""API endpoints for AI Sales Copilot.

Customer workspace endpoints. Private lookup uses the same service as /api/v1/copilot.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from src.api.copilot import current_copilot_user
from src.models.auth import AuthenticatedUser
from src.models.copilot import CopilotQueryRequest, QueryText
from src.models.sales_copilot import (
    ChatMessageCreate,
    ChatMessageResponse,
    ConversationResponse,
    CustomerProfileSnapshot,
    LeadStage,
    MessageDraftResponse,
    NextBestActionResponse,
    SalesPreferences,
)
from src.services.copilot_query import customer_lookup_history, run_copilot_request
from src.services.sales_conversation_service import SalesConversationService
from src.services.sales_agenda_service import SalesAgendaService, validate_interval
from src.services.sales_copilot_analyzer import SalesCopilotAnalyzer
from src.services.sales_copilot_assistant import SalesCopilotAssistant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sales-copilot", tags=["Sales Copilot"])


async def get_current_user(request: Request) -> AuthenticatedUser:
    """Use the same authenticated advisor identity for CRM and private lookup."""
    return await current_copilot_user(request)


async def require_conversation_access(
    conversation_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    repository = request.app.state.sales_copilot_repository
    try:
        await run_in_threadpool(repository.owned_conversation, conversation_id, user.user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.") from exc


class AnalyzeRequest(BaseModel):
    pass


class SalesChatRequest(BaseModel):
    query: QueryText


class UpdateTaskStatusRequest(BaseModel):
    status: Literal["pending", "in_progress", "completed", "cancelled", "needs_review"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"\S")
    priority: Literal["low", "medium", "high"] | None = None
    due_at: datetime | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    item_type: Literal["task", "appointment"] | None = None
    description: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_edit(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set - {"due_at"}):
            raise ValueError("Cần ít nhất một thay đổi hợp lệ.")
        return self


class ProfileFactRequest(BaseModel):
    field: Literal["interested_models", "budget_vnd", "usage_purpose", "payment_method", "down_payment_vnd", "purchase_timeline", "charging_condition"]
    value: Any

    @model_validator(mode="after")
    def validate_value(self):
        profile = CustomerProfileSnapshot.model_validate({self.field: self.value})
        self.value = getattr(profile, self.field)
        if len(str(self.value)) > 2000:
            raise ValueError("Dữ kiện quá dài.")
        if self.field in {"budget_vnd", "down_payment_vnd"} and self.value is not None and self.value < 0:
            raise ValueError("Số tiền phải không âm.")
        return self


class CreateFollowupTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")
    priority: Literal["low", "medium", "high"] = "medium"
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    item_type: Literal["task", "appointment"] = "task"
    description: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_schedule(self):
        validate_interval(self.starts_at, self.ends_at, required=True)
        return self


class CreatePersonalTaskRequest(CreateFollowupTaskRequest):
    customer_id: str | None = Field(default=None, min_length=1, max_length=64)


class UpdateLeadStageRequest(BaseModel):
    stage: LeadStage | None
    reason: str = Field(default="", max_length=400)


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------

@router.get("/dashboard")
async def dashboard(request: Request, user: AuthenticatedUser = Depends(get_current_user),
                    activity_days: int = 7,
                    work_filter: Literal["today", "upcoming", "stale", "unscheduled", "review", "completed"] = "today",
                    work_page: int = Query(default=1, ge=1)):
    if activity_days not in (7, 30):
        raise HTTPException(status_code=422, detail="Chỉ hỗ trợ 7 hoặc 30 ngày.")
    return await run_in_threadpool(SalesAgendaService(request.app.state.sales_copilot_repository).dashboard,
                                  user.user_id, activity_days=activity_days, work_filter=work_filter, work_page=work_page)


@router.get("/calendar")
async def calendar(request: Request, week_start: date, user: AuthenticatedUser = Depends(get_current_user)):
    return await run_in_threadpool(SalesAgendaService(request.app.state.sales_copilot_repository).calendar,
                                  user.user_id, week_start)


@router.get("/tasks/overlaps")
async def task_overlaps(request: Request, starts_at: AwareDatetime, ends_at: AwareDatetime,
                        exclude_id: str | None = None, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        return await run_in_threadpool(SalesAgendaService(request.app.state.sales_copilot_repository).overlaps,
                                      user.user_id, starts_at, ends_at, exclude_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tasks", status_code=201)
async def create_personal_task(payload: CreatePersonalTaskRequest, request: Request,
                               user: AuthenticatedUser = Depends(get_current_user)):
    try:
        return await run_in_threadpool(SalesAgendaService(request.app.state.sales_copilot_repository).create,
                                      user.user_id, payload.model_dump() | {"title": payload.title.strip()})
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng.") from exc

@router.get("/conversations", response_model=list[dict[str, Any]])
async def list_conversations(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List all customer conversations assigned to this sales rep."""
    service: SalesConversationService = request.app.state.sales_conversation_service
    return await run_in_threadpool(service.list_advisor_conversations, user.user_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse,
            dependencies=[Depends(require_conversation_access)])
async def get_conversation_details(
    conversation_id: str,
    request: Request,
    message_limit: int | None = Query(default=None, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get conversation message history and current analysis state."""
    service: SalesConversationService = request.app.state.sales_conversation_service
    details = await run_in_threadpool(service.get_conversation_details, conversation_id, message_limit)
    if not details:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.")
    return details


@router.get("/conversations/{conversation_id}/messages", dependencies=[Depends(require_conversation_access)])
async def get_message_page(
    conversation_id: str, request: Request, before_seq: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=100), source_message_id: str | None = Query(default=None, max_length=120),
):
    if before_seq is not None and source_message_id:
        raise HTTPException(status_code=422, detail="Chỉ chọn một mốc tải tin nhắn.")
    repo = request.app.state.sales_copilot_repository
    try:
        messages = await run_in_threadpool(repo.list_messages, conversation_id, limit=limit,
                                          before_seq=before_seq, source_message_id=source_message_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Tin nguồn không thuộc hội thoại này hoặc đã bị xóa.") from exc
    return {"messages": messages, "next_before_seq": messages[0].seq if messages and messages[0].seq > 1 else None}


@router.patch("/conversations/{conversation_id}/profile-fact", dependencies=[Depends(require_conversation_access)])
async def confirm_profile_fact(
    conversation_id: str, payload: ProfileFactRequest, request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    repo = request.app.state.sales_copilot_repository
    await run_in_threadpool(repo.save_profile_override, conversation_id, payload.field, payload.value, user.user_id)
    service = request.app.state.sales_conversation_service
    details = await run_in_threadpool(service.get_conversation_details, conversation_id, 1)
    return details.profile


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageResponse,
             dependencies=[Depends(require_conversation_access)])
async def send_sales_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Sales sends a new message to the conversation."""
    service: SalesConversationService = request.app.state.sales_conversation_service
    return await run_in_threadpool(service.add_sales_message, conversation_id, payload.content)


@router.post("/conversations/{conversation_id}/analyze", dependencies=[Depends(require_conversation_access)])
async def trigger_conversation_analysis(
    conversation_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Action button: '⚡ Phân tích hội thoại' - Triggers F01, F02, F05, F06."""
    analyzer: SalesCopilotAnalyzer = request.app.state.sales_copilot_analyzer
    try:
        result = await analyzer.analyze_conversation(conversation_id, user.user_id)
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Analysis error")
        raise HTTPException(status_code=500, detail=f"Lỗi khi phân tích hội thoại: {exc}")


@router.get("/preferences", response_model=SalesPreferences)
async def get_preferences(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get sales feature flags for F03 (NBA) and F04 (Drafting)."""
    repo = request.app.state.sales_copilot_repository
    return await run_in_threadpool(repo.get_preferences, user.user_id)


@router.patch("/preferences", response_model=SalesPreferences)
async def update_preferences(
    payload: SalesPreferences,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Update sales feature flags."""
    repo = request.app.state.sales_copilot_repository
    payload.advisor_id = user.user_id
    return await run_in_threadpool(repo.update_preferences, payload)


@router.post("/conversations/{conversation_id}/recommendations", response_model=NextBestActionResponse,
             dependencies=[Depends(require_conversation_access)])
async def get_next_best_actions(
    conversation_id: str,
    request: Request,
    force: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """F03 Next Best Action: Auto-triggered when toggle is ON."""
    assistant: SalesCopilotAssistant = request.app.state.sales_copilot_assistant
    return await assistant.generate_next_best_actions(conversation_id, user.user_id, force=force)


@router.post("/conversations/{conversation_id}/draft", response_model=MessageDraftResponse,
             dependencies=[Depends(require_conversation_access)])
async def generate_message_draft(
    conversation_id: str,
    request: Request,
    force: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """F04 AI Message Drafting: Auto-triggered when toggle is ON."""
    assistant: SalesCopilotAssistant = request.app.state.sales_copilot_assistant
    return await assistant.generate_message_draft(conversation_id, user.user_id, force=force)


@router.get("/conversations/{conversation_id}/draft", response_model=dict[str, Any] | None,
            dependencies=[Depends(require_conversation_access)])
async def get_saved_message_draft(
    conversation_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Read the saved draft without triggering retrieval or an LLM call."""
    repo = request.app.state.sales_copilot_repository
    return await run_in_threadpool(repo.get_latest_recommendation, conversation_id, "draft")


@router.post("/conversations/{conversation_id}/tasks", status_code=201,
             dependencies=[Depends(require_conversation_access)])
async def create_followup_task(
    conversation_id: str,
    payload: CreateFollowupTaskRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return await run_in_threadpool(
            SalesAgendaService(request.app.state.sales_copilot_repository).create,
            user.user_id, payload.model_dump() | {"title": payload.title.strip()},
            conversation_id=conversation_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.") from exc


@router.post("/conversations/{conversation_id}/copilot-chat")
async def copilot_contextual_chat(
    conversation_id: str,
    payload: SalesChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(current_copilot_user),
):
    """Private, durable customer lookup through the shared Copilot workflow."""
    return await run_copilot_request(
        CopilotQueryRequest(query=payload.query), request, user,
        background_tasks=background_tasks, customer_conversation_id=conversation_id,
    )


@router.post("/conversations/{conversation_id}/copilot-chat/stream")
async def stream_customer_lookup(
    conversation_id: str, payload: SalesChatRequest, request: Request,
    background_tasks: BackgroundTasks, user=Depends(current_copilot_user),
):
    return await run_copilot_request(
        CopilotQueryRequest(query=payload.query), request, user, stream=True,
        background_tasks=background_tasks, customer_conversation_id=conversation_id,
    )


@router.get("/conversations/{conversation_id}/copilot-chat")
async def get_customer_lookup_history(
    conversation_id: str, request: Request, user=Depends(current_copilot_user),
    before_seq: int | None = Query(default=None, ge=1), limit: int = Query(default=20, ge=1, le=100),
):
    return await customer_lookup_history(request, user, conversation_id, before_seq=before_seq, limit=limit)


@router.patch("/conversations/{conversation_id}/lead-stage", dependencies=[Depends(require_conversation_access)])
async def update_lead_stage(
    conversation_id: str, payload: UpdateLeadStageRequest, request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    service: SalesConversationService = request.app.state.sales_conversation_service
    try:
        return await run_in_threadpool(service.update_lead_stage, conversation_id, user.user_id,
                                      payload.stage, payload.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.") from exc


@router.patch("/tasks/{task_id}")
async def update_task_status(
    task_id: str,
    payload: UpdateTaskStatusRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Mark follow-up task done, rescheduled, or cancelled."""
    try:
        task = await run_in_threadpool(SalesAgendaService(request.app.state.sales_copilot_repository).edit,
                                      user.user_id, task_id, payload.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhiệm vụ.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "success", "task_id": task_id, "new_status": payload.status, "task": task}


@router.post("/seed-demo-data")
async def seed_demo_data(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Seed or re-sync the 3 real customer conversations from message_sales.docx."""
    service: SalesConversationService = request.app.state.sales_conversation_service
    res = await run_in_threadpool(service.seed_real_conversations_from_docx, "data/message_sales.docx", user.user_id)
    return {"status": "success", "seeded": res}
