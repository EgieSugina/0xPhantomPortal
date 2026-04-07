import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from . import config
from .main_window import MainWindow


def _warn_missing_ssh_tools() -> None:
    config.prepend_bundled_ssh_tools_path()
    ssh = config.which_ssh_client()
    sshpass = config.which_sshpass()
    if ssh and sshpass:
        return
    parts: list[str] = []
    if not ssh:
        parts.append(
            "• <b>ssh</b> (OpenSSH client) not found in PATH. "
            "SSH port-forward tunnels will not start."
        )
    if not sshpass:
        parts.append(
            "• <b>sshpass</b> not found. Saved-password tunnels cannot run "
            "(SSH keys, identity files, and ssh-agent still work)."
        )
    tip = (
        "<p>Examples:</p>"
        "<p>Debian/Ubuntu: <code>sudo apt install openssh-client sshpass</code><br>"
        "Arch: <code>sudo pacman -S openssh sshpass</code><br>"
        "Fedora: <code>sudo dnf install openssh-clients sshpass</code></p>"
        "<p>To bundle binaries with a PyInstaller build, see comments in <code>build.sh</code> "
        "(you must supply binaries built for your target OS; portability is your responsibility).</p>"
    )
    QMessageBox.warning(
        None,
        "External SSH tools",
        "<html><body style='white-space:pre-wrap;'>" + "<br><br>".join(parts) + tip + "</body></html>",
    )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_DISPLAY_NAME)
    _warn_missing_ssh_tools()
    config.TITLE_FONT_FAMILY = config.load_title_font()
    icon = config.load_app_icon()
    app.setWindowIcon(icon)
    win = MainWindow()
    win.setWindowIcon(icon)
    win.show()
    sys.exit(app.exec())
