"""
Discord IPC Socket Discovery Module.

Audits host system and Flatpak sandbox locations for running Discord/Vesktop IPC Unix sockets.
"""

import os
import glob
import stat
import pwd
import grp
import socket
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SocketMetadata:
    path: str
    client_type: str
    exists: bool
    is_socket: bool
    owner: str
    group: str
    permissions: str
    can_connect: bool
    error_reason: Optional[str] = None

    def __str__(self) -> str:
        if not self.exists:
            return f"[{self.client_type}] {self.path} (MISSING)"
        
        status = "SOCKET" if self.is_socket else "NOT_SOCKET"
        conn = "CONNECTED" if self.can_connect else f"CONNECT_FAILED ({self.error_reason})"
        return (
            f"[{self.client_type}] {self.path} | Type: {status} | Owner: {self.owner}:{self.group} "
            f"| Mode: {self.permissions} | Status: {conn}"
        )


KNOWN_FLATPAK_APPS = [
    ("com.discordapp.Discord", "flatpak_discord"),
    ("dev.vencord.Vesktop", "flatpak_vesktop"),
    ("de.sharksocial.Vesktop", "flatpak_vesktop"),
    ("io.github.shifteight.webcord", "flatpak_webcord"),
    ("com.armcord.ArmCord", "flatpak_armcord"),
]


def get_dynamic_candidate_paths() -> List[tuple[str, str]]:
    """
    Generate static and dynamic candidate paths across /tmp, XDG_RUNTIME_DIR, and Flatpak app directories.
    """
    candidates: List[tuple[str, str]] = []
    seen = set()

    def add_candidate(path: str, ctype: str):
        if path not in seen:
            seen.add(path)
            candidates.append((path, ctype))

    # 1. /tmp scanning
    for i in range(10):
        add_candidate(f"/tmp/discord-ipc-{i}", "native_tmp")

    # 2. XDG_RUNTIME_DIR base & app directories
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    uid = str(os.getuid()) if hasattr(os, "getuid") else "1000"

    base_runtime_dirs = []
    if xdg_runtime:
        base_runtime_dirs.append(xdg_runtime)
    base_runtime_dirs.append(f"/run/user/{uid}")

    for base_dir in base_runtime_dirs:
        # Standard XDG runtime sockets
        for i in range(10):
            add_candidate(os.path.join(base_dir, f"discord-ipc-{i}"), "native_xdg")

        # Dynamic search under /run/user/$UID/app/*/ and $XDG_RUNTIME_DIR/app/*/
        app_base = os.path.join(base_dir, "app")
        if os.path.exists(app_base) and os.path.isdir(app_base):
            for pattern in [
                os.path.join(app_base, "*", "discord-ipc-[0-9]"),
                os.path.join(app_base, "*", "*", "discord-ipc-[0-9]"),
            ]:
                for matched_path in glob.glob(pattern):
                    # Identify client type from app dir
                    app_id = matched_path.split(os.sep)[-2]
                    ctype = f"flatpak_app_{app_id}"
                    add_candidate(matched_path, ctype)

        # Explicit known Flatpak app candidates
        for app_id, ctype in KNOWN_FLATPAK_APPS:
            app_dir = os.path.join(base_dir, "app", app_id)
            for i in range(10):
                add_candidate(os.path.join(app_dir, f"discord-ipc-{i}"), ctype)

    # 3. User home Flatpak runtime / var paths
    home_dir = os.path.expanduser("~")
    for app_id, ctype in KNOWN_FLATPAK_APPS:
        var_app_dir = os.path.join(home_dir, ".var", "app", app_id)
        for i in range(10):
            add_candidate(os.path.join(var_app_dir, f"discord-ipc-{i}"), ctype)

    return candidates


def inspect_and_probe_socket(path: str, client_type: str) -> SocketMetadata:
    """
    Inspect socket path metadata and attempt a host-side Unix socket connection.
    """
    if not os.path.exists(path):
        return SocketMetadata(
            path=path,
            client_type=client_type,
            exists=False,
            is_socket=False,
            owner="N/A",
            group="N/A",
            permissions="N/A",
            can_connect=False,
            error_reason="File does not exist",
        )

    # File exists - read stat metadata
    try:
        st = os.stat(path)
        is_sock = stat.S_ISSOCK(st.st_mode)
        mode_octal = oct(st.st_mode & 0o777)
        
        try:
            owner_name = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner_name = str(st.st_uid)
            
        try:
            group_name = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group_name = str(st.st_gid)

    except Exception as e:
        return SocketMetadata(
            path=path,
            client_type=client_type,
            exists=True,
            is_socket=False,
            owner="Unknown",
            group="Unknown",
            permissions="Unknown",
            can_connect=False,
            error_reason=f"Stat failed: {e}",
        )

    if not is_sock:
        return SocketMetadata(
            path=path,
            client_type=client_type,
            exists=True,
            is_socket=False,
            owner=owner_name,
            group=group_name,
            permissions=mode_octal,
            can_connect=False,
            error_reason="Path is not a Unix domain socket",
        )

    # Attempt host-side socket connection
    can_conn = False
    err_reason = None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(path)
        can_conn = True
    except Exception as e:
        err_reason = str(e)
    finally:
        sock.close()

    return SocketMetadata(
        path=path,
        client_type=client_type,
        exists=True,
        is_socket=True,
        owner=owner_name,
        group=group_name,
        permissions=mode_octal,
        can_connect=can_conn,
        error_reason=err_reason,
    )


def find_all_ipc_sockets() -> List[SocketMetadata]:
    """
    Scan system and return metadata for all existing candidate sockets.
    """
    results: List[SocketMetadata] = []
    for path, ctype in get_dynamic_candidate_paths():
        res = inspect_and_probe_socket(path, ctype)
        if res.exists:
            results.append(res)
    return results


def get_active_ipc_socket() -> Optional[SocketMetadata]:
    """
    Return the first connectable IPC socket metadata object, or None.
    """
    for item in find_all_ipc_sockets():
        if item.can_connect:
            return item
    return None


if __name__ == "__main__":
    import sys

    print("=== Discord IPC Socket Audit ===")
    print(f"Python: {sys.version.split()[0]}")
    print(f"XDG_RUNTIME_DIR: {os.environ.get('XDG_RUNTIME_DIR', 'Not Set')}")
    print(f"UID: {os.getuid() if hasattr(os, 'getuid') else 'Unknown'}\n")

    sockets = find_all_ipc_sockets()
    if not sockets:
        print("No existing IPC socket files found in scanned locations.")
    else:
        print(f"Found {len(sockets)} existing path(s):")
        for s in sockets:
            print(f"  {s}")

    active = get_active_ipc_socket()
    if active:
        print(f"\nLive connected socket: {active.path}")
    else:
        print("\nNo connectable active IPC socket detected.")
