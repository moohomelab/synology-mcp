"""DSMClient tests using httpx.MockTransport - no network, no mocking library."""

import httpx
import pytest

from synology_mcp.dsm_client import DSMClient, DSMError

API_INFO = {
    "success": True,
    "data": {
        "SYNO.API.Auth": {"path": "auth.cgi", "minVersion": 1, "maxVersion": 7},
        "SYNO.Core.System": {"path": "entry.cgi", "minVersion": 1, "maxVersion": 3},
    },
}


def make_client(handler):
    return DSMClient(
        host="nas.test",
        username="u",
        password="p",
        transport=httpx.MockTransport(handler),
    )


async def test_login_fetches_api_info_then_sid():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("query.cgi"):
            assert request.url.params["api"] == "SYNO.API.Info"
            return httpx.Response(200, json=API_INFO)
        if request.url.path.endswith("auth.cgi"):
            assert request.url.params["method"] == "login"
            assert request.url.params["account"] == "u"
            assert request.url.params["format"] == "sid"
            # Auth version is capped at 6 even though the NAS advertises 7
            assert request.url.params["version"] == "6"
            return httpx.Response(200, json={"success": True, "data": {"sid": "SID123"}})
        raise AssertionError(f"unexpected call: {request.url}")

    client = make_client(handler)
    await client._login()
    assert client._sid == "SID123"
    assert seen == ["/webapi/query.cgi", "/webapi/auth.cgi"]


async def test_login_failure_raises_dsm_error():
    def handler(request):
        if request.url.path.endswith("query.cgi"):
            return httpx.Response(200, json=API_INFO)
        return httpx.Response(200, json={"success": False, "error": {"code": 400}})

    client = make_client(handler)
    with pytest.raises(DSMError) as exc:
        await client._login()
    assert exc.value.code == 400


async def test_request_logs_in_lazily_and_adds_sid():
    def handler(request):
        path = request.url.path
        if path.endswith("query.cgi"):
            return httpx.Response(200, json=API_INFO)
        if path.endswith("auth.cgi"):
            return httpx.Response(200, json={"success": True, "data": {"sid": "SID123"}})
        assert path == "/webapi/entry.cgi"
        assert request.url.params["_sid"] == "SID123"
        assert request.url.params["api"] == "SYNO.Core.System"
        assert request.url.params["version"] == "3"  # maxVersion from discovery
        assert request.url.params["method"] == "info"
        return httpx.Response(200, json={"success": True, "data": {"model": "RS1221+"}})

    client = make_client(handler)
    data = await client.request("SYNO.Core.System", "info")
    assert data["model"] == "RS1221+"


async def test_session_expiry_triggers_one_relogin_and_retry():
    sids = iter(["SID1", "SID2"])

    def handler(request):
        path = request.url.path
        if path.endswith("query.cgi"):
            return httpx.Response(200, json=API_INFO)
        if path.endswith("auth.cgi"):
            return httpx.Response(200, json={"success": True, "data": {"sid": next(sids)}})
        if request.url.params["_sid"] == "SID1":
            return httpx.Response(200, json={"success": False, "error": {"code": 119}})
        return httpx.Response(200, json={"success": True, "data": {"ok": True}})

    client = make_client(handler)
    data = await client.request("SYNO.Core.System", "info")
    assert data == {"ok": True}


async def test_non_session_dsm_error_raises():
    def handler(request):
        path = request.url.path
        if path.endswith("query.cgi"):
            return httpx.Response(200, json=API_INFO)
        if path.endswith("auth.cgi"):
            return httpx.Response(200, json={"success": True, "data": {"sid": "S"}})
        # 105 = insufficient privilege - must surface, NOT retry
        return httpx.Response(200, json={"success": False, "error": {"code": 105}})

    client = make_client(handler)
    with pytest.raises(DSMError) as exc:
        await client.request("SYNO.Core.System", "info")
    assert exc.value.code == 105


async def test_unknown_api_raises_code_minus_one():
    def handler(request):
        path = request.url.path
        if path.endswith("query.cgi"):
            return httpx.Response(200, json=API_INFO)
        if path.endswith("auth.cgi"):
            return httpx.Response(200, json={"success": True, "data": {"sid": "S"}})
        raise AssertionError("should not reach the API call")

    client = make_client(handler)
    with pytest.raises(DSMError) as exc:
        await client.request("SYNO.Nope.Missing", "list")
    assert exc.value.code == -1
