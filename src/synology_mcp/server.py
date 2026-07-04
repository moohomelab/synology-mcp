"""Read-only Synology DSM MCP server.

Every tool is a read: this file contains no DSM write calls by design.
NAS mutations belong to AAP playbooks (Bill's gated write path).
"""

import json
import logging
import os
from collections.abc import Callable

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .dsm_client import DSMClient, DSMError

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("synology-mcp", host="0.0.0.0", port=8000)

_client: DSMClient | None = None


def get_client() -> DSMClient:
    global _client
    if _client is None:
        _client = DSMClient.from_env()
    return _client


async def _tool_call(
    api: str,
    method: str,
    shape: Callable[[dict], dict] | None = None,
    **params,
) -> str:
    """Shared tool body: one DSM call, optional shaping, uniform error strings."""
    try:
        data = await get_client().request(api, method, **params)
        return json.dumps(shape(data) if shape else data, indent=2)
    except DSMError as err:
        return f"Error: {err}"
    except Exception as err:  # httpx transport errors, timeouts, etc.
        logger.exception("Call to %s failed", api)
        return f"Error: NAS unreachable or unexpected failure: {err}"


@mcp.tool()
async def get_system_health() -> str:
    """NAS model, DSM version, uptime, temperature, and fan/power status."""
    return await _tool_call("SYNO.Core.System", "info")


@mcp.tool()
async def get_resource_usage() -> str:
    """Live CPU, memory, network, and disk utilization on the NAS."""

    def shape(data: dict) -> dict:
        return {key: data.get(key) for key in ("cpu", "memory", "network", "disk")}

    return await _tool_call("SYNO.Core.System.Utilization", "get", shape=shape)


def main():
    """Main entry point for the MCP server."""
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
