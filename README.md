# synology-mcp

Read-only MCP server for the Synology RS1221+ ("Illmatic"). Exposes NAS
health, storage/RAID/SMART, shares, snapshots, iSCSI LUN status, and DSM
package status over MCP Streamable HTTP.

**Read-only by construction** — no write code exists. NAS mutations go
through AAP playbooks (Bill's gated write path), never through this server.

## Tools

get_system_health, get_resource_usage, get_storage_status, get_disk_health,
list_shares, list_snapshots, get_iscsi_status, list_packages

## Run locally

    cp .env.example .env   # fill in credentials
    uv run python -m synology_mcp

## Deploy

Image: ghcr.io/moohomelab/synology-mcp (built by GitHub Actions on push to
main). Manifests: moolab repo, homelab/openshift-cluster/apps/ai-platform/mcp-synology/.
Spec: moolab docs/superpowers/specs/2026-07-04-synology-mcp-design.md
