"""Hermes FastAPI v2 app entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hermes.api.dependencies import shutdown_resources, startup_resources
from hermes.api.routers.agents import router as agents_router
from hermes.api.routers.leaderboard import router as leaderboard_router
from hermes.api.routers.swarm import router as swarm_router

_BASE = Path(__file__).resolve().parents[1]
load_dotenv(_BASE / ".env")


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
    allow_origins=["https://app.letagentscook.lol"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router, prefix="/api/v2")
app.include_router(leaderboard_router, prefix="/api/v2")
app.include_router(swarm_router, prefix="/api/v2")
