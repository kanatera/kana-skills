---
name: truenas-app-setup
description: Install a new app on the user's TrueNAS Scale server (`bear`, 192.168.7.17) via the `truenas` MCP, following the user's host-path storage convention. Use when the user wants to install/deploy a TrueNAS catalog app (e.g. "install <app> on truenas", "set up <app> on the NAS").
---

# TrueNAS app setup (via the `truenas` MCP)

Installs a catalog app on the TrueNAS Scale host **`bear` (192.168.7.17)** using the `truenas` MCP
server's app + filesystem tools, applying the user's standing conventions.

## User conventions (always apply)
- **Host-path storage, never ix-volume.** One folder per app under **`/mnt/dlsapps/apps/<app-name>`**
  (the `dlsapps/apps` dataset), with a subdir per storage entry (e.g. `config`, `data`, `postgres`).
- **Owner / run-as = `kanatera` = uid `3000` / gid `3000`.** chown the app folder tree to `3000:3000`
  and set the app's `run_as` to `{user:3000, group:3000}` when the schema exposes it.
  ⚠️ Some official images (e.g. Home Assistant) run their container as **root** regardless of
  `run_as`, so their on-disk files end up root-owned. Set `run_as` anyway; just don't promise
  non-root for images known to require root.
- **Bridged networking** (published port), not host network — avoids the 5353/avahi conflict on this box.

## MCP tools available (server: `truenas`)
`list_available_apps(search)`, `get_app_schema(app_name, train)`, `install_app(app_name, catalog_app, values, train)`,
`make_dir(path, mode)`, `chown_path(path, uid, gid, recursive)`, `list_dir(path)`,
plus `list_apps`, `get_app(app_name)`, `list_jobs(state)`, `start_app`/`stop_app`.

> If you edit `~/dev/truenas-mcp/main.py` to add tools, the user must `/mcp` → reconnect `truenas`
> before the new tools load (the server only reads new code on restart).

## Procedure
1. **Find the catalog app:** `list_available_apps(search="<name>")` → note `name` (catalog id) and `train`
   (usually `stable` or `community`).
2. **Read the schema:** `get_app_schema(app_name="<id>", train="<train>")`. Identify: required fields,
   the storage entries (each has `type` enum `host_path`/`ix_volume` and a `host_path_config.path`),
   the web port field (`network.*.web_port.port_number` + `bind_mode: published`), `run_as`, `TZ`
   (default `Asia/Bangkok`), and any required secrets (e.g. a `db_password` with empty default →
   generate one with `openssl rand -hex 20`).
3. **Pick a free port.** Default to a memorable one (e.g. the app's native port). Confirm it's unused
   with a read-only `GET /api/v2.0/app/used_ports`; the install will error on a conflict otherwise.
4. **Provision storage** (the host_path must exist before install):
   - `make_dir("/mnt/dlsapps/apps/<name>")` then one `make_dir(...)` per storage subdir.
   - `chown_path("/mnt/dlsapps/apps/<name>", 3000, 3000, recursive=True)`.
5. **Build `values`** from the schema: set `TZ`, `run_as={user:3000,group:3000}`, the web port
   (`bind_mode:"published"`, `port_number:<port>`, `host_ips:[]`), every storage entry to
   `{"type":"host_path","host_path_config":{"acl_enable":false,"path":"/mnt/dlsapps/apps/<name>/<subdir>"}}`
   (add `"auto_permissions":true` for DB data dirs like postgres), and any generated secrets.
6. **Install:** `install_app(app_name="<name>", catalog_app="<id>", values=<dict>, train="<train>")`
   → returns a **job id**.
7. **Wait + verify:** poll the job (background `until` loop on
   `GET /api/v2.0/core/get_jobs?id=<jobid>` until state ∈ SUCCESS/FAILED/ABORTED), then
   `get_app("<name>")` should be `state: RUNNING`, and `curl http://192.168.7.17:<port>` should answer.
8. **Report** the URL `http://192.168.7.17:<port>` and any generated secret (it's stored in the app config).

## Notes / gotchas
- `install_app`, `chown_path`, and other long-running calls return a **job id**, not the final result —
  always poll before declaring success.
- `get_app`, `list_users`, `list_datasets` can return very large payloads (saved to a file) — prefer
  targeted reads / `list_dir` / direct API GETs with `jq`/python filtering.
- The MCP `get_dataset` 404s on dataset ids containing `/` (it doesn't URL-encode the slash) — use the
  raw API or `list_datasets` instead.
- API auth: the bearer key is **not** in any file — it's `TRUENAS_API_KEY`, injected at launch from
  Bitwarden Secrets Manager (start the session with `claude-secure`, i.e. `bws run -- claude`). Only the
  host (`TRUENAS_HOST`) lives in the `truenas` MCP env block of `~/.claude.json` (host is `http` on
  port 80; https/443 is closed). If the MCP can't authenticate, you launched plain `claude` without the token.

## Reference: Home Assistant (installed 2026-06-07)
First app set up with this flow. Instance `home-assistant`, stable train, chart 1.8.35 (HA 2026.6.0,
bundles PostgreSQL). Port **8123**, host paths under `/mnt/dlsapps/apps/home-assistant`
(`config`, `postgres` with auto_permissions, `media`). UI: http://192.168.7.17:8123.
