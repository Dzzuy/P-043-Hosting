"""Authenticated HTTP adapters for the shared Copilot service."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response

from src.agents.copilot.graph import copilot_agent  # noqa: F401 - compatibility for existing integrations
from src.integrations.copilot_sessions import CopilotSessionNotFoundError
from src.models.auth import UserRole
from src.models.copilot import CopilotQueryRequest, CopilotQueryResponse, SalesKnowledgeQueryRequest
from src.observability import span
from src.services.copilot_query import (  # noqa: F401 - public compatibility
    advisor_lookup_history,
    query_copilot,
    run_copilot_request,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/copilot", tags=["Copilot"])

async def current_copilot_user(request: Request):
    with span("authentication"):
        identity = await request.app.state.current_user(request)
        if identity.role != UserRole.ADVISOR:
            raise HTTPException(status_code=403, detail="Advisor access required.")
        return identity


@router.post("/query", response_model=CopilotQueryResponse)
async def query_session_copilot(
    payload: CopilotQueryRequest, request: Request,
    background_tasks: BackgroundTasks, user=Depends(current_copilot_user),
):
    return await run_copilot_request(payload, request, user, background_tasks=background_tasks)


@router.get("/knowledge")
async def get_advisor_knowledge_history(
    request: Request, user=Depends(current_copilot_user),
    before_seq: int | None = Query(default=None, ge=1), limit: int = Query(default=20, ge=1, le=100),
):
    return await advisor_lookup_history(request, user, before_seq=before_seq, limit=limit)


@router.post("/knowledge", response_model=CopilotQueryResponse)
async def query_advisor_knowledge(
    payload: SalesKnowledgeQueryRequest, request: Request,
    background_tasks: BackgroundTasks, user=Depends(current_copilot_user),
):
    return await run_copilot_request(
        CopilotQueryRequest(query=payload.query), request, user,
        background_tasks=background_tasks, advisor_lookup=True,
    )


@router.post("/knowledge/stream")
async def stream_advisor_knowledge(
    payload: SalesKnowledgeQueryRequest, request: Request,
    background_tasks: BackgroundTasks, user=Depends(current_copilot_user),
):
    return await run_copilot_request(
        CopilotQueryRequest(query=payload.query), request, user,
        background_tasks=background_tasks, advisor_lookup=True, stream=True,
    )


@router.post("/query/stream")
async def stream_copilot_query(
    payload: CopilotQueryRequest, request: Request,
    background_tasks: BackgroundTasks, user=Depends(current_copilot_user),
):
    return await run_copilot_request(payload, request, user, background_tasks=background_tasks, stream=True)


@router.get("/sessions")
async def list_copilot_sessions(
    request: Request, user=Depends(current_copilot_user)
) -> list[dict[str, Any]]:
    repository = request.app.state.copilot_sessions
    return await asyncio.to_thread(repository.list_conversations, user.user_id)


@router.get("/sessions/{session_id}")
async def get_copilot_session_detail(
    session_id: str, request: Request, user=Depends(current_copilot_user)
) -> dict[str, Any]:
    repository = request.app.state.copilot_sessions
    try:
        return await asyncio.to_thread(repository.get_conversation_detail, session_id, user.user_id)
    except CopilotSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên Copilot.") from exc


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_copilot_session(session_id: str, request: Request, user=Depends(current_copilot_user)):
    try:
        await asyncio.to_thread(request.app.state.copilot_sessions.delete, session_id, user.user_id)
    except CopilotSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên Copilot.") from exc
    return Response(status_code=204)


@router.get("/sources/{document_id}")
async def get_source_document(
    document_id: str, chunk_id: str | None = None, user=Depends(current_copilot_user)
) -> dict[str, Any]:
    path = Path("data/knowledge/corpus.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy kho tài liệu.")
    try:
        items = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
        for item in items:
            if item.get("document_id") == document_id:
                result = dict(item)
                if chunk_id:
                    from src.knowledge.chunking import load_and_chunk_corpus

                    chunks = await asyncio.to_thread(load_and_chunk_corpus, path)
                    target_chunk = next((c for c in chunks if c.chunk_id == chunk_id), None)
                    if target_chunk:
                        result["chunk"] = {
                            "chunk_id": target_chunk.chunk_id,
                            "content": target_chunk.content,
                            "section": getattr(target_chunk.metadata, "section", None),
                            "headers": getattr(target_chunk.metadata, "headers", None),
                        }
                return result
    except Exception as exc:
        logger.warning("Source lookup failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Không thể đọc tài liệu lúc này.") from None
    raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
