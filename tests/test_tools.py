"""Tool tests - fake the DSM client, verify shaping and error paths."""

import json

import httpx

import synology_mcp.server as server


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def request(self, api, method, **params):
        self.calls.append((api, method, params))
        result = self.responses[(api, method)]
        if isinstance(result, Exception):
            raise result
        return result


async def test_get_system_health(monkeypatch):
    fake = FakeClient({("SYNO.Core.System", "info"): {"model": "RS1221+", "up_time": "12:34:56"}})
    monkeypatch.setattr(server, "_client", fake)
    out = await server.get_system_health()
    assert json.loads(out)["model"] == "RS1221+"


async def test_get_resource_usage_shapes_output(monkeypatch):
    fake = FakeClient({
        ("SYNO.Core.System.Utilization", "get"): {
            "cpu": {"user_load": 5},
            "memory": {"real_usage": 40},
            "network": [{"device": "total", "rx": 1}],
            "disk": {"total": {"utilization": 2}},
            "space": {"ignored": True},
        }
    })
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.get_resource_usage())
    assert set(out.keys()) == {"cpu", "memory", "network", "disk"}


async def test_tool_reports_dsm_error(monkeypatch):
    from synology_mcp.dsm_client import DSMError

    fake = FakeClient({("SYNO.Core.System", "info"): DSMError(105, "SYNO.Core.System")})
    monkeypatch.setattr(server, "_client", fake)
    out = await server.get_system_health()
    assert out.startswith("Error:") and "105" in out


async def test_tool_reports_nas_unreachable(monkeypatch):
    fake = FakeClient({("SYNO.Core.System", "info"): httpx.ConnectError("no route to host")})
    monkeypatch.setattr(server, "_client", fake)
    out = await server.get_system_health()
    assert out.startswith("Error: NAS unreachable")
