"""服务入口。后端同时托管前端静态页面，开箱即可访问 http://127.0.0.1:8000 。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import FRONTEND_DIR

app = FastAPI(
    title="青少年运动健康 - 健康档案理解与一人一策运动处方",
    version="0.1.0",
    description="健康档案理解与个性化运动处方生成服务。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if FRONTEND_DIR.is_dir():

    class NoCacheStaticFiles(StaticFiles):
        """静态资源强制走协商缓存（304），避免浏览器用启发式缓存拿到旧 JS 配新 HTML。"""

        def file_response(self, *args, **kwargs):  # type: ignore[override]
            response = super().file_response(*args, **kwargs)
            response.headers["Cache-Control"] = "no-cache"
            return response

    app.mount("/static", NoCacheStaticFiles(directory=FRONTEND_DIR), name="static")

    _NO_CACHE = {"Cache-Control": "no-cache"}

    @app.get("/", include_in_schema=False)
    @app.get("/report", include_in_schema=False)
    def report() -> FileResponse:
        """运动处方报告页（纯 HTML 流式页面，自适应窗口宽度）。

        作为默认入口：打开即呈现空白报告版式，选择档案生成后再填充内容。
        """
        return FileResponse(FRONTEND_DIR / "report.html", headers=_NO_CACHE)

    @app.get("/profile", include_in_schema=False)
    def profile() -> FileResponse:
        """健康档案理解报告页：展示第一阶段画像（基础评价、六维、安全评估等）各字段。"""
        return FileResponse(FRONTEND_DIR / "profile.html", headers=_NO_CACHE)
