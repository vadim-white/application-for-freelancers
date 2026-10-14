from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from .proxy import stream_proxy
from .deps import require_jwt
from .health import router as health_router
from .core.config import settings

app = FastAPI(title="API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# health check
app.include_router(health_router)

# catch-all proxy route: all paths under /api/*
# For protected endpoints we call require_jwt which will validate token if needed.
@app.api_route("/api/{full_path:path}", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"])
async def proxy(full_path: str, request: Request):
    # проверяем токен только для защищённых эндпоинтов
    from .middleware import jwt_middleware
    await jwt_middleware(request)
    return await stream_proxy(request)

@app.get("/")
async def root():
    return {"service": "gateway", "status": "ok"}
