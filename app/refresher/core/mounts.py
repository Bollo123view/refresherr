import os
import psutil

def is_mount_present(path: str) -> bool:
    try:
        for p in psutil.disk_partitions(all=True):
            if os.path.abspath(path) == os.path.abspath(p.mountpoint):
                return True
    except Exception:
        pass
    return os.path.ismount(path) or os.path.exists(path)
