# truenas-mcp

MCP server for TrueNAS SCALE 25.04+. Talks JSON-RPC 2.0 over `wss://<host>/api/current`
through the official [`truenas_api_client`](https://github.com/truenas/api_client), pinned to
the branch matching the NAS (`release/25.10.7`; bump it with the NAS version).
The REST API (`/api/v2.0`) is not used: it is deprecated and removed in TrueNAS 26.

## Configuration

| Env | Default | |
|---|---|---|
| `TRUENAS_HOST` | — | Must be `https://…`. The server refuses `http://`, because TrueNAS revokes an API key the first time it is sent over plain HTTP. |
| `TRUENAS_USER` | `admin` | User that owns the API key. |
| `TRUENAS_API_KEY` | — | |

One authenticated websocket is shared by all tools and re-established if the server drops it.
TrueNAS rate-limits logins, so connecting per call stops working after ~20 calls.

## Notes

- Job methods (`app.start`, `app.create`, `cloudsync.sync`, `vm.stop`, `filesystem.chown`,
  `system.reboot`, …) return the job id; follow up with `list_jobs`.
- `read_file` / `write_file` use `core.download` and `/_upload`. A failed download still answers
  HTTP 200 with an empty body, so `read_file` checks the job state. `write_file` keeps the
  owner and mode on overwrite, and returns them read back via `filesystem.stat`.
- `filesystem.mkdir` only accepts paths under `/mnt`.
- 25.10 has no SMART methods in the API, so there is no SMART-results tool.
