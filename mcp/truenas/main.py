#!/usr/bin/env python3
"""TrueNAS Scale MCP Server — connects to a local TrueNAS Scale instance via REST API."""

import os
import httpx
from mcp.server.fastmcp import FastMCP

TRUENAS_HOST = os.environ.get("TRUENAS_HOST", "http://truenas.local")
TRUENAS_API_KEY = os.environ.get("TRUENAS_API_KEY", "")

mcp = FastMCP("truenas")


def client() -> httpx.Client:
    headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}", "Content-Type": "application/json"}
    return httpx.Client(base_url=f"{TRUENAS_HOST}/api/v2.0", headers=headers, verify=False, timeout=30)


def get(path: str, params: dict | None = None) -> dict | list:
    with client() as c:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()


def post(path: str, data: dict) -> dict | list:
    with client() as c:
        r = c.post(path, json=data)
        r.raise_for_status()
        return r.json()


def delete(path: str, params: dict | None = None) -> dict | list | None:
    with client() as c:
        r = c.delete(path, params=params)
        r.raise_for_status()
        return r.json() if r.content else None


# ── System ────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_system_info() -> dict:
    """Get TrueNAS system information (hostname, version, uptime, etc.)."""
    return get("/system/info")


@mcp.tool()
def get_system_version() -> str:
    """Get the TrueNAS Scale version string."""
    return get("/system/version")


@mcp.tool()
def get_system_state() -> str:
    """Get the current system state (READY, BOOTING, etc.)."""
    return get("/system/state")


@mcp.tool()
def reboot_system() -> dict:
    """Reboot the TrueNAS system."""
    return post("/system/reboot", {})


@mcp.tool()
def shutdown_system() -> dict:
    """Shut down the TrueNAS system."""
    return post("/system/shutdown", {})


# ── Alerts ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_alerts() -> list:
    """List all active system alerts."""
    return get("/alert/list")


@mcp.tool()
def dismiss_alert(uuid: str) -> None:
    """Dismiss an alert by its UUID."""
    post("/alert/dismiss", {"uuid": uuid})


# ── Storage / Pools ───────────────────────────────────────────────────────────

@mcp.tool()
def list_pools() -> list:
    """List all ZFS storage pools with their health and status."""
    return get("/pool")


@mcp.tool()
def get_pool(pool_id: int) -> dict:
    """Get details for a specific pool by ID."""
    return get(f"/pool/id/{pool_id}")


@mcp.tool()
def list_datasets(pool_name: str | None = None) -> list:
    """List all ZFS datasets. Optionally filter by pool name."""
    params = {}
    if pool_name:
        params["pool"] = pool_name
    return get("/pool/dataset", params=params)


@mcp.tool()
def get_dataset(dataset_id: str) -> dict:
    """Get details for a specific dataset by ID (e.g. 'tank/data')."""
    return get(f"/pool/dataset/id/{dataset_id}")


@mcp.tool()
def create_dataset(name: str, comments: str = "", compression: str = "lz4", atime: str = "off") -> dict:
    """
    Create a new ZFS dataset.
    - name: full dataset path, e.g. 'tank/newdataset'
    - compression: lz4, gzip, zstd, off
    - atime: on or off
    """
    return post("/pool/dataset", {"name": name, "comments": comments, "compression": compression, "atime": atime})


@mcp.tool()
def delete_dataset(dataset_id: str, recursive: bool = False) -> None:
    """Delete a ZFS dataset. Set recursive=True to also remove children."""
    delete(f"/pool/dataset/id/{dataset_id}", params={"recursive": recursive})


@mcp.tool()
def list_snapshots(dataset: str | None = None) -> list:
    """List ZFS snapshots. Optionally filter by dataset name."""
    params = {}
    if dataset:
        params["dataset"] = dataset
    return get("/zfs/snapshot", params=params)


@mcp.tool()
def create_snapshot(dataset: str, name: str, recursive: bool = False) -> dict:
    """
    Create a ZFS snapshot.
    - dataset: dataset path, e.g. 'tank/data'
    - name: snapshot name suffix, e.g. 'manual-2024-01-01'
    """
    return post("/zfs/snapshot", {"dataset": dataset, "name": name, "recursive": recursive})


@mcp.tool()
def delete_snapshot(snapshot_id: str) -> None:
    """Delete a ZFS snapshot by ID (e.g. 'tank/data@snap1')."""
    delete(f"/zfs/snapshot/id/{snapshot_id}")


# ── Disks ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_disks() -> list:
    """List all physical disks with model, size, serial, and temperature."""
    return get("/disk")


@mcp.tool()
def get_disk_temperature(disk_name: str) -> dict:
    """Get S.M.A.R.T. temperature for a disk (e.g. 'sda')."""
    return post("/disk/temperature", {"name": disk_name})


@mcp.tool()
def get_disk_smart_results(disk_name: str) -> list:
    """Get S.M.A.R.T. test results for a disk."""
    return get(f"/disk/smarttest/results/{disk_name}")


# ── Network ───────────────────────────────────────────────────────────────────

@mcp.tool()
def list_interfaces() -> list:
    """List all network interfaces with IP addresses and link state."""
    return get("/interface")


@mcp.tool()
def get_network_config() -> dict:
    """Get network configuration (default gateway, nameservers, hostname)."""
    return get("/network/configuration")


# ── Shares ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_smb_shares() -> list:
    """List all SMB/Windows shares."""
    return get("/sharing/smb")


@mcp.tool()
def list_nfs_shares() -> list:
    """List all NFS shares."""
    return get("/sharing/nfs")


@mcp.tool()
def create_smb_share(path: str, name: str, comment: str = "") -> dict:
    """
    Create a new SMB share.
    - path: absolute path to the dataset, e.g. '/mnt/tank/media'
    - name: share name visible to Windows clients
    """
    return post("/sharing/smb", {"path": path, "name": name, "comment": comment})


@mcp.tool()
def delete_smb_share(share_id: int) -> None:
    """Delete an SMB share by ID."""
    delete(f"/sharing/smb/id/{share_id}")


# ── Services ──────────────────────────────────────────────────────────────────

@mcp.tool()
def list_services() -> list:
    """List all services (SMB, NFS, SSH, etc.) with their running state."""
    return get("/service")


@mcp.tool()
def start_service(service_name: str) -> bool:
    """Start a service by name (e.g. 'smb', 'nfs', 'ssh', 'ftp', 'snmp')."""
    return post("/service/start", {"service": service_name})


@mcp.tool()
def stop_service(service_name: str) -> bool:
    """Stop a service by name."""
    return post("/service/stop", {"service": service_name})


@mcp.tool()
def restart_service(service_name: str) -> bool:
    """Restart a service by name."""
    return post("/service/restart", {"service": service_name})


# ── Users & Groups ────────────────────────────────────────────────────────────

@mcp.tool()
def list_users() -> list:
    """List all local users."""
    return get("/user")


@mcp.tool()
def list_groups() -> list:
    """List all local groups."""
    return get("/group")


# ── Jobs / Tasks ──────────────────────────────────────────────────────────────

@mcp.tool()
def list_jobs(state: str | None = None) -> list:
    """
    List background jobs/tasks.
    - state: filter by state — RUNNING, SUCCESS, FAILED, ABORTED (optional)
    """
    params = {}
    if state:
        params["state"] = state
    return get("/core/get_jobs", params=params)


@mcp.tool()
def list_cloud_sync_tasks() -> list:
    """List all cloud sync tasks."""
    return get("/cloudsync")


@mcp.tool()
def run_cloud_sync_task(task_id: int) -> dict:
    """Trigger a cloud sync task to run immediately."""
    return post(f"/cloudsync/id/{task_id}/sync", {})


@mcp.tool()
def list_replication_tasks() -> list:
    """List all ZFS replication tasks."""
    return get("/replication")


@mcp.tool()
def list_periodic_snapshot_tasks() -> list:
    """List all automatic snapshot tasks."""
    return get("/pool/snapshottask")


# ── Apps (TrueNAS Scale) ──────────────────────────────────────────────────────

@mcp.tool()
def list_apps() -> list:
    """List all installed TrueNAS Scale apps."""
    return get("/app")


@mcp.tool()
def get_app(app_name: str) -> dict:
    """Get details for a specific app by name."""
    return get(f"/app/id/{app_name}")


@mcp.tool()
def start_app(app_name: str) -> dict:
    """Start an app by name."""
    return post(f"/app/id/{app_name}/start", {})


@mcp.tool()
def stop_app(app_name: str) -> dict:
    """Stop an app by name."""
    return post(f"/app/id/{app_name}/stop", {})


@mcp.tool()
def list_available_apps(search: str | None = None) -> list:
    """List apps installable from the catalog. Optionally filter by a name/title substring.
    Returns name (catalog id), title, train, catalog, and latest versions for each match."""
    apps = get("/app/available")
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
    details = post("/catalog/get_app_details", {"app_name": app_name, "app_version_details": {"train": train}})
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
    return post("/app", {
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
    entries = post("/filesystem/listdir", {"path": path})
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
    return post("/filesystem/mkdir", {"path": path, "options": {"mode": mode}})


@mcp.tool()
def chown_path(path: str, uid: int, gid: int, recursive: bool = True) -> int:
    """Change ownership of a path to uid:gid (recursive by default). Returns the job id."""
    return post("/filesystem/chown", {"path": path, "uid": uid, "gid": gid, "options": {"recursive": recursive}})


# ── VMs ───────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_vms() -> list:
    """List all virtual machines."""
    return get("/vm")


@mcp.tool()
def start_vm(vm_id: int) -> None:
    """Start a virtual machine by ID."""
    post(f"/vm/id/{vm_id}/start", {})


@mcp.tool()
def stop_vm(vm_id: int, force: bool = False) -> None:
    """Stop a virtual machine by ID. Set force=True for immediate shutdown."""
    post(f"/vm/id/{vm_id}/stop", {"force_after_timeout": force})


if __name__ == "__main__":
    mcp.run()
