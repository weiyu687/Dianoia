from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from . import admin, agent, ai, auth, digital_courses, exams, lesson_templates, lessons, mind_maps, presentations, resources
from .db import engine
from .learning_analytics.router import router as learning_analytics_router
from .migrate import initialize_database
from .question_banks.router import router as question_bank_router
from .models import AgentMessage


@asynccontextmanager
async def lifespan(_):
    initialize_database()
    with Session(engine) as db:
        db.execute(
            update(AgentMessage)
            .where(AgentMessage.status.in_(("thinking", "stopping")))
            .values(status="interrupted", content="服务重启时这次回复被中断，请重新发送。")
        )
        db.commit()
    yield
    engine.dispose()


app = FastAPI(title="Dianoia API", lifespan=lifespan)


@app.middleware("http")
async def check_browser_request(request, call_next):
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("x-dianoia-client") != "web":
            return JSONResponse({"detail": "请求来源无效"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


for feature in (auth, admin, resources, lessons, lesson_templates, ai, mind_maps, exams, presentations, digital_courses, agent):
    app.include_router(feature.router)

app.include_router(question_bank_router)
app.include_router(learning_analytics_router)
