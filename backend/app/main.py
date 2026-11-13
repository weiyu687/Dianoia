from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import admin, agent, ai, auth, exams, lesson_templates, lessons, mind_maps, resources
from .db import Base, engine


@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)
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


for feature in (auth, admin, resources, lessons, lesson_templates, ai, mind_maps, exams, agent):
    app.include_router(feature.router)
