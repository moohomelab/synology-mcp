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
