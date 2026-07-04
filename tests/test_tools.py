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


STORAGE_DATA = {
    "volumes": [{"id": "volume_1", "status": "normal", "size": {"total": "10", "used": "5"}}],
    "storagePools": [{"id": "reuse_1", "status": "normal", "raidType": "raid_5"}],
    "disks": [
        {
            "id": "sata1", "model": "WD80EFAX", "serial": "X", "temp": 38,
            "smart_status": "normal", "status": "normal", "size_total": "8001563222016",
            "firm": "ignored-field",
        }
    ],
}


async def test_get_storage_status(monkeypatch):
    fake = FakeClient({("SYNO.Storage.CGI.Storage", "load_info"): STORAGE_DATA})
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.get_storage_status())
    assert out["volumes"][0]["status"] == "normal"
    assert out["storage_pools"][0]["raidType"] == "raid_5"
    assert "disks" not in out


async def test_get_disk_health_trims_fields(monkeypatch):
    fake = FakeClient({("SYNO.Storage.CGI.Storage", "load_info"): STORAGE_DATA})
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.get_disk_health())
    disk = out["disks"][0]
    assert disk["smart_status"] == "normal"
    assert "firm" not in disk


async def test_list_shares(monkeypatch):
    fake = FakeClient({
        ("SYNO.Core.Share", "list"): {
            "shares": [{"name": "media", "vol_path": "/volume1"}],
            "total": 1,
        }
    })
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.list_shares())
    assert out["shares"][0]["name"] == "media"
    # size info must be requested from DSM
    assert fake.calls[0][2].get("additional") == '["size_info"]'


async def test_list_snapshots_iterates_all_shares(monkeypatch):
    from synology_mcp.dsm_client import DSMError

    fake = FakeClient({
        ("SYNO.Core.Share", "list"): {"shares": [{"name": "media"}, {"name": "docker"}]},
        ("SYNO.Core.Share.Snapshot", "list"): {"snapshots": [{"time": "GMT-2026.07.01"}]},
    })
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.list_snapshots())
    assert set(out.keys()) == {"media", "docker"}


async def test_list_snapshots_single_share(monkeypatch):
    fake = FakeClient({
        ("SYNO.Core.Share.Snapshot", "list"): {"snapshots": []},
    })
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.list_snapshots(share_name="media"))
    assert out == {"media": []}
    # must NOT have called SYNO.Core.Share list
    assert all(call[0] != "SYNO.Core.Share" for call in fake.calls)


async def test_list_snapshots_records_per_share_error(monkeypatch):
    from synology_mcp.dsm_client import DSMError

    class PartialFailClient:
        async def request(self, api, method, **params):
            if api == "SYNO.Core.Share":
                return {"shares": [{"name": "media"}, {"name": "docker"}]}
            if params.get("name") == "docker":
                raise DSMError(3300, "SYNO.Core.Share.Snapshot")
            return {"snapshots": [{"time": "GMT-2026.07.01"}]}

    monkeypatch.setattr(server, "_client", PartialFailClient())
    out = json.loads(await server.list_snapshots())
    assert out["media"] == [{"time": "GMT-2026.07.01"}]
    assert out["docker"] == "unavailable (DSM error 3300)"


async def test_get_iscsi_status_combines_luns_and_targets(monkeypatch):
    fake = FakeClient({
        ("SYNO.Core.ISCSI.LUN", "list"): {"luns": [{"name": "k8s-pvc", "status": "normal"}]},
        ("SYNO.Core.ISCSI.Target", "list"): {"targets": [{"name": "target-1", "status": "online"}]},
    })
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.get_iscsi_status())
    assert out["luns"][0]["name"] == "k8s-pvc"
    assert out["targets"][0]["status"] == "online"


async def test_list_packages(monkeypatch):
    fake = FakeClient({
        ("SYNO.Core.Package", "list"): {
            "packages": [{"id": "SynologyDrive", "version": "3.5", "additional": {"status": "stop"}}]
        }
    })
    monkeypatch.setattr(server, "_client", fake)
    out = json.loads(await server.list_packages())
    assert out["packages"][0]["id"] == "SynologyDrive"
    assert fake.calls[0][2].get("additional") == '["status"]'
