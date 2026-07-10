# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Read-only MCP server for the Synology RS1221+ ("Illmatic"): 8 tools (system health,
resource usage, storage/RAID, disk SMART, shares, snapshots, iSCSI LUNs, packages)
over FastMCP Streamable HTTP. Registered user-scope as `mcp__synology__*`.

## INVARIANT: read-only — never add write tools

NAS mutations go through AAP playbooks (Bill's gated write path), **never** this
server. Read-only is enforced in code, not by DSM: the `READ_METHODS` allowlist +
reserved-param guard in `DSMClient.request()` plus a test pinning the 8-tool surface.
The DSM service account (`mcp`) is **admin-privileged** — DSM's iSCSI/disk APIs
require admin, so the code-level guard is the only guard. Adding a write tool is a
spec change, not a patch.

## Commands

- **Tests** — `uv run pytest -q` (CI runs this before any image push).
- **Run locally** — `cp .env.example .env` (fill creds), then
  `uv run python -m synology_mcp` (stdio by default; cluster sets
  `MCP_TRANSPORT=streamable-http`, port 8000).

## Repo split & deploy

Code + Containerfile live here; runtime manifests live in
`~/moolab/homelab/openshift-cluster/apps/ai-platform/mcp-synology/` (ArgoCD app
`app-mcp-synology`). Push to `main` → GitHub Actions builds
`ghcr.io/moohomelab/synology-mcp:latest` (tests gate the push); the Deployment pulls
`:latest` with `imagePullPolicy: Always`, so a redeploy = pod restart. DSM creds come
from Vault `mcp/synology` via ESO. Netpol egress = NAS `10.1.3.2:5001` + DNS only.

## Gotchas

- DSM 7 endpoint discovery goes through `SYNO.API.Info` (auth lives at `entry.cgi`,
  not `auth.cgi`) — never hardcode DSM paths. Auth API capped at v6; the client
  auto re-logins on DSM codes 106/107/119.
- Non-Btrfs shares reject the snapshot API — `list_snapshots` reports that instead
  of failing.
