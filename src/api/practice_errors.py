"""Stable, localized errors scoped to Practice and its voice/review routes."""

import logging
from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from src.agents.roleplay.customer_agent import CustomerResponseError
from src.agents.roleplay.graph import RoleplaySessionConflictError
from src.agents.roleplay.turn_analyzer import TurnAnalysisError
from src.services.practice import PracticeEvaluationUnavailableError
from src.services.practice_records import AssignmentConflictError, ReviewConflictError
from src.services.voice import MAX_AUDIO_SECONDS

logger = logging.getLogger(__name__)

PracticeErrorCode = Literal[
    "session_finished",
    "session_busy",
    "session_not_found",
    "forbidden",
    "unauthenticated",
    "provider_unavailable",
    "message_not_sent",
    "assignment_conflict",
    "review_conflict",
    "evaluation_failed",
    "voice_not_configured",
    "voice_invalid_audio",
    "voice_too_long",
    "voice_failed",
    "validation_error",
    "rate_limited",
]

ERRORS: dict[PracticeErrorCode, tuple[int, str]] = {
    "message_not_sent": (503, "Chưa gửi được tin nhắn. Vui lòng gửi lại."),
    "assignment_conflict": (409, "Không thể giao hoặc bắt đầu bài luyện tập này."),
    "review_conflict": (409, "Không thể duyệt lượt luyện tập này."),
    "session_finished": (409, "Phiên luyện tập đã kết thúc và không nhận thêm tin nhắn."),
    "session_busy": (409, "Khách hàng đang trả lời, vui lòng đợi giây lát."),
    "session_not_found": (404, "Không tìm thấy phiên luyện tập."),
    "forbidden": (403, "Bạn không có quyền thực hiện thao tác này."),
    "unauthenticated": (401, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."),
    "provider_unavailable": (503, "Hệ thống AI tạm thời gián đoạn. Tin nhắn của bạn đã được lưu, hãy thử lại."),
    "evaluation_failed": (503, "Chưa thể chấm điểm lúc này. Vui lòng thử lại."),
    "voice_not_configured": (503, "Tính năng giọng nói chưa được cấu hình. Vui lòng nhập bằng bàn phím."),
    "voice_invalid_audio": (422, "Bản ghi không hợp lệ hoặc quá lớn. Vui lòng ghi lại."),
    "voice_too_long": (422, f"Bản ghi dài hơn {MAX_AUDIO_SECONDS} giây. Vui lòng ghi ngắn hơn."),
    "voice_failed": (502, "Không chuyển được giọng nói thành chữ. Vui lòng thử lại."),
    "validation_error": (422, "Nội dung gửi lên chưa hợp lệ."),
    "rate_limited": (429, "Bạn đã đạt giới hạn sử dụng. Vui lòng thử lại sau."),
}


class PracticeAPIError(HTTPException):
    def __init__(self, code: PracticeErrorCode, *, status_code: int | None = None, detail: str | None = None) -> None:
        default_status, message = ERRORS[code]
        super().__init__(status_code=status_code or default_status, detail=detail or message)
        self.code = code


async def practice_exception_handler(request: Request, exc: PracticeAPIError) -> JSONResponse:
    cause = exc.__cause__
    log = logger.warning if exc.status_code >= 500 else logger.info
    log(
        "practice_request_failed code=%s status=%d error_type=%s",
        exc.code,
        exc.status_code,
        type(cause).__name__ if cause else type(exc).__name__,
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})


def session_conflict(exc: Exception) -> PracticeAPIError:
    """Graph/reducer errors distinguish terminal state from an outstanding reply."""
    if isinstance(exc, RoleplaySessionConflictError):
        return PracticeAPIError(exc.code, status_code=409)
    return PracticeAPIError("validation_error", status_code=409)


# The records subsystem currently exposes legacy reason strings. Translate only
# known reasons; unknown diagnostics must never become client-visible text.
CONFLICT_REASONS = {
    "Advisor does not exist or is inactive.": "Tư vấn viên không tồn tại hoặc đã ngừng hoạt động.",
    "Practice scenario was not found.": "Không tìm thấy kịch bản luyện tập.",
    "Due date cannot be in the past.": "Hạn hoàn thành không được ở trong quá khứ.",
    "Assignment does not match this advisor and scenario.": "Bài được giao không khớp với tư vấn viên và kịch bản này.",
    "Assignment is already completed.": "Bài được giao này đã hoàn thành.",
    "attempt is unfinished or already reviewed": "Lượt luyện tập chưa hoàn thành hoặc đã được duyệt.",
    "attempt is already reviewed": "Lượt luyện tập này đã được duyệt.",
    "only assessed criteria may receive score overrides": "Chỉ được sửa điểm của tiêu chí đã được đánh giá.",
}


class PracticeRoute(APIRoute):
    """Translate shared dependency HTTP failures only within these routers."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except PracticeAPIError:
                raise
            except PracticeEvaluationUnavailableError as exc:
                raise PracticeAPIError("evaluation_failed") from exc
            except TurnAnalysisError as exc:
                raise PracticeAPIError("message_not_sent") from exc
            except AssignmentConflictError as exc:
                raise PracticeAPIError("assignment_conflict", detail=CONFLICT_REASONS.get(str(exc))) from exc
            except ReviewConflictError as exc:
                raise PracticeAPIError("review_conflict", detail=CONFLICT_REASONS.get(str(exc))) from exc
            except CustomerResponseError as exc:
                raise PracticeAPIError("provider_unavailable") from exc
            except HTTPException as exc:
                codes: dict[int, PracticeErrorCode] = {
                    401: "unauthenticated",
                    403: "forbidden",
                    429: "rate_limited",
                }
                if exc.status_code in codes:
                    raise PracticeAPIError(codes[exc.status_code]) from exc
                raise

        return handler
