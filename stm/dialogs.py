import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QMessageBox,
    QWidget,
)

from .config import (
    KEYRING_OK,
    KIND_LOCAL,
    KIND_REMOTE,
    KIND_SOCKS,
    THEME_BTN_SECONDARY,
    THEME_PRIMARY,
    TUNNEL_KINDS,
    load_password,
)


class TunnelDialog(QDialog):
    def __init__(self, parent=None, tunnel: dict = None, kind: str = KIND_SOCKS):
        super().__init__(parent)
        self._existing = tunnel or {}
        self._kind = self._existing.get("kind", kind)
        if self._kind not in TUNNEL_KINDS:
            self._kind = KIND_SOCKS
        self.setMinimumWidth(520)
        self._tid = self._existing.get("id", "")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.name_edit = QLineEdit(self._existing.get("name", ""))
        self.host_edit = QLineEdit(self._existing.get("host", ""))
        self.user_edit = QLineEdit(self._existing.get("username", ""))
        self.ssh_port = QSpinBox()
        self.ssh_port.setRange(1, 65535)
        self.ssh_port.setValue(self._existing.get("ssh_port", 22))
        self.key_edit = QLineEdit(self._existing.get("identity_file", ""))
        form.addRow("Name:", self.name_edit)
        form.addRow("Host / IP:", self.host_edit)
        form.addRow("Username:", self.user_edit)
        form.addRow("SSH Port:", self.ssh_port)
        form.addRow("Identity Key:", self.key_edit)

        self._kind_stack = QStackedWidget()
        w_socks = QWidget()
        fs = QFormLayout(w_socks)
        self.socks_local_port = QSpinBox()
        self.socks_local_port.setRange(1, 65535)
        self.socks_local_port.setValue(self._existing.get("local_port", 1080))
        fs.addRow("Local SOCKS port:", self.socks_local_port)
        self._kind_stack.addWidget(w_socks)

        w_loc = QWidget()
        fl = QFormLayout(w_loc)
        self.local_bind = QLineEdit(self._existing.get("local_bind", "127.0.0.1"))
        self.local_port = QSpinBox()
        self.local_port.setRange(1, 65535)
        self.local_port.setValue(self._existing.get("local_port", 8080))
        self.remote_host = QLineEdit(self._existing.get("remote_host", "127.0.0.1"))
        self.remote_port = QSpinBox()
        self.remote_port.setRange(1, 65535)
        self.remote_port.setValue(self._existing.get("remote_port", 80))
        fl.addRow("Listen bind:", self.local_bind)
        fl.addRow("Listen port:", self.local_port)
        fl.addRow("Remote host:", self.remote_host)
        fl.addRow("Remote port:", self.remote_port)
        self._kind_stack.addWidget(w_loc)

        w_rem = QWidget()
        fr = QFormLayout(w_rem)
        self.remote_bind = QLineEdit(self._existing.get("remote_bind", ""))
        self.remote_listen_port = QSpinBox()
        self.remote_listen_port.setRange(1, 65535)
        self.remote_listen_port.setValue(self._existing.get("remote_port", 9090))
        self.r_local_host = QLineEdit(self._existing.get("local_host", "127.0.0.1"))
        self.r_local_port = QSpinBox()
        self.r_local_port.setRange(1, 65535)
        self.r_local_port.setValue(self._existing.get("local_port", 3000))
        fr.addRow("Server bind (opt):", self.remote_bind)
        fr.addRow("Listen on server:", self.remote_listen_port)
        fr.addRow("Forward to host:", self.r_local_host)
        fr.addRow("Forward to port:", self.r_local_port)
        self._kind_stack.addWidget(w_rem)
        self._kind_stack.setCurrentIndex({KIND_SOCKS: 0, KIND_LOCAL: 1, KIND_REMOTE: 2}.get(self._kind, 0))
        form.addRow(self._kind_stack)

        self.pw_group = QGroupBox("Password Authentication")
        self.pw_group.setCheckable(True)
        self.pw_group.setChecked(self._existing.get("use_password", False))
        pw_form = QFormLayout(self.pw_group)
        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.Password)
        if self._tid:
            saved = load_password(self._tid)
            if saved:
                self.pw_edit.setText(saved)
        pw_form.addRow("Password:", self.pw_edit)
        note = QLabel("🔒 Stored in keyring" if KEYRING_OK else "⚠ keyring not installed")
        pw_form.addRow(note)

        self.auto_start = QCheckBox("Auto-start on launch")
        self.auto_start.setChecked(self._existing.get("auto_start", False))
        btns = QHBoxLayout()
        save_btn = QPushButton("💾 Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.setStyleSheet(f"background:{THEME_PRIMARY};padding:7px 20px;")
        cancel_btn.setStyleSheet(f"background:{THEME_BTN_SECONDARY};padding:7px 14px;")
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(form)
        layout.addWidget(self.pw_group)
        layout.addWidget(self.auto_start)
        layout.addLayout(btns)

    def _save(self):
        if not self.host_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Host / IP is required.")
            return
        if self._kind == KIND_LOCAL and not self.remote_host.text().strip():
            QMessageBox.warning(self, "Validation", "Remote host is required for -L.")
            return
        self.accept()

    def get_data(self) -> dict:
        base = {
            "id": self._existing.get("id", str(int(time.time() * 1000))),
            "kind": self._kind,
            "name": self.name_edit.text().strip() or self.host_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "username": self.user_edit.text().strip(),
            "ssh_port": self.ssh_port.value(),
            "identity_file": self.key_edit.text().strip(),
            "use_password": self.pw_group.isChecked(),
            "auto_start": self.auto_start.isChecked(),
        }
        if self._kind == KIND_SOCKS:
            base["local_port"] = self.socks_local_port.value()
        elif self._kind == KIND_LOCAL:
            base["local_bind"] = self.local_bind.text().strip() or "127.0.0.1"
            base["local_port"] = self.local_port.value()
            base["remote_host"] = self.remote_host.text().strip()
            base["remote_port"] = self.remote_port.value()
        else:
            base["remote_bind"] = self.remote_bind.text().strip()
            base["remote_port"] = self.remote_listen_port.value()
            base["local_host"] = self.r_local_host.text().strip() or "127.0.0.1"
            base["local_port"] = self.r_local_port.value()
        return base

    def get_password(self) -> str:
        return self.pw_edit.text() if self.pw_group.isChecked() else ""
