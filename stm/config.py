import json
import os
import shutil
import time
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

try:
    import paramiko  # noqa: F401
    PARAMIKO_OK = True
except ImportError:
    PARAMIKO_OK = False

try:
    import keyring
    KEYRING_OK = True
except ImportError:
    keyring = None
    KEYRING_OK = False

KEYRING_SERVICE = "0xPhantomPortal"
APP_DISPLAY_NAME = "0xPhantomPortal"
TITLE_FONT_FAMILY = ""

CONFIG_FILE = Path.home() / ".config" / "0xPhantomPortal" / "tunnels.json"
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
SFTP_ACCOUNTS_FILE = CONFIG_FILE.parent / "sftp_accounts.json"

THEME_PRIMARY = "#aca3ff"
THEME_PRIMARY_DARK = "#6f5fea"
THEME_PRIMARY_MUTED = "#5948d3"
THEME_BG_WIDGET = "#0d0d16"
THEME_BG_TABLE = "#12121d"
THEME_BG_TABLE_ALT = "#191924"
THEME_BORDER = "#484752"
THEME_HEADER_BG = "#1f1e2b"
THEME_HEADER_FG = "#aca9b6"
THEME_INPUT_BG = "#000000"
THEME_INPUT_BORDER = "#484752"
THEME_BTN_SECONDARY = "#1f1e2b"
THEME_BTN_DISABLED = "#252532"
THEME_LOG_BG = "#000000"
THEME_LOG_FG = "#ece9f7"
THEME_SPLITTER = "#252532"
THEME_TITLE = "#aca3ff"

STATUS_CONNECTED = "#00fd93"
STATUS_CONNECTING = "#ffb74d"
STATUS_DISCONNECTED = "#ff6e84"
STATUS_DISABLED = "#8b7a9e"

KIND_SOCKS = "socks"
KIND_LOCAL = "local"
KIND_REMOTE = "remote"
TUNNEL_KINDS = (KIND_SOCKS, KIND_LOCAL, KIND_REMOTE)


def resource_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def prepend_bundled_ssh_tools_path() -> None:
    """If PyInstaller bundled `ssh` / `sshpass` next to extracted assets, put them on PATH."""
    rd = resource_dir()
    if not any((rd / name).is_file() for name in ("ssh", "sshpass")):
        return
    prefix = str(rd)
    os.environ["PATH"] = prefix + os.pathsep + os.environ.get("PATH", "")


def which_ssh_client() -> str | None:
    return shutil.which("ssh")


def which_sshpass() -> str | None:
    return shutil.which("sshpass")


def load_app_icon() -> QIcon:
    svg = resource_dir() / "icon.svg"
    if not svg.exists():
        return QIcon()
    ic = QIcon(str(svg))
    if not ic.isNull():
        return ic
    r = QSvgRenderer(str(svg))
    if not r.isValid():
        return QIcon()
    side = 256
    img = QImage(side, side, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    r.render(p)
    p.end()
    return QIcon(QPixmap.fromImage(img))


def load_title_font() -> str:
    font_path = resource_dir() / "font" / "Anurati-Regular.otf"
    if not font_path.exists():
        return ""
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        return ""
    families = QFontDatabase.applicationFontFamilies(font_id)
    return families[0] if families else ""


def _coerce_int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def normalize_tunnel_record(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    host = str(raw.get("host", "")).strip()
    if not host:
        return None
    t = {k: raw[k] for k in raw}
    t["host"] = host
    kind = t.get("kind", KIND_SOCKS)
    if kind not in TUNNEL_KINDS:
        kind = KIND_SOCKS
    t["kind"] = kind
    tid = str(t.get("id", "")).strip()
    if not tid:
        tid = str(int(time.time() * 1000))
    t["id"] = tid
    t["name"] = str(t.get("name", "")).strip() or host
    t["username"] = str(t.get("username", "")).strip()
    t["ssh_port"] = _coerce_int(t.get("ssh_port"), 22)
    t["identity_file"] = str(t.get("identity_file", "")).strip()
    t["use_password"] = bool(t.get("use_password", False))
    t["auto_start"] = bool(t.get("auto_start", False))
    if kind == KIND_SOCKS:
        t["local_port"] = _coerce_int(t.get("local_port"), 1080)
    elif kind == KIND_LOCAL:
        t["local_bind"] = str(t.get("local_bind", "127.0.0.1")).strip() or "127.0.0.1"
        t["local_port"] = _coerce_int(t.get("local_port"), 8080)
        t["remote_host"] = str(t.get("remote_host", "127.0.0.1")).strip() or "127.0.0.1"
        t["remote_port"] = _coerce_int(t.get("remote_port"), 80)
    else:
        t["remote_bind"] = str(t.get("remote_bind", "")).strip()
        t["remote_port"] = _coerce_int(t.get("remote_port"), 9090)
        t["local_host"] = str(t.get("local_host", "127.0.0.1")).strip() or "127.0.0.1"
        t["local_port"] = _coerce_int(t.get("local_port"), 3000)
    return t


def parse_tunnels_json(text: str) -> tuple[list | None, str | None]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, str(e)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("tunnels"), list):
        return data["tunnels"], None
    return None, 'Expected a JSON array or an object with a "tunnels" key.'


def _pw_key(tid: str) -> str:
    return f"tunnel_{tid}"


def save_password(tid: str, password: str):
    if KEYRING_OK and keyring:
        keyring.set_password(KEYRING_SERVICE, _pw_key(tid), password)
    else:
        pw_file = CONFIG_FILE.parent / f".pw_{tid}"
        pw_file.write_bytes(bytes(b ^ 0x5A for b in password.encode()))
        pw_file.chmod(0o600)


def load_password(tid: str) -> str:
    if KEYRING_OK and keyring:
        return keyring.get_password(KEYRING_SERVICE, _pw_key(tid)) or ""
    pw_file = CONFIG_FILE.parent / f".pw_{tid}"
    if pw_file.exists():
        return bytes(b ^ 0x5A for b in pw_file.read_bytes()).decode()
    return ""


def delete_password(tid: str):
    if KEYRING_OK and keyring:
        try:
            keyring.delete_password(KEYRING_SERVICE, _pw_key(tid))
        except Exception:
            pass
    else:
        (CONFIG_FILE.parent / f".pw_{tid}").unlink(missing_ok=True)


def load_sftp_accounts() -> list[dict]:
    if not SFTP_ACCOUNTS_FILE.exists():
        return []
    try:
        data = json.loads(SFTP_ACCOUNTS_FILE.read_text())
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "host": str(item.get("host", "")).strip(),
                "username": str(item.get("username", "")).strip(),
                "port": int(item.get("port", 22) or 22),
                "key_file": str(item.get("key_file", "")).strip(),
                "use_socks5": bool(item.get("use_socks5", False)),
                "socks_host": str(item.get("socks_host", "127.0.0.1")).strip() or "127.0.0.1",
                "socks_port": int(item.get("socks_port", 1080) or 1080),
            }
        )
    return out


def save_sftp_accounts(accounts: list[dict]):
    SFTP_ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2))


def sftp_password_id(account_name: str) -> str:
    return f"sftp_account_{account_name.strip()}"
