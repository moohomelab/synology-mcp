"""Async client for the Synology DSM Web API.

Owns the DSM session lifecycle: SYNO.API.Info discovery (so endpoint paths
and versions come from the NAS, not hardcoded), sid login, GET requests,
and one automatic re-login when the session expires.
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# DSM error codes that mean "session is gone - log in again and retry once".
# 106 = session timeout, 107 = session interrupted (duplicate login), 119 = invalid sid.
SESSION_EXPIRED_CODES = {106, 107, 119}


class DSMError(Exception):
    """A DSM API call returned success=false (code -1 = API not on this NAS)."""

    def __init__(self, code: int, api: str):
        self.code = code
        self.api = api
        super().__init__(f"DSM API error {code} calling {api}")


class DSMClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 5001,
        verify_ssl: bool = False,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._username = username
        self._password = password
        self._sid: str | None = None
        self._api_info: dict | None = None
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            base_url=f"https://{host}:{port}/webapi",
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> "DSMClient":
        return cls(
            host=os.environ["SYNOLOGY_HOST"],
            port=int(os.getenv("SYNOLOGY_PORT", "5001")),
            username=os.environ["SYNOLOGY_USERNAME"],
            password=os.environ["SYNOLOGY_PASSWORD"],
            verify_ssl=os.getenv("SYNOLOGY_VERIFY_SSL", "false").lower() == "true",
            timeout=float(os.getenv("SYNOLOGY_TIMEOUT", "10.0")),
        )

    async def _call(self, path: str, params: dict) -> dict:
        """One raw GET to /webapi/<path>; unwraps the DSM success/error envelope."""
        response = await self._http.get(f"/{path}", params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            code = payload.get("error", {}).get("code", -1)
            raise DSMError(code, params.get("api", path))
        return payload.get("data", {})

    async def _discover(self) -> dict:
        """Fetch (once) the API catalog: name -> {path, minVersion, maxVersion}."""
        if self._api_info is None:
            self._api_info = await self._call(
                "query.cgi",
                {"api": "SYNO.API.Info", "version": "1", "method": "query", "query": "all"},
            )
        return self._api_info

    async def _login(self) -> None:
        info = await self._discover()
        auth = info["SYNO.API.Auth"]
        data = await self._call(
            auth["path"],
            {
                "api": "SYNO.API.Auth",
                # Cap at v6: v7 changes the login contract; v6 is stable on DSM 7
                "version": str(min(auth["maxVersion"], 6)),
                "method": "login",
                "account": self._username,
                "passwd": self._password,
                "format": "sid",
            },
        )
        self._sid = data["sid"]
        logger.info("Logged in to DSM as %s", self._username)
