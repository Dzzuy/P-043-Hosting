"""Practice-only translation must not change shared authentication routes."""

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from src.api.practice_errors import PracticeAPIError, PracticeRoute, practice_exception_handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "detail"),
    [
        (401, "unauthenticated", "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."),
        (403, "forbidden", "Bạn không có quyền thực hiện thao tác này."),
        (429, "rate_limited", "Bạn đã đạt giới hạn sử dụng. Vui lòng thử lại sau."),
    ],
)
async def test_scoped_dependency_errors_leave_other_routes_unchanged(status, code, detail):
    from fastapi import APIRouter, Depends

    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)

    async def failing_dependency():
        raise HTTPException(status_code=status, detail="Existing other-route error")

    router = APIRouter(route_class=PracticeRoute)

    @router.get("/practice", dependencies=[Depends(failing_dependency)])
    async def practice():
        return {}

    @app.get("/other", dependencies=[Depends(failing_dependency)])
    async def other():
        return {}

    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/practice")
        assert response.status_code == status
        assert response.json() == {"code": code, "detail": detail}
        other_response = await client.get("/other")
        assert other_response.status_code == status
        assert other_response.json() == {"detail": "Existing other-route error"}


def test_main_registers_only_practice_error_handler():
    from src.main import app

    assert app.exception_handlers[PracticeAPIError] is practice_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException

    assert app.exception_handlers[StarletteHTTPException] is not practice_exception_handler
