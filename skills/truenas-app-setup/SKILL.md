---
name: truenas-app-setup
description: Install a new app on the user's TrueNAS Scale server (`bear`, 192.168.7.17) via the `truenas` MCP, following the user's host-path storage convention. Use when the user wants to install/deploy a TrueNAS catalog app (e.g. "install <app> on truenas", "set up <app> on the NAS").
---

# TrueNAS app setup (via the `truenas` MCP)

Installs a catalog app on the TrueNAS Scale host **`bear` (192.168.7.17, TrueNAS 25.10)** using the
`truenas` MCP server's app + filesystem tools, applying the user's standing conventions.

## User conventions (always apply)
- **Host-path storage, never ix-volume.** One folder per app under **`/mnt/dlsapps/apps/<app-name>`**
  (the `dlsapps/apps` dataset), with a subdir per storage entry (e.g. `config`, `data`, `postgres`).
- **Owner / run-as = `kanatera` = uid `3000` / gid `3000`.** chown the app folder tree to `3000:3000`
  and set the app's `run_as` to `{user:3000, group:3000}` when the schema exposes it.
  ⚠️ Some images run as **root** regardless, so their on-disk files end up root-owned. Set `run_as`
  anyway; just don't promise non-root for images known to require root (Home Assistant; Scrutiny,
  whose schema has no `run_as` at all because it reads raw disks).
- **Bridged networking** (published port), not host network — avoids the 5353/avahi conflict on this box.
- **Never use port 8080** — the user is reserving it. Prefer the app's native port if free, else the
  catalog's default `port_number`.
- **Publish only the web UI.** Internal ports (databases, InfluxDB, …) get `bind_mode: "exposed"`.
- **Add the app to Homepage** (see below) once it's running.

## MCP tools (server: `truenas`, `~/dev/truenas-mcp`)
`list_available_apps(search)`, `get_app_schema(app_name, train)`, `install_app(app_name, catalog_app, values, train)`,
`make_dir(path, mode)`, `chown_path(path, uid, gid, recursive)`, `list_dir(path)`, `read_file(path)`,
`write_file(path, content, mode)`, plus `list_apps`, `get_app(app_name)`, `list_jobs(state)`, `start_app`/`stop_app`.

The MCP speaks JSON-RPC over `wss://192.168.7.17/api/current` (REST `/api/v2.0` is removed in TrueNAS 26 —
don't use it). For methods without a tool (`app.used_ports`, `app.config`, `app.update`, `cronjob.*`)
and for polling jobs, drive the same code from Python — one shared login, so no rate limiting:

```bash
cd ~/dev/truenas-mcp && .venv/bin/python - <<'EOF'
import main
print(main.call("app.used_ports"))                      # any JSON-RPC method
with main.session() as c: main._wait_job(c, job_id)     # block until a job finishes
EOF
```

> After editing `~/dev/truenas-mcp/main.py`, the user must `/mcp` → reconnect `truenas` before the
> tools pick up the new code. The Python route above always uses the current file.

## Procedure
1. **Find the catalog app:** `list_available_apps(search="<name>")` → note `name` (catalog id) and `train`
   (often `community`, not `stable` — `get_app_schema` 404s with the wrong train).
2. **Read the schema:** `get_app_schema(app_name="<id>", train="<train>")`. Identify: required fields,
   the storage entries (each has `type` enum `host_path`/`ix_volume` and a `host_path_config.path`),
   the port fields (`network.*.port_number` + `bind_mode`), `run_as`, `TZ`, and any required secrets
   (e.g. a `db_password` with empty default → generate one with `openssl rand -hex 20`).
   Only set `TZ` (`Asia/Bangkok`) if the schema has a field for it — some apps (Scrutiny) set `TZ`
   themselves, and adding it via `additional_envs` fails the render ("already defined").
3. **Pick a free port** (see conventions). Check `main.call("app.used_ports")`.
4. **Provision storage** (the host_path must exist before install):
   - `make_dir("/mnt/dlsapps/apps/<name>")` then one `make_dir(...)` per storage subdir.
   - `chown_path("/mnt/dlsapps/apps/<name>", 3000, 3000, recursive=True)` → job id; wait for it.
5. **Build `values`** from the schema: `run_as={user:3000,group:3000}` if present, the web port
   (`bind_mode:"published"`, `port_number:<port>`, `host_ips:[]`), other ports `bind_mode:"exposed"`,
   every storage entry to
   `{"type":"host_path","host_path_config":{"acl_enable":false,"path":"/mnt/dlsapps/apps/<name>/<subdir>"}}`
   (add `"auto_permissions":true` for DB data dirs like postgres), and any generated secrets.
6. **Install:** `install_app(app_name="<name>", catalog_app="<id>", values=<dict>, train="<train>")`
   → returns a **job id**. A failed render leaves no app behind; read the job's `error` tail for the cause.
7. **Wait + verify:** wait for the job, then `get_app("<name>")` until `state: RUNNING`, and
   `curl http://192.168.7.17:<port>` should answer. **Re-read `main.call("app.config", "<name>")["network"]`
   and confirm every port's `bind_mode`** — Scrutiny's InfluxDB port came out `published` (open on the LAN)
   despite being set to `exposed`. Probe internal ports from outside too; they must not answer.
8. **Homepage:** add the app to `/mnt/dlsapps/apps/homepage/services.yaml` (see below).
9. **Report** the URL `http://192.168.7.17:<port>` and any generated secret (it's stored in the app config).

Changing settings later: `app.update` **replaces each top-level section you send** (`network`, `storage`,
the app's own section…) — it does not merge inside it. Read `main.call("app.config", "<name>")`, copy the
whole section, change one key, and send that section back:
`main.call("app.update", "<name>", {"values": {"<section>": section}})` → job id. Sending a single key
either fails (`Field required` for e.g. bitcoind's `rpc_password`) or silently resets its siblings to
defaults (Scrutiny's InfluxDB port flipped back to `published`). Diff `app.config` before vs after.

## Homepage (dashboard on http://192.168.7.17:9999)
Config: `/mnt/dlsapps/apps/homepage/services.yaml` (owner `1000:1000`, mode `0664`; Homepage reloads it
automatically). Groups: *Media & Entertainment*, *Downloads & Media Management*, *Monitoring & Management*,
*Network & Infrastructure*. Entry style:

```yaml
    - <Name>:
        icon: <app>.png
        href: http://192.168.7.17:<port>
        description: <short description>
        widget:                      # only if Homepage has a widget for the app
          type: <app>
          url: http://192.168.7.17:<port>
```

Read it with `read_file`, edit locally, validate the YAML, write a backup (`services.yaml.pre-<app>`, then
`chown_path` it to `1000:1000`), then `write_file` the new version (overwrite keeps owner and mode) and
read it back. Verify via `curl http://192.168.7.17:9999/api/services` and the widget proxy
`/api/services/proxy?group=<group>&service=<Name>&index=0&endpoint=<key>`, where `<key>` is the
widget's **mapping name** from Homepage's `src/widgets/<type>/widget.js` (e.g. `status`, `alerts` for
TrueNAS) — an API path there gives "Unsupported service endpoint". The TrueNAS widget uses `version: 2`
(websocket) with an `https://` url and the read-only `homepage` user's API key.
The file contains other apps' keys and passwords — never print it unredacted.

## Notes / gotchas
- Long-running calls (`install_app`, `chown_path`, `app.update`, `app.start`/`stop`) return a **job id** —
  always wait for it before declaring success.
- `get_app`, `list_users`, `list_datasets`, `list_snapshots` return very large payloads — filter in Python.
- `make_dir` only works under `/mnt`. There is no delete-file API: to remove a path, create a **disabled**
  root `cronjob.create` with `rm -rf <exact path>`, `cronjob.run(id, False)`, wait, then `cronjob.delete`.
- API auth: `TRUENAS_API_KEY` (+ `TRUENAS_USER`) are injected at launch from Bitwarden Secrets Manager —
  start the session with `claude-secure`. `TRUENAS_HOST` must be **`https://192.168.7.17`**: TrueNAS revokes
  an API key the first time it is sent over plain HTTP, and the MCP refuses `http://`.

## Reference: Home Assistant (installed 2026-06-07, automation working 2026-06-12)
First app set up with this flow. Instance `home-assistant`, stable train, chart 1.8.35 (HA 2026.6.0,
bundles PostgreSQL). Port **8123**, host paths under `/mnt/dlsapps/apps/home-assistant`
(`config`, `postgres` with auto_permissions, `media`). UI: http://192.168.7.17:8123.

**HA container gotcha — no `default_config:`:** the TrueNAS HA app starts with an empty
`configuration.yaml`. None of the standard includes (`automation`, `script`, `scene`) are wired up.
The UI writes automations to `automations.yaml` but nothing loads that file until you add
`automation: !include automations.yaml`. Symptom: "New automation setup timed out" with **zero
log errors**. Fix: add the three includes, fix `scenes.yaml` from `{}` to `[]`, then do a **full
HA restart** (stop + start the TrueNAS app — a config reload is not enough for new includes).
Full setup reference: `/mnt/c/temp/ha-washer-speaker-setup.md`.

## Reference: Scrutiny (installed 2026-10-04)
SMART dashboard. Instance `scrutiny`, **community** train, chart 1.3.14 (v0.9.5-omnibus: web + collector +
InfluxDB in one container). Web port **31054** (moved off 8080), InfluxDB port 31055 **exposed** only.
Host paths `/mnt/dlsapps/apps/scrutiny/{config,influxdb}`. Runs as root (no `run_as`); `TZ` comes from
the app. Homepage widget `type: scrutiny`. UI: http://192.168.7.17:31054.
