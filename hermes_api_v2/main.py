"""Hermes FastAPI v2 entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure FastAPI gets the same env as Flask app (/root/hermes/.env).
_BASE = Path(__file__).resolve().parent.parent
load_dotenv(_BASE / ".env")

from hermes_api_v2.api.v2.agents import router as agents_router
from hermes_api_v2.api.v2.leaderboard import router as leaderboard_router
from hermes_api_v2.api.v2.websocket import router as websocket_router
from hermes_api_v2.core.config import cors_allow_origins
from hermes_api_v2.core.database import shutdown_resources, startup_resources


@asynccontextmanager
async def lifespan(_: FastAPI):
    await startup_resources()
    try:
        yield
    finally:
        await shutdown_resources()


app = FastAPI(title="Hermes API v2", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router, prefix="/api/v2")
app.include_router(leaderboard_router, prefix="/api/v2")
app.include_router(websocket_router, prefix="/api/v2")

