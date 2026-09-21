"""VarunOps Windows endpoint agent.

Security design:
- Uses HTTPS certificate validation from Python/Windows by default.
- Per-device key after one-time enrollment; the bootstrap token is deleted locally.
- Polls only structured allow-listed software commands (install/update/uninstall).
- Never evaluates server-provided shell text and never uses shell=True.
- Validates Winget IDs against the separately fetched authenticated server manifest before execution.

Set dry_run=false in agent.json only after testing on a non-critical endpoint.
"""
from __future__ import annotations

import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request

if os.name == "nt":
    import winreg
else:
    winreg = None

try:
    import psutil
except Exception:
    psutil = None

PROGRAM_DATA = Path(os.getenv("PROGRAMDATA", Path.home())) / "VarunOps"
CONFIG_PATH = Path(os.getenv("VARUNOPS_CONFIG", PROGRAM_DATA / "agent.json"))
LOG_PATH = PROGRAM_DATA / "agent.log"
SAFE_WINGET_ID = re.compile(r"^[A-Za-z0-9._+-]{2,120}$")
ALLOWED_ACTIONS = {"install", "update", "uninstall"}


def setup_logging():
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("varunops-agent")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger

LOG = setup_logging()


def load_config():
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Missing config: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    url = str(cfg.get("server_url", "")).rstrip("/")
    if not url:
        raise RuntimeError("server_url is required")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Non-local VarunOps servers must use HTTPS")
    cfg["server_url"] = url
    return cfg


def save_config(cfg):
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    temp.replace(CONFIG_PATH)


def request_json(cfg, path, *, method="GET", body=None, extra_headers=None, timeout=30):
    url = cfg["server_url"] + path
    headers = {"Accept": "application/json", "User-Agent": "VarunOps-Agent/1.0"}
    if cfg.get("agent_id") and cfg.get("agent_key"):
        headers["X-Agent-ID"] = cfg["agent_id"]
        headers["X-Agent-Key"] = cfg["agent_key"]
    if extra_headers:
        headers.update(extra_headers)
    payload = None
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(2_000_000)
            return json.loads(data.decode("utf-8")) if data else {}
    except urllib.error.HTTPError as e:
        detail = e.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection failed: {e.reason}") from e


def powershell_value(script, timeout=12):
    if os.name != "nt":
        return ""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout, check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout.strip()[:500] if result.returncode == 0 else ""
    except Exception:
        return ""


def serial_number():
    return powershell_value("(Get-CimInstance Win32_BIOS).SerialNumber")


def memory_gb():
    if os.name != "nt":
        return ""
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]
    stat = MEMORYSTATUSEX(); stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return f"{stat.ullTotalPhys / (1024**3):.1f} GB"
    return ""


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return None


def system_info():
    total, used, free = shutil.disk_usage(Path.home().anchor or "/")
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown",
        "memory": memory_gb() or "Unknown",
        "system_disk": f"{total / (1024**3):.0f} GB",
        "agent_version": "2.0",
        "manufacturer": powershell_value("(Get-CimInstance Win32_ComputerSystem).Manufacturer"),
        "model": powershell_value("(Get-CimInstance Win32_ComputerSystem).Model"),
        "cpu_name": powershell_value("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"),
    }


def registry_programs():
    if winreg is None:
        return []
    programs = []
    locations = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in locations:
        try:
            with winreg.OpenKey(hive, path) as root:
                count = winreg.QueryInfoKey(root)[0]
                for i in range(count):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, i)) as sub:
                            name = winreg.QueryValueEx(sub, "DisplayName")[0]
                            try: version = winreg.QueryValueEx(sub, "DisplayVersion")[0]
                            except OSError: version = ""
                            try: publisher = winreg.QueryValueEx(sub, "Publisher")[0]
                            except OSError: publisher = ""
                            if name:
                                programs.append((str(name)[:180], str(version)[:64], str(publisher)[:140]))
                    except OSError:
                        continue
        except OSError:
            continue
    # de-duplicate while retaining a stable order
    seen=set(); output=[]
    for item in programs:
        key=(item[0].casefold(),item[1],item[2])
        if key not in seen:
            seen.add(key);output.append(item)
    return output


def device_metrics():
    total, used, free = shutil.disk_usage(Path.home().anchor or "/")
    volumes = []
    if psutil is not None:
        seen_mounts = set()
        try:
            for part in psutil.disk_partitions(all=False):
                mount = str(part.mountpoint or "").strip()
                if not mount or mount.casefold() in seen_mounts:
                    continue
                seen_mounts.add(mount.casefold())
                try:
                    usage = psutil.disk_usage(mount)
                except (PermissionError, OSError):
                    continue
                volumes.append({
                    "mount": mount[:40],
                    "filesystem": str(part.fstype or "")[:32],
                    "percent": round(float(usage.percent), 1),
                    "used_gb": round(float(usage.used) / (1024**3), 2),
                    "total_gb": round(float(usage.total) / (1024**3), 2),
                })
                if len(volumes) >= 12:
                    break
        except Exception:
            volumes = []
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.15)
        boot = float(psutil.boot_time())
        return {
            "cpu_percent": round(float(cpu), 1),
            "memory_percent": round(float(vm.percent), 1),
            "memory_used_gb": round(float(vm.used) / (1024**3), 2),
            "memory_total_gb": round(float(vm.total) / (1024**3), 2),
            "storage_percent": round((used / total * 100) if total else 0, 1),
            "storage_used_gb": round(used / (1024**3), 2),
            "storage_total_gb": round(total / (1024**3), 2),
            "storage_volumes": volumes,
            "uptime_seconds": max(0, int(time.time() - boot)),
        }
    return {
        "cpu_percent": 0,
        "memory_percent": 0,
        "memory_used_gb": 0,
        "memory_total_gb": 0,
        "storage_percent": round((used / total * 100) if total else 0, 1),
        "storage_used_gb": round(used / (1024**3), 2),
        "storage_total_gb": round(total / (1024**3), 2),
        "storage_volumes": volumes,
        "uptime_seconds": 0,
    }


def boot_time_iso():
    if psutil is not None:
        return datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc).isoformat()
    value = powershell_value("(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')")
    return value or ""


def recent_power_events():
    if os.name != "nt":
        return []
    script = r"""
    $e=Get-WinEvent -FilterHashtable @{LogName='System'; Id=6005,6006,6008} -MaxEvents 20 -ErrorAction SilentlyContinue |
      Select-Object Id,@{N='Time';E={$_.TimeCreated.ToUniversalTime().ToString('o')}}
    $e | ConvertTo-Json -Compress
    """
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=15, check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        raw = json.loads(result.stdout.strip())
        rows = raw if isinstance(raw, list) else [raw]
        output=[]
        for row in rows[:20]:
            event_id=int(row.get("Id",0))
            kind={6005:"boot",6006:"shutdown",6008:"unexpected_shutdown"}.get(event_id)
            if kind and row.get("Time"):
                output.append({"event_type":kind,"occurred_at":row["Time"],"source_id":str(event_id)})
        return output
    except Exception:
        return []


def software_inventory():
    return [{"name": name, "version": version, "publisher": publisher} for name, version, publisher in registry_programs()[:700]]


def _rewrite_registry_string_list(root_path, values):
    if winreg is None:
        return
    access = winreg.KEY_READ | winreg.KEY_SET_VALUE | getattr(winreg, "KEY_WOW64_64KEY", 0)
    key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, root_path, 0, access)
    try:
        # Snapshot names first, then delete only numbered URL-list entries. This avoids
        # index shifting while preserving unrelated managed values under the same key.
        value_names = []
        count = winreg.QueryInfoKey(key)[1]
        for idx in range(count):
            try:
                value_names.append(winreg.EnumValue(key, idx)[0])
            except OSError:
                continue
        for name in value_names:
            if str(name).isdigit():
                try:
                    winreg.DeleteValue(key, name)
                except OSError:
                    pass
        for idx, value in enumerate(values, 1):
            winreg.SetValueEx(key, str(idx), 0, winreg.REG_SZ, str(value))
    finally:
        winreg.CloseKey(key)


def apply_network_policy(policy):
    if os.name != "nt" or winreg is None:
        return "Browser policy enforcement is Windows-only"
    all_browsers=[r"SOFTWARE\Policies\Microsoft\Edge", r"SOFTWARE\Policies\Google\Chrome"]
    # VarunOps treats these URL list keys as exclusively managed by this agent.
    for base in all_browsers:
        _rewrite_registry_string_list(base + r"\URLBlocklist", [])
        _rewrite_registry_string_list(base + r"\URLAllowlist", [])
    if not policy:
        return "Cleared VarunOps browser network policy"
    mode = str(policy.get("mode", "blocklist"))
    allowed = [str(x) for x in policy.get("allowed_sites", [])[:300]]
    blocked = [str(x) for x in policy.get("blocked_sites", [])[:300]]
    if mode == "allowlist":
        block_values = ["*"]
        allow_values = allowed
    else:
        block_values = blocked
        allow_values = []
    browsers=[]
    if policy.get("enforce_edge", True):
        browsers.append(r"SOFTWARE\Policies\Microsoft\Edge")
    if policy.get("enforce_chrome", True):
        browsers.append(r"SOFTWARE\Policies\Google\Chrome")
    for base in browsers:
        _rewrite_registry_string_list(base + r"\URLBlocklist", block_values)
        _rewrite_registry_string_list(base + r"\URLAllowlist", allow_values)
    return f"Applied {policy.get('name','network policy')} to {len(browsers)} browser(s)"


def detect_catalog_apps(manifest):
    installed = registry_programs()
    report=[]
    for app in manifest.get("apps", []):
        names=[str(x).casefold() for x in app.get("detection_names", []) if x]
        if not names:
            names=[str(app.get("name", "")).casefold()]
        match=None
        for display_name, version, _publisher in installed:
            low=display_name.casefold()
            if any(name == low or name in low for name in names):
                match=(display_name,version);break
        if match:
            report.append({"slug": app["slug"], "version": match[1], "detected_name": match[0]})
    return report


def enroll(cfg):
    if cfg.get("agent_id") and cfg.get("agent_key"):
        return cfg
    token = cfg.get("enrollment_token", "")
    if not token:
        raise RuntimeError("Agent is not enrolled and enrollment_token is missing")
    body={
        "name": cfg.get("name") or socket.gethostname(),
        "branch": cfg.get("branch", ""),
        "device_type": cfg.get("device_type", "Desktop"),
        "os_version": platform.platform(),
        "serial_number": serial_number(),
    }
    result=request_json(cfg,"/api/agent/enroll/",method="POST",body=body,extra_headers={"X-Enrollment-Token":token})
    cfg["agent_id"]=result["agent_id"]
    cfg["agent_key"]=result["agent_key"]
    cfg.pop("enrollment_token",None)  # bootstrap secret should not remain on disk
    save_config(cfg)
    LOG.info("Enrollment succeeded for %s", result.get("name"))
    return cfg


def heartbeat(cfg, manifest):
    return request_json(cfg,"/api/agent/heartbeat/",method="POST",body={
        "ip_address": local_ip(),
        "os_version": platform.platform(),
        "serial_number": serial_number(),
        "system_info": system_info(),
        "apps": detect_catalog_apps(manifest),
        "software_inventory": software_inventory(),
        "metrics": device_metrics(),
        "boot_time": boot_time_iso(),
        "power_events": recent_power_events(),
    })


def run_winget(action, winget_id, dry_run=True):
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Unsupported action")
    if not SAFE_WINGET_ID.fullmatch(winget_id or ""):
        raise ValueError("Unsafe or missing Winget package id")
    if dry_run:
        return True, f"Dry run: would {action} {winget_id}"
    executable = shutil.which("winget")
    if not executable:
        return False, "winget.exe was not found"
    base=[executable]
    if action == "install":
        args=["install","--id",winget_id,"--exact","--silent","--accept-package-agreements","--accept-source-agreements","--disable-interactivity"]
    elif action == "update":
        args=["upgrade","--id",winget_id,"--exact","--silent","--accept-package-agreements","--accept-source-agreements","--disable-interactivity"]
    else:
        args=["uninstall","--id",winget_id,"--exact","--silent","--disable-interactivity"]
    try:
        result=subprocess.run(base+args,capture_output=True,text=True,timeout=1200,check=False,shell=False,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        output=(result.stdout+"\n"+result.stderr).strip()[-3500:]
        return result.returncode==0, output or f"winget exited with {result.returncode}"
    except subprocess.TimeoutExpired:
        return False,"winget operation timed out after 20 minutes"
    except Exception as e:
        return False,f"winget error: {type(e).__name__}"


def process_commands(cfg, manifest):
    manifest_by_slug={a["slug"]:a for a in manifest.get("apps",[])}
    payload=request_json(cfg,"/api/agent/commands/")
    for cmd in payload.get("commands",[]):
        cid=str(cmd.get("id",""));action=str(cmd.get("action",""));server_app=cmd.get("app",{});slug=str(server_app.get("slug",""))
        approved=manifest_by_slug.get(slug)
        ok=False;message="Command rejected by local validation";version=""
        if action in ALLOWED_ACTIONS and approved:
            # Bind command payload back to the independently fetched manifest.
            winget_id=str(server_app.get("winget_id",""))
            if winget_id == str(approved.get("winget_id","")) and SAFE_WINGET_ID.fullmatch(winget_id or ""):
                ok,message=run_winget(action,winget_id,bool(cfg.get("dry_run",True)))
                version=str(approved.get("latest_version","")) if ok and action!="uninstall" else ""
        request_json(cfg,f"/api/agent/commands/{urllib.parse.quote(cid)}/result/",method="POST",body={
            "status":"succeeded" if ok else "failed","message":message,"version":version,
        })
        LOG.info("Command %s %s: %s", cid, "succeeded" if ok else "failed", message[:250])


def uninstall_detected(name, dry_run=True):
    name = str(name or "").strip()[:180]
    if not name:
        return False, "Missing software name"
    installed_names = {n.casefold(): n for n, _v, _p in registry_programs()}
    actual = installed_names.get(name.casefold())
    if not actual:
        return True, "Software is no longer detected"
    if dry_run:
        return True, f"Dry run: would uninstall detected software {actual}"
    executable = shutil.which("winget")
    if not executable:
        return False, "winget.exe was not found"
    try:
        result = subprocess.run(
            [executable, "uninstall", "--name", actual, "--exact", "--silent", "--disable-interactivity"],
            capture_output=True, text=True, timeout=1200, check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output=(result.stdout+"\n"+result.stderr).strip()[-3500:]
        return result.returncode == 0, output or f"winget exited with {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "Uninstall timed out after 20 minutes"
    except Exception as exc:
        return False, f"Uninstall error: {type(exc).__name__}"


def process_agent_tasks(cfg):
    payload = request_json(cfg, "/api/agent/tasks/")
    for item in payload.get("tasks", []):
        task_id = str(item.get("id", ""))
        kind = str(item.get("kind", ""))
        task_payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        ok=False; message="Unsupported agent task"
        if kind == "uninstall_detected":
            ok, message = uninstall_detected(task_payload.get("display_name"), bool(cfg.get("dry_run", True)))
        request_json(cfg, f"/api/agent/tasks/{urllib.parse.quote(task_id)}/result/", method="POST", body={
            "status": "succeeded" if ok else "failed", "message": message,
        })


def run_once(cfg):
    cfg=enroll(cfg)
    manifest=request_json(cfg,"/api/agent/manifest/")
    try:
        message = apply_network_policy(manifest.get("network_policy"))
        LOG.info(message)
    except Exception as exc:
        LOG.error("Network policy apply failed: %s", exc)
    heartbeat(cfg,manifest)
    process_commands(cfg,manifest)
    process_agent_tasks(cfg)


def main():
    cfg=load_config()
    interval=max(10,min(300,int(cfg.get("poll_seconds",20))))
    once="--once" in sys.argv
    if "--pair" in sys.argv:
        try:
            idx=sys.argv.index("--pair")
            code=sys.argv[idx+1]
        except Exception:
            raise RuntimeError("Use --pair 12345678")
        cfg=enroll(cfg)
        result=request_json(cfg,"/api/agent/pair/",method="POST",body={"code":code})
        LOG.info("Device paired with %s", result.get("employee"))
        print(f"Paired with {result.get('employee')}")
        return
    while True:
        try:
            run_once(cfg)
        except Exception as e:
            LOG.error("Agent cycle failed: %s", e)
        if once:break
        time.sleep(interval)
        try:cfg=load_config()
        except Exception as e:LOG.error("Config reload failed: %s",e)


if __name__ == "__main__":
    main()
