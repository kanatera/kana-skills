#!/usr/bin/env python3
"""TrueNAS SCALE MCP server.

Talks JSON-RPC 2.0 over wss://<host>/api/current (TrueNAS 25.04+) through the official
`truenas_api_client`. The REST API (/api/v2.0) is deprecated and removed in TrueNAS 26.
"""

import errno
import os
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from truenas_api_client import Client, ClientException

TRUENAS_HOST = os.environ.get("TRUENAS_HOST", "https://truenas.local").rstrip("/")
TRUENAS_USER = os.environ.get("TRUENAS_USER", "admin")
TRUENAS_API_KEY = os.environ.get("TRUENAS_API_KEY", "")

if not TRUENAS_HOST.startswith("https://"):
    # TrueNAS 25.04+ revokes an API key the first time it is sent over plain HTTP.
    raise SystemExit(f"TRUENAS_HOST must be https:// — got {TRUENAS_HOST}")

WS_URI = f"wss://{urlsplit(TRUENAS_HOST).netloc}/api/current"

mcp = FastMCP("truenas")


# One authenticated connection shared by all tools: TrueNAS rate-limits logins, so
# connecting per call fails with "[EBUSY] Rate Limit Exceeded" after ~20 calls.
_lock = threading.RLock()
_client: Client | None = None


def _drop() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None


def _connected() -> Client:
    global _client
    if _client is not None and not _client._closed.is_set():
        return _client
    _drop()
    # verify_ssl=False: tools address the NAS by IP, which its certificate doesn't name.
    c = Client(WS_URI, verify_ssl=False)
    try:
        r = c.call("auth.login_ex", {
            "mechanism": "API_KEY_PLAIN", "username": TRUENAS_USER, "api_key": TRUENAS_API_KEY,
        })
        if r.get("response_type") != "SUCCESS":
            raise RuntimeError(f"TrueNAS rejected the API key for user '{TRUENAS_USER}' ({r.get('response_type')})")
    except BaseException:
        c.close()
        raise
    _client = c
    return c


@contextmanager
def session():
    with _lock:
        yield _connected()


def call(method: str, *args):
    """Call a method. For job methods this returns the job id without waiting."""
    with _lock:
        try:
            return _connected().call(method, *args)
        except ClientException as e:
            if e.errno != errno.ECONNABORTED:
                raise
            # The server closed an idle connection; reconnect once.
            _drop()
            return _connected().call(method, *args)


def _wait_job(c: Client, job_id: int, timeout: float = 120) -> object:
    deadline = time.monotonic() + timeout
    while True:
        job = c.call("core.get_jobs", [["id", "=", job_id]])[0]
        if job["state"] == "SUCCESS":
            return job.get("result")
        if job["state"] in ("FAILED", "ABORTED"):
            raise RuntimeError(f"TrueNAS job {job_id} {job['state']}: {job.get('error')}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"TrueNAS job {job_id} still {job['state']} after {timeout}s")
        time.sleep(1)


# ── System ────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_system_info() -> dict:
    """Get TrueNAS system information (hostname, version, uptime, etc.)."""
    return call("system.info")


@mcp.tool()
def get_system_version() -> str:
    """Get the TrueNAS Scale version string."""
    return call("system.version")


@mcp.tool()
def get_system_state() -> str:
    """Get the current system state (READY, BOOTING, etc.)."""
    return call("system.state")


@mcp.tool()
def reboot_system(reason: str = "Requested via MCP") -> int:
    """Reboot the TrueNAS system. Returns the job id."""
    return call("system.reboot", reason)


@mcp.tool()
def shutdown_system(reason: str = "Requested via MCP") -> int:
    """Shut down the TrueNAS system. Returns the job id."""
    return call("system.shutdown", reason)


# ── Alerts ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_alerts() -> list:
    """List all active system alerts."""
    return call("alert.list")


@mcp.tool()
def dismiss_alert(uuid: str) -> None:
    """Dismiss an alert by its UUID."""
    call("alert.dismiss", uuid)


# ── Storage / Pools ───────────────────────────────────────────────────────────

@mcp.tool()
def list_pools() -> list:
    """List all ZFS storage pools with their health and status."""
    return call("pool.query")


@mcp.tool()
def get_pool(pool_id: int) -> dict:
    """Get details for a specific pool by ID."""
    return call("pool.get_instance", pool_id)


@mcp.tool()
def list_datasets(pool_name: str | None = None) -> list:
    """List all ZFS datasets. Optionally filter by pool name."""
    return call("pool.dataset.query", [["pool", "=", pool_name]] if pool_name else [])


@mcp.tool()
def get_dataset(dataset_id: str) -> dict:
    """Get details for a specific dataset by ID (e.g. 'tank/data')."""
    return call("pool.dataset.get_instance", dataset_id)


@mcp.tool()
def create_dataset(name: str, comments: str = "", compression: str = "lz4", atime: str = "off") -> dict:
    """
    Create a new ZFS dataset.
    - name: full dataset path, e.g. 'tank/newdataset'
    - compression: lz4, gzip, zstd, off, inherit (case-insensitive)
    - atime: on, off or inherit
    """
    return call("pool.dataset.create", {
        "name": name, "comments": comments, "compression": compression.upper(), "atime": atime.upper(),
    })


@mcp.tool()
def delete_dataset(dataset_id: str, recursive: bool = False) -> None:
    """Delete a ZFS dataset. Set recursive=True to also remove children."""
    call("pool.dataset.delete", dataset_id, {"recursive": recursive})


@mcp.tool()
def list_snapshots(dataset: str | None = None) -> list:
    """List ZFS snapshots. Optionally filter by dataset name."""
    return call("pool.snapshot.query", [["dataset", "=", dataset]] if dataset else [])


@mcp.tool()
def create_snapshot(dataset: str, name: str, recursive: bool = False) -> dict:
    """
    Create a ZFS snapshot.
    - dataset: dataset path, e.g. 'tank/data'
    - name: snapshot name suffix, e.g. 'manual-2024-01-01'
    """
    return call("pool.snapshot.create", {"dataset": dataset, "name": name, "recursive": recursive})


@mcp.tool()
def delete_snapshot(snapshot_id: str) -> None:
    """Delete a ZFS snapshot by ID (e.g. 'tank/data@snap1')."""
    call("pool.snapshot.delete", snapshot_id)


# ── Disks ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_disks() -> list:
    """List all physical disks with model, size and serial."""
    return call("disk.query")


@mcp.tool()
def get_disk_temperature(disk_name: str) -> dict:
    """Get the current temperature (°C) for a disk (e.g. 'sda'), as {disk_name: temperature}."""
    return call("disk.temperatures", [disk_name])


# ── Network ───────────────────────────────────────────────────────────────────

@mcp.tool()
def list_interfaces() -> list:
    """List all network interfaces with IP addresses and link state."""
    return call("interface.query")


@mcp.tool()
def get_network_config() -> dict:
    """Get network configuration (default gateway, nameservers, hostname)."""
    return call("network.configuration.config")


# ── Shares ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_smb_shares() -> list:
    """List all SMB/Windows shares."""
    return call("sharing.smb.query")


@mcp.tool()
def list_nfs_shares() -> list:
    """List all NFS shares."""
    return call("sharing.nfs.query")


@mcp.tool()
def create_smb_share(path: str, name: str, comment: str = "") -> dict:
    """
    Create a new SMB share.
    - path: absolute path to the dataset, e.g. '/mnt/tank/media'
    - name: share name visible to Windows clients
    """
    return call("sharing.smb.create", {"path": path, "name": name, "comment": comment})


@mcp.tool()
def delete_smb_share(share_id: int) -> None:
    """Delete an SMB share by ID."""
    call("sharing.smb.delete", share_id)


# ── Services ──────────────────────────────────────────────────────────────────

@mcp.tool()
def list_services() -> list:
    """List all services (SMB, NFS, SSH, etc.) with their running state."""
    return call("service.query")


@mcp.tool()
def start_service(service_name: str) -> bool:
    """Start a service by name (e.g. 'cifs', 'nfs', 'ssh', 'ftp', 'snmp')."""
    return call("service.start", service_name, {"silent": False})


@mcp.tool()
def stop_service(service_name: str) -> bool:
    """Stop a service by name."""
    return call("service.stop", service_name, {"silent": False})


@mcp.tool()
def restart_service(service_name: str) -> bool:
    """Restart a service by name."""
    return call("service.restart", service_name, {"silent": False})


# ── Users & Groups ────────────────────────────────────────────────────────────

@mcp.tool()
def list_users() -> list:
    """List all local users."""
    return call("user.query")


@mcp.tool()
def list_groups() -> list:
    """List all local groups."""
    return call("group.query")


# ── Jobs / Tasks ──────────────────────────────────────────────────────────────

@mcp.tool()
def list_jobs(state: str | None = None) -> list:
    """
    List background jobs/tasks.
    - state: filter by state — RUNNING, SUCCESS, FAILED, ABORTED (optional)
    """
    return call("core.get_jobs", [["state", "=", state]] if state else [])


@mcp.tool()
def list_cloud_sync_tasks() -> list:
    """List all cloud sync tasks."""
    return call("cloudsync.query")


@mcp.tool()
def run_cloud_sync_task(task_id: int) -> int:
    """Trigger a cloud sync task to run immediately. Returns the job id."""
    return call("cloudsync.sync", task_id)


@mcp.tool()
def list_replication_tasks() -> list:
    """List all ZFS replication tasks."""
    return call("replication.query")


@mcp.tool()
def list_periodic_snapshot_tasks() -> list:
    """List all automatic snapshot tasks."""
    return call("pool.snapshottask.query")


# ── Apps (TrueNAS Scale) ──────────────────────────────────────────────────────

@mcp.tool()
def list_apps() -> list:
    """List all installed TrueNAS Scale apps."""
    return call("app.query")


@mcp.tool()
def get_app(app_name: str) -> dict:
    """Get details for a specific app by name."""
    return call("app.get_instance", app_name)


@mcp.tool()
def start_app(app_name: str) -> int:
    """Start an app by name. Returns the job id."""
    return call("app.start", app_name)


@mcp.tool()
def stop_app(app_name: str) -> int:
    """Stop an app by name. Returns the job id."""
    return call("app.stop", app_name)


@mcp.tool()
def list_available_apps(search: str | None = None) -> list:
    """List apps installable from the catalog. Optionally filter by a name/title substring.
    Returns name (catalog id), title, train, catalog, and latest versions for each match."""
    apps = call("app.available")
    if search:
        s = search.lower()
        apps = [a for a in apps if s in a.get("name", "").lower() or s in a.get("title", "").lower()]
    return [
        {k: a.get(k) for k in ("name", "title", "train", "catalog", "latest_version", "latest_app_version")}
        for a in apps
    ]


@mcp.tool()
def get_app_schema(app_name: str, train: str = "stable") -> dict:
    """Get a catalog app's configuration value schema (questions) for its latest version.
    Inspect this to learn valid `values` keys/defaults/enums before calling install_app."""
    details = call("catalog.get_app_details", app_name, {"train": train})
    ver = details.get("latest_version")
    schema = details.get("versions", {}).get(ver, {}).get("schema", {})
    return {"app_name": app_name, "train": train, "version": ver, "questions": schema.get("questions", [])}


@mcp.tool()
def install_app(app_name: str, catalog_app: str, values: dict, train: str = "stable") -> int:
    """Install a catalog app and return the deploy job id.
    - app_name: instance name (lowercase alphanumeric + hyphens, e.g. 'home-assistant')
    - catalog_app: catalog item id (often same as app_name)
    - values: config dict matching the app schema (see get_app_schema)
    Poll the returned job id via list_jobs, then confirm with get_app(app_name)."""
    return call("app.create", {
        "custom_app": False,
        "catalog_app": catalog_app,
        "app_name": app_name,
        "train": train,
        "values": values,
    })


# ── Filesystem ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_dir(path: str) -> list:
    """List a directory's contents with name, type, owner uid/gid, and octal mode."""
    entries = call("filesystem.listdir", path)
    return [
        {
            "name": e.get("name"),
            "type": e.get("type"),
            "uid": e.get("uid"),
            "gid": e.get("gid"),
            "mode": oct(e["mode"])[-4:] if isinstance(e.get("mode"), int) else e.get("mode"),
        }
        for e in entries
    ]


@mcp.tool()
def make_dir(path: str, mode: str = "755") -> dict:
    """Create a directory at an absolute path (e.g. '/mnt/dlsapps/apps/myapp'). Parent must exist."""
    return call("filesystem.mkdir", {"path": path, "options": {"mode": mode}})


@mcp.tool()
def chown_path(path: str, uid: int, gid: int, recursive: bool = True) -> int:
    """Change ownership of a path to uid:gid (recursive by default). Returns the job id."""
    return call("filesystem.chown", {"path": path, "uid": uid, "gid": gid, "options": {"recursive": recursive}})


@mcp.tool()
def read_file(path: str) -> str:
    """Read the contents of a file on the TrueNAS host. Returns the file content as a string."""
    with session() as c:
        # filesystem.get is a download job: core.download returns [job_id, url] and the
        # bytes are served from that one-shot url.
        job_id, url = c.call("core.download", "filesystem.get", [path], os.path.basename(path) or "file")
        with httpx.Client(base_url=TRUENAS_HOST, verify=False, timeout=60) as h:
            r = h.get(url)
            r.raise_for_status()
        # A failed read (missing file, permissions) still answers 200 with an empty body;
        # only the job state tells the difference.
        _wait_job(c, job_id)
    return r.content.decode("utf-8", errors="replace")


@mcp.tool()
def write_file(path: str, content: str, mode: str | None = None) -> dict:
    """Write (overwrite) a file at an absolute path on the TrueNAS host with the given text content.
    Overwriting keeps the existing owner and permissions; pass `mode` (octal string, e.g. "0700")
    to set permissions explicitly. Returns the size, mode and owner read back from the server."""
    import json as _json
    options: dict = {}
    if mode is not None:
        options["mode"] = int(mode, 8)
    files = {
        "data": (None, _json.dumps({"method": "filesystem.put", "params": [path, options]}), "application/json"),
        "file": ("file", content.encode("utf-8"), "application/octet-stream"),
    }
    # Uploads have no websocket equivalent; /_upload starts the filesystem.put job.
    with httpx.Client(base_url=TRUENAS_HOST, headers={"Authorization": f"Bearer {TRUENAS_API_KEY}"},
                      verify=False, timeout=60) as h:
        r = h.post("/_upload", files=files)
        r.raise_for_status()
        job_id = r.json()["job_id"]
    with session() as c:
        _wait_job(c, job_id)
        st = c.call("filesystem.stat", path)
    return {"path": path, "size": st["size"], "mode": oct(st["mode"] & 0o7777), "uid": st["uid"], "gid": st["gid"]}


# ── VMs ───────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_vms() -> list:
    """List all virtual machines."""
    return call("vm.query")


@mcp.tool()
def start_vm(vm_id: int) -> None:
    """Start a virtual machine by ID."""
    call("vm.start", vm_id)


@mcp.tool()
def stop_vm(vm_id: int, force: bool = False) -> int:
    """Stop a virtual machine by ID. Set force=True for immediate shutdown. Returns the job id."""
    return call("vm.stop", vm_id, {"force_after_timeout": force})


if __name__ == "__main__":
    mcp.run()
