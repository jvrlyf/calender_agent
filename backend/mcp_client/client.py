from __future__ import annotations

import json
import sys
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.config import settings
from backend.utils.logger import get_logger

log = get_logger("mcp.client")


class MCPCalendarClient:


    def __init__(self):
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self._connected: bool = False

    # ── lifecycle ─────────────────────────────────────
    async def connect(self) -> None:
        if self._connected:
            log.warning("MCP client already connected")
            return

        try:
            self._stack = AsyncExitStack()
            await self._stack.__aenter__()

            # Find python executable — use same python that's running this app
            python_exe = sys.executable

            server_script = settings.MCP_SERVER_SCRIPT

            # Verify server script exists
            if not os.path.exists(server_script):
                log.error("MCP server script not found: %s", server_script)
                raise FileNotFoundError(f"MCP server script not found: {server_script}")

            server_params = StdioServerParameters(
                command=python_exe,
                args=[server_script],
                env={
                    **os.environ,
                    "PYTHONPATH": str(settings.BASE_DIR),
                },
            )

            log.info("Connecting to MCP server: %s %s", python_exe, server_script)

            read_stream, write_stream = await self._stack.enter_async_context(
                stdio_client(server_params)
            )
            self._session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()

            tools = await self._session.list_tools()
            tool_names = [t.name for t in tools.tools]
            log.info("MCP connected — available tools: %s", tool_names)
            self._connected = True

        except Exception as exc:
            log.exception("MCP connection failed")
            self._connected = False
            # clean up partial connection
            if self._stack:
                try:
                    await self._stack.__aexit__(None, None, None)
                except Exception:
                    pass
            self._stack = None
            self._session = None
            raise

    async def disconnect(self) -> None:
        if self._stack:
            try:
                await self._stack.__aexit__(None, None, None)
            except Exception as exc:
                log.warning("Error during MCP disconnect: %s", exc)
            self._session = None
            self._stack = None
            self._connected = False
            log.info("MCP client disconnected")

    async def _reconnect(self) -> None:
        log.warning("Attempting MCP reconnection...")
        await self.disconnect()
        await self.connect()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if not self._connected or self._session is None:
            try:
                await self.connect()
            except Exception as exc:
                return {"error": f"MCP not available: {exc}"}

        log.info("Calling MCP tool '%s' with args %s", tool_name, arguments)

        # Try call, reconnect once on failure
        for attempt in range(2):
            try:
                result = await self._session.call_tool(tool_name, arguments=arguments)
                text = result.content[0].text if result.content else "{}"
                parsed = json.loads(text)
                log.info("MCP tool '%s' returned: %s", tool_name, parsed)
                return parsed

            except Exception as exc:
                log.warning("MCP call attempt %d failed: %s", attempt + 1, exc)
                if attempt == 0:
                    # first failure → try reconnect
                    try:
                        await self._reconnect()
                    except Exception as reconn_exc:
                        log.error("Reconnection failed: %s", reconn_exc)
                        return {"error": f"MCP connection lost: {reconn_exc}"}
                else:
                    # second failure → give up
                    log.exception("MCP call_tool '%s' failed after retry", tool_name)
                    return {"error": str(exc)}

        return {"error": "MCP call failed"}

    async def list_tools(self) -> list[str]:
        """Return names of all available MCP tools."""
        if self._session is None:
            return []
        try:
            tools = await self._session.list_tools()
            return [t.name for t in tools.tools]
        except Exception:
            return []

    @property
    def is_connected(self) -> bool:
        return self._connected