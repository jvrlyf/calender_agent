from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.mcp_client.client import MCPCalendarClient
from backend.agent.graph import build_agent_graph
from backend.api.routes import router as api_router, inject_dependencies
from backend.utils.logger import get_logger

log = get_logger("main")

mcp_client = MCPCalendarClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # ── startup ──
    log.info("🚀 Starting %s", settings.APP_NAME)

    try:
        await mcp_client.connect()
        log.info("MCP client connected")
    except Exception as exc:
        log.error("MCP client connection failed: %s (continuing without it)", exc)

    agent_graph = build_agent_graph(mcp_client)
    inject_dependencies(agent_graph, mcp_client)
    log.info("Agent graph ready")

    yield

    # ── shutdown ──
    log.info("Shutting down…")
    await mcp_client.disconnect()
    log.info("Goodbye 👋")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)

# Serve frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")