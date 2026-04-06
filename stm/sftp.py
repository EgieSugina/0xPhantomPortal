import os
import posixpath
import queue
import socket
import stat
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QStyle,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import PARAMIKO_OK
from .config import (
    STATUS_DISCONNECTED,
    THEME_PRIMARY,
    delete_password,
    load_password,
    load_sftp_accounts,
    save_password,
    save_sftp_accounts,
    sftp_password_id,
)

if PARAMIKO_OK:
    import paramiko


class SFTPDropTree(QTreeWidget):
    paths_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.paths_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class SFTPPanel(QWidget):
    _CONNECT_TIMEOUT_SEC = 8
    _COLOR_FOLDER = QColor("#c77dff")
    _COLOR_FILE = QColor("#d8c8f0")
    _COLOR_TYPE_DIR = QColor("#9a7dff")
    _COLOR_TYPE_FILE = QColor("#7ec8ff")
    _COLOR_STATUS_OK = "#2ecc71"
    _COLOR_STATUS_OFF = "#ff6b6b"
    _COLOR_STATUS_BUSY = "#ffb74d"
    _COLOR_CONNECT_BTN = "#2ecc71"
    _COLOR_DISCONNECT_BTN = "#e74c3c"
    _COLOR_UPLOAD_BTN = "#2d9cdb"
    _COLOR_DOWNLOAD_BTN = "#5b6dee"
    _COLOR_DELETE_BTN = "#e74c3c"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._transport = None
        self._sftp = None
        self._cwd = "."
        self._accounts: list[dict] = []
        self._busy = False
        self._op_queue: queue.Queue = queue.Queue()
        self._op_thread: threading.Thread | None = None
        self._op_name: str | None = None
        self._build_ui()
        self._load_accounts()

    def _build_ui(self):
        root = QVBoxLayout(self)
        conn = QGroupBox("SFTP Connection")
        conn_layout = QVBoxLayout(conn)
        conn_layout.setContentsMargins(12, 12, 12, 12)
        conn_layout.setSpacing(8)
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("example.com")
        self.host_edit.setClearButtonEnabled(True)
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("root")
        self.user_edit.setClearButtonEnabled(True)
        self.account_name_edit = QLineEdit()
        self.account_name_edit.setPlaceholderText("my-prod-server")
        self.account_name_edit.setClearButtonEnabled(True)
        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(220)
        self.account_combo.currentIndexChanged.connect(self._on_account_selected)
        self.save_account_btn = QPushButton("Save Account")
        self.delete_account_btn = QPushButton("Delete Account")
        self.save_account_btn.clicked.connect(self._save_account)
        self.delete_account_btn.clicked.connect(self._delete_account)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(3, 60)
        self.timeout_spin.setValue(self._CONNECT_TIMEOUT_SEC)
        self.timeout_spin.setToolTip("Connection timeout in seconds")
        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(1, 10)
        self.worker_spin.setValue(4)
        self.worker_spin.setToolTip("Parallel upload connections")
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setPlaceholderText("Password (optional if key is used)")
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("~/.ssh/id_rsa (optional)")
        self.key_edit.setClearButtonEnabled(True)
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.test_btn = QPushButton("Test Connection")
        self.connect_btn.setStyleSheet(f"background-color:{self._COLOR_CONNECT_BTN};color:#ffffff;")
        self.disconnect_btn.setStyleSheet(f"background-color:{self._COLOR_DISCONNECT_BTN};color:#ffffff;")
        self.test_btn.setStyleSheet("background-color:#f39c12;color:#ffffff;")
        self.disconnect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.test_btn.clicked.connect(self._test_connection)
        self.conn_status = QLabel("● Disconnected")
        self.conn_status.setStyleSheet(f"color:{self._COLOR_STATUS_OFF};font-weight:700;")

        profile_box = QGroupBox("Profile")
        profile_form = QFormLayout(profile_box)
        profile_form.setLabelAlignment(Qt.AlignRight)
        row_acc = QHBoxLayout()
        row_acc.setSpacing(6)
        row_acc.addWidget(self.account_combo, 1)
        row_acc.addWidget(self.save_account_btn)
        row_acc.addWidget(self.delete_account_btn)
        profile_form.addRow("Account name:", self.account_name_edit)
        profile_form.addRow("Saved accounts:", row_acc)

        server_box = QGroupBox("Server")
        server_form = QFormLayout(server_box)
        server_form.setLabelAlignment(Qt.AlignRight)
        server_form.addRow("Host:", self.host_edit)
        server_form.addRow("Username:", self.user_edit)
        server_form.addRow("Port:", self.port_spin)
        server_form.addRow("Timeout (sec):", self.timeout_spin)

        auth_box = QGroupBox("Authentication")
        auth_form = QFormLayout(auth_box)
        auth_form.setLabelAlignment(Qt.AlignRight)
        auth_form.addRow("Password:", self.pass_edit)
        auth_form.addRow("Identity key:", self.key_edit)
        auth_form.addRow("Max upload workers:", self.worker_spin)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(profile_box, 0, 0)
        grid.addWidget(server_box, 0, 1)
        grid.addWidget(auth_box, 1, 0, 1, 2)
        conn_layout.addLayout(grid)

        row_btn = QHBoxLayout()
        row_btn.setSpacing(8)
        row_btn.addWidget(self.conn_status)
        row_btn.addStretch()
        row_btn.addWidget(self.test_btn)
        row_btn.addWidget(self.connect_btn)
        row_btn.addWidget(self.disconnect_btn)
        conn_layout.addLayout(row_btn)
        root.addWidget(conn)

        nav = QHBoxLayout()
        self.path_edit = QLineEdit(".")
        self.path_edit.returnPressed.connect(self._goto_path)
        self.refresh_btn = QPushButton("Refresh")
        self.up_btn = QPushButton("Up")
        self.mkdir_btn = QPushButton("New Folder")
        self.refresh_btn.clicked.connect(self._refresh)
        self.up_btn.clicked.connect(self._up_dir)
        self.mkdir_btn.clicked.connect(self._mkdir)
        nav.addWidget(QLabel("Remote path:"))
        nav.addWidget(self.path_edit)
        nav.addWidget(self.up_btn)
        nav.addWidget(self.refresh_btn)
        nav.addWidget(self.mkdir_btn)
        root.addLayout(nav)

        self.tree = SFTPDropTree()
        self.tree.setHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.tree.header().setStretchLastSection(False)
        self.tree.setColumnWidth(0, 380)  # Name
        self.tree.setColumnWidth(1, 90)   # Type
        self.tree.setColumnWidth(2, 110)  # Size
        self.tree.setColumnWidth(3, 170)  # Modified
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setStyleSheet(
            "QTreeWidget::item{padding:2px 0;}"
            "QTreeWidget::item:selected{background:#7300ff;color:#ffffff;}"
        )
        self.tree.itemDoubleClicked.connect(self._open_item)
        self.tree.paths_dropped.connect(self._upload_local_paths)
        root.addWidget(self.tree, 1)

        actions = QHBoxLayout()
        self.upload_btn = QPushButton("Upload Files/Folder")
        self.download_btn = QPushButton("Download Selected")
        self.delete_btn = QPushButton("Delete Selected")
        self.upload_btn.setStyleSheet(f"background-color:{self._COLOR_UPLOAD_BTN};color:#ffffff;")
        self.download_btn.setStyleSheet(f"background-color:{self._COLOR_DOWNLOAD_BTN};color:#ffffff;")
        self.delete_btn.setStyleSheet(f"background-color:{self._COLOR_DELETE_BTN};color:#ffffff;")
        self.upload_btn.clicked.connect(self._upload_pick)
        self.download_btn.clicked.connect(self._download_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        actions.addWidget(self.upload_btn)
        actions.addWidget(self.download_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch()
        root.addLayout(actions)

        self.drop_hint = QLabel("Tip: You can drag and drop file/folder here to upload.")
        self.drop_hint.setStyleSheet("color:#9fc3ff;font-style:italic;")
        root.addWidget(self.drop_hint)

        self.progress_label = QLabel("")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        root.addWidget(self.progress_label)
        root.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        root.addWidget(self.log)
        style = QApplication.style()
        self._folder_icon = style.standardIcon(QStyle.SP_DirIcon) if style else QIcon()
        self._file_icon = style.standardIcon(QStyle.SP_FileIcon) if style else QIcon()
        self._apply_button_icons()
        if not PARAMIKO_OK:
            self._append("❌ paramiko not installed. Run: pip install paramiko")
            # Keep button clickable so user gets explicit error dialog.

    def _apply_button_icons(self):
        def set_theme_icon(button: QPushButton, icon_name: str):
            icon = QIcon.fromTheme(icon_name)
            if not icon.isNull():
                button.setIcon(icon)

        set_theme_icon(self.connect_btn, "network-connect")
        set_theme_icon(self.disconnect_btn, "network-disconnect")
        set_theme_icon(self.test_btn, "network-wired")
        set_theme_icon(self.save_account_btn, "document-save")
        set_theme_icon(self.delete_account_btn, "edit-delete")
        set_theme_icon(self.refresh_btn, "view-refresh")
        set_theme_icon(self.up_btn, "go-up")
        set_theme_icon(self.mkdir_btn, "folder-new")
        set_theme_icon(self.upload_btn, "go-up")
        set_theme_icon(self.download_btn, "go-down")
        set_theme_icon(self.delete_btn, "edit-delete")

    def _append(self, msg: str):
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self._yield_ui()

    def _start_progress(self, label: str, total: int):
        total = max(total, 1)
        self.progress_label.setText(label)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._yield_ui()

    def _set_progress(self, value: int):
        if not self.progress.isVisible():
            return
        self.progress.setValue(max(0, min(value, self.progress.maximum())))
        self._yield_ui()

    def _set_progress_total(self, total: int, label: str | None = None):
        total = max(total, 1)
        if label:
            self.progress_label.setText(label)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._yield_ui()

    def _end_progress(self):
        self.progress.setVisible(False)
        self.progress_label.setText("")
        self._yield_ui()

    def _start_background_job(self, op_name: str, target, *args):
        if self._op_thread and self._op_thread.is_alive():
            self._append("⚠ Another operation is still running.")
            return False
        self._op_name = op_name
        self._set_busy(True)
        self._start_progress(f"{op_name.capitalize()} in progress...", 1)
        self._op_thread = threading.Thread(target=target, args=args, daemon=True)
        self._op_thread.start()
        self._poll_background_job()
        return True

    def _poll_background_job(self):
        while True:
            try:
                event = self._op_queue.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "log":
                self._append(event[1])
            elif kind == "progress_total":
                _, total, label = event
                self._set_progress_total(total, label)
            elif kind == "progress":
                _, done = event
                self._set_progress(done)
            elif kind == "error":
                self._append(f"❌ {event[1]}")
            elif kind == "done":
                _, ok, msg = event
                if msg:
                    self._append(msg)
                if ok and self._sftp is not None:
                    self._refresh()
                self._end_progress()
                self._set_busy(False)
                self._op_name = None
                self._op_thread = None
                return
        if self._op_thread and self._op_thread.is_alive():
            QTimer.singleShot(40, self._poll_background_job)
            return
        if self._op_name is not None:
            # Safety cleanup if thread exits unexpectedly without done event.
            self._end_progress()
            self._set_busy(False)
            self._op_name = None
            self._op_thread = None

    @staticmethod
    def _open_client_from_params(params):
        timeout = int(params.get("timeout", 8) or 8)
        sock = socket.create_connection(
            (params["host"], params["port"]),
            timeout=timeout,
        )
        transport = paramiko.Transport(sock)
        transport.banner_timeout = timeout
        transport.auth_timeout = timeout
        password = params.get("password") or None
        pkey = None
        if params.get("key_file"):
            pkey = paramiko.RSAKey.from_private_key_file(
                os.path.expanduser(params["key_file"]), password=password
            )
            password = None
        transport.connect(username=params["username"], password=password, pkey=pkey)
        return transport, paramiko.SFTPClient.from_transport(transport)

    @staticmethod
    def _yield_ui():
        app = QApplication.instance()
        if app:
            app.processEvents()

    def _set_busy(self, busy: bool):
        self._busy = busy
        if busy:
            self.conn_status.setText("● Busy")
            self.conn_status.setStyleSheet(f"color:{self._COLOR_STATUS_BUSY};font-weight:700;")
        elif self._sftp is not None:
            self.conn_status.setText("● Connected")
            self.conn_status.setStyleSheet(f"color:{self._COLOR_STATUS_OK};font-weight:700;")
        else:
            self.conn_status.setText("● Disconnected")
            self.conn_status.setStyleSheet(f"color:{self._COLOR_STATUS_OFF};font-weight:700;")
        self.connect_btn.setEnabled(not busy and PARAMIKO_OK and self._sftp is None)
        self.disconnect_btn.setEnabled(not busy and self._sftp is not None)
        self.test_btn.setEnabled(not busy and PARAMIKO_OK)
        self.timeout_spin.setEnabled(not busy)
        self.worker_spin.setEnabled(not busy)
        self.upload_btn.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)
        self.delete_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.up_btn.setEnabled(not busy)
        self.mkdir_btn.setEnabled(not busy)

    def _load_accounts(self):
        self._accounts = load_sftp_accounts()
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        self.account_combo.addItem("(new account)")
        for acc in self._accounts:
            self.account_combo.addItem(acc["name"])
        self.account_combo.setCurrentIndex(0)
        self.account_combo.blockSignals(False)

    def _on_account_selected(self, idx: int):
        if idx <= 0:
            return
        name = self.account_combo.currentText().strip()
        acc = next((a for a in self._accounts if a["name"] == name), None)
        if not acc:
            return
        self.account_name_edit.setText(acc["name"])
        self.host_edit.setText(acc.get("host", ""))
        self.user_edit.setText(acc.get("username", ""))
        self.port_spin.setValue(int(acc.get("port", 22) or 22))
        self.key_edit.setText(acc.get("key_file", ""))
        self.pass_edit.setText(load_password(sftp_password_id(acc["name"])))

    def _save_account(self):
        name = self.account_name_edit.text().strip()
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "SFTP", "Account name is required.")
            return
        if not host or not user:
            QMessageBox.warning(self, "SFTP", "Host and Username are required.")
            return
        rec = {
            "name": name,
            "host": host,
            "username": user,
            "port": int(self.port_spin.value()),
            "key_file": self.key_edit.text().strip(),
        }
        found = False
        for i, acc in enumerate(self._accounts):
            if acc["name"] == name:
                self._accounts[i] = rec
                found = True
                break
        if not found:
            self._accounts.append(rec)
        save_sftp_accounts(self._accounts)
        pw = self.pass_edit.text()
        if pw:
            save_password(sftp_password_id(name), pw)
        else:
            delete_password(sftp_password_id(name))
        self._load_accounts()
        self.account_combo.setCurrentText(name)
        self._append(f"💾 Saved account: {name}")

    def _delete_account(self):
        name = self.account_name_edit.text().strip() or self.account_combo.currentText().strip()
        if not name or name == "(new account)":
            return
        if QMessageBox.question(self, "Delete account", f"Delete saved account '{name}'?") != QMessageBox.Yes:
            return
        self._accounts = [a for a in self._accounts if a["name"] != name]
        save_sftp_accounts(self._accounts)
        delete_password(sftp_password_id(name))
        self._load_accounts()
        self.account_name_edit.clear()
        self._append(f"🗑 Deleted account: {name}")

    def _ensure_connected(self):
        if self._sftp is None:
            QMessageBox.information(self, "SFTP", "Connect first.")
            return False
        return True

    def _connect(self):
        if self._busy:
            return
        if not PARAMIKO_OK:
            QMessageBox.critical(
                self,
                "SFTP unavailable",
                "Python package 'paramiko' is not installed.\n\n"
                "Install it in your active environment:\n"
                "pip install paramiko",
            )
            return
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        if not host or not user:
            QMessageBox.warning(self, "SFTP", "Host and Username are required.")
            return
        timeout = int(self.timeout_spin.value())
        try:
            self._set_busy(True)
            self._append(f"🔌 Connecting to {user}@{host}:{self.port_spin.value()} ...")
            self._disconnect()
            self._append(f"⏱ Connection timeout: {timeout}s")
            sock = socket.create_connection(
                (host, int(self.port_spin.value())),
                timeout=timeout,
            )
            self._transport = paramiko.Transport(sock)
            # Reduce the chance of long hangs on auth/banner failures.
            self._transport.banner_timeout = timeout
            self._transport.auth_timeout = timeout
            key_file = self.key_edit.text().strip()
            password = self.pass_edit.text()
            pkey = None
            if key_file:
                pkey = paramiko.RSAKey.from_private_key_file(
                    os.path.expanduser(key_file), password=password or None
                )
                password = None
            self._transport.connect(username=user, password=password or None, pkey=pkey)
            self._sftp = paramiko.SFTPClient.from_transport(self._transport)
            self._cwd = self._sftp.normalize(".")
            self.path_edit.setText(self._cwd)
            self._append(f"✅ Connected to {user}@{host}:{self.port_spin.value()}")
            self._refresh()
        except socket.timeout:
            self._append("❌ Connect timeout. Host unreachable or SSH service too slow.")
            self._disconnect()
        except TimeoutError:
            self._append("❌ Connect timeout. Host unreachable or SSH service too slow.")
            self._disconnect()
        except paramiko.ssh_exception.SSHException as e:
            msg = str(e)
            if "Error reading SSH protocol banner" in msg:
                self._append(
                    "❌ SSH banner timeout. Check host/port and ensure target is an SSH server."
                )
            else:
                self._append(f"❌ SSH error: {msg}")
            self._disconnect()
        except Exception as e:
            self._append(f"❌ Connect failed: {e}")
            self._disconnect()
        finally:
            self._set_busy(False)

    def _test_connection(self):
        if self._busy:
            return
        if not PARAMIKO_OK:
            QMessageBox.critical(self, "SFTP unavailable", "paramiko is not installed.")
            return
        host = self.host_edit.text().strip()
        port = int(self.port_spin.value())
        if not host:
            QMessageBox.warning(self, "SFTP", "Host is required.")
            return
        timeout = int(self.timeout_spin.value())
        transport = None
        sock = None
        try:
            self._set_busy(True)
            self._append(f"🧪 Testing SSH endpoint {host}:{port} ...")
            sock = socket.create_connection((host, port), timeout=timeout)
            transport = paramiko.Transport(sock)
            transport.banner_timeout = timeout
            transport.auth_timeout = timeout
            transport.start_client(timeout=timeout)
            self._append(f"✅ SSH endpoint reachable: {host}:{port}")
        except socket.timeout:
            self._append("❌ Test failed: timeout")
        except TimeoutError:
            self._append("❌ Test failed: timeout")
        except paramiko.ssh_exception.SSHException as e:
            msg = str(e)
            if "Error reading SSH protocol banner" in msg:
                self._append("❌ Test failed: host reachable but not responding as SSH server.")
            else:
                self._append(f"❌ Test failed: SSH error ({msg})")
        except Exception as e:
            self._append(f"❌ Test failed: {e}")
        finally:
            try:
                if transport:
                    transport.close()
            except Exception:
                pass
            try:
                if sock:
                    sock.close()
            except Exception:
                pass
            self._set_busy(False)

    def _disconnect(self):
        if self._busy and self._sftp is None and self._transport is None:
            return
        try:
            if self._sftp:
                self._sftp.close()
        except Exception:
            pass
        try:
            if self._transport:
                self._transport.close()
        except Exception:
            pass
        self._sftp = None
        self._transport = None
        self._set_busy(False)

    def _goto_path(self):
        if not self._ensure_connected():
            return
        try:
            self._cwd = self._sftp.normalize(self.path_edit.text().strip() or ".")
            self.path_edit.setText(self._cwd)
            self._refresh()
        except Exception as e:
            self._append(f"❌ Cannot open path: {e}")

    def _up_dir(self):
        if not self._ensure_connected():
            return
        self.path_edit.setText(posixpath.dirname(self._cwd.rstrip("/")) or "/")
        self._goto_path()

    def _refresh(self):
        if not self._ensure_connected():
            return
        self.tree.clear()
        try:
            entries = sorted(self._sftp.listdir_attr(self._cwd), key=lambda x: x.filename.lower())
            for a in entries:
                if a.filename in (".", ".."):
                    continue
                is_dir = stat.S_ISDIR(a.st_mode)
                item = QTreeWidgetItem([
                    a.filename,
                    "dir" if is_dir else "file",
                    "" if is_dir else str(a.st_size),
                    datetime.fromtimestamp(a.st_mtime).strftime("%Y-%m-%d %H:%M"),
                ])
                item.setData(0, Qt.UserRole, "dir" if is_dir else "file")
                item.setIcon(0, self._folder_icon if is_dir else self._file_icon)
                if is_dir:
                    item.setForeground(0, QBrush(self._COLOR_FOLDER))
                    item.setForeground(1, QBrush(self._COLOR_TYPE_DIR))
                else:
                    item.setForeground(0, QBrush(self._COLOR_FILE))
                    item.setForeground(1, QBrush(self._COLOR_TYPE_FILE))
                self.tree.addTopLevelItem(item)
                self._yield_ui()
        except Exception as e:
            self._append(f"❌ Refresh failed: {e}")

    def _mkdir(self):
        if not self._ensure_connected():
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            try:
                self._sftp.mkdir(posixpath.join(self._cwd, name.strip()))
                self._refresh()
            except Exception as e:
                self._append(f"❌ mkdir failed: {e}")

    def _open_item(self, item: QTreeWidgetItem):
        if item.data(0, Qt.UserRole) == "dir":
            self._cwd = posixpath.join(self._cwd, item.text(0))
            self.path_edit.setText(self._cwd)
            self._refresh()

    def _upload_pick(self):
        if not self._ensure_connected():
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Upload files")
        folder = QFileDialog.getExistingDirectory(self, "Upload folder (optional)")
        paths = list(files)
        if folder:
            paths.append(folder)
        if paths:
            self._upload_local_paths(paths)

    def _upload_local_paths(self, paths):
        if not self._ensure_connected():
            return
        self._append(f"⬆ Upload queue: {len(paths)} item(s)")
        params = self._sftp_connection_params()
        params["cwd"] = self._cwd
        self._start_background_job("upload", self._run_upload_job, params, list(paths), int(self.worker_spin.value()))

    def _collect_upload_tasks(self, paths):
        dirs_to_create: set[str] = set()
        file_tasks: list[tuple[str, str]] = []
        for p in paths:
            p = os.path.abspath(p)
            if os.path.isdir(p):
                remote_root = posixpath.join(self._cwd, os.path.basename(p))
                dirs_to_create.add(remote_root)
                for root, dirs, files in os.walk(p):
                    rel = os.path.relpath(root, p).replace("\\", "/")
                    remote_base = remote_root if rel == "." else posixpath.join(remote_root, rel)
                    dirs_to_create.add(remote_base)
                    for d in dirs:
                        dirs_to_create.add(posixpath.join(remote_base, d))
                    for f in files:
                        file_tasks.append((os.path.join(root, f), posixpath.join(remote_base, f)))
            elif os.path.isfile(p):
                file_tasks.append((p, posixpath.join(self._cwd, os.path.basename(p))))
        return dirs_to_create, file_tasks

    def _sftp_connection_params(self):
        return {
            "host": self.host_edit.text().strip(),
            "port": int(self.port_spin.value()),
            "username": self.user_edit.text().strip(),
            "password": self.pass_edit.text(),
            "key_file": self.key_edit.text().strip(),
            "timeout": int(self.timeout_spin.value()),
        }

    def _upload_bucket(self, params, tasks):
        transport = None
        sftp = None
        try:
            transport, sftp = self._open_client_from_params(params)
            results = []
            for local_path, remote_path in tasks:
                try:
                    sftp.put(local_path, remote_path)
                    results.append((True, local_path, remote_path, ""))
                except Exception as e:
                    results.append((False, local_path, remote_path, str(e)))
            return results
        finally:
            try:
                if sftp:
                    sftp.close()
            except Exception:
                pass
            try:
                if transport:
                    transport.close()
            except Exception:
                pass

    def _upload_files_parallel(self, params, file_tasks, workers):
        total = len(file_tasks)
        if total == 0:
            return
        max_workers = min(max(int(workers), 1), 10, total)
        self._op_queue.put(("log", f"🚀 Uploading {total} file(s) with {max_workers} worker(s)"))
        self._op_queue.put(("progress_total", total, "Uploading files..."))
        if max_workers <= 1:
            transport = None
            sftp = None
            done = 0
            for local_path, remote_path in file_tasks:
                try:
                    if sftp is None:
                        transport, sftp = self._open_client_from_params(params)
                    sftp.put(local_path, remote_path)
                    self._op_queue.put(("log", f"✅ Uploaded: {remote_path}"))
                except Exception as e:
                    self._op_queue.put(("log", f"❌ Upload failed: {local_path} ({e})"))
                done += 1
                self._op_queue.put(("progress", done))
            try:
                if sftp:
                    sftp.close()
            except Exception:
                pass
            try:
                if transport:
                    transport.close()
            except Exception:
                pass
            return

        buckets = [[] for _ in range(max_workers)]
        for i, task in enumerate(file_tasks):
            buckets[i % max_workers].append(task)
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(self._upload_bucket, params, b) for b in buckets if b]
            for fut in as_completed(futures):
                for ok, local_path, remote_path, err in fut.result():
                    if ok:
                        self._op_queue.put(("log", f"✅ Uploaded: {remote_path}"))
                    else:
                        self._op_queue.put(("log", f"❌ Upload failed: {local_path} ({err})"))
                    done += 1
                    self._op_queue.put(("progress", done))
                    if done % 10 == 0 or done == total:
                        self._op_queue.put(("log", f"📈 Upload progress: {done}/{total}"))

    def _run_upload_job(self, params, paths, workers):
        try:
            dirs_to_create, file_tasks = self._collect_upload_tasks(paths)
            self._op_queue.put(("log", f"📦 Prepared {len(file_tasks)} file task(s)"))
            transport = None
            sftp = None
            try:
                transport, sftp = self._open_client_from_params(params)
                for remote_dir in sorted(dirs_to_create, key=lambda p: p.count("/")):
                    try:
                        sftp.mkdir(remote_dir)
                        self._op_queue.put(("log", f"📁 Created remote dir: {remote_dir}"))
                    except Exception:
                        pass
            finally:
                try:
                    if sftp:
                        sftp.close()
                except Exception:
                    pass
                try:
                    if transport:
                        transport.close()
                except Exception:
                    pass
            if file_tasks:
                self._upload_files_parallel(params, file_tasks, workers)
            self._op_queue.put(("done", True, "✔ Upload finished"))
        except Exception as e:
            self._op_queue.put(("error", f"Upload failed: {e}"))
            self._op_queue.put(("done", False, ""))

    def _download_selected(self):
        if not self._ensure_connected():
            return
        items = self.tree.selectedItems()
        if not items:
            return
        target = QFileDialog.getExistingDirectory(self, "Choose local destination")
        if not target:
            return
        self._set_busy(True)
        self._append(f"⬇ Download queue: {len(items)} item(s) to {target}")
        try:
            for item in items:
                name = item.text(0)
                rp = posixpath.join(self._cwd, name)
                lp = os.path.join(target, name)
                if item.data(0, Qt.UserRole) == "dir":
                    self._append(f"⬇ Download folder: {rp}")
                    self._download_dir(rp, lp)
                    self._append(f"✅ Downloaded folder: {rp}")
                else:
                    self._append(f"⬇ Download file: {rp} -> {lp}")
                    self._sftp.get(rp, lp)
                    self._append(f"✅ Downloaded file: {rp}")
                self._yield_ui()
            self._append("✔ Download finished")
        finally:
            self._set_busy(False)

    def _download_dir(self, remote_dir: str, local_dir: str):
        os.makedirs(local_dir, exist_ok=True)
        for a in self._sftp.listdir_attr(remote_dir):
            rp = posixpath.join(remote_dir, a.filename)
            lp = os.path.join(local_dir, a.filename)
            if stat.S_ISDIR(a.st_mode):
                self._download_dir(rp, lp)
            else:
                self._append(f"⬇ Download file: {rp} -> {lp}")
                self._sftp.get(rp, lp)
                self._yield_ui()

    def _delete_selected(self):
        if not self._ensure_connected():
            return
        items = self.tree.selectedItems()
        if not items:
            return
        names = [i.text(0) for i in items]
        preview = "\n".join(f"- {n}" for n in names[:8])
        if len(names) > 8:
            preview += f"\n... and {len(names) - 8} more"
        confirm_text = (
            f"Delete {len(items)} selected item(s)?\n\n"
            "This action cannot be undone.\n\n"
            f"{preview}"
        )
        if QMessageBox.question(self, "Confirm Delete", confirm_text) != QMessageBox.Yes:
            return
        delete_targets = [(posixpath.join(self._cwd, i.text(0)), i.data(0, Qt.UserRole) == "dir") for i in items]
        self._append(f"🗑 Delete queue: {len(delete_targets)} item(s)")
        params = self._sftp_connection_params()
        self._start_background_job("delete", self._run_delete_job, params, delete_targets)

    @staticmethod
    def _remove_remote_dir(sftp, remote_dir: str):
        for a in sftp.listdir_attr(remote_dir):
            p = posixpath.join(remote_dir, a.filename)
            if stat.S_ISDIR(a.st_mode):
                SFTPPanel._remove_remote_dir(sftp, p)
            else:
                sftp.remove(p)
        sftp.rmdir(remote_dir)

    def _run_delete_job(self, params, delete_targets):
        transport = None
        sftp = None
        try:
            self._op_queue.put(("progress_total", len(delete_targets), "Deleting selected items..."))
            transport, sftp = self._open_client_from_params(params)
            done = 0
            for remote_path, is_dir in delete_targets:
                if is_dir:
                    self._remove_remote_dir(sftp, remote_path)
                else:
                    sftp.remove(remote_path)
                done += 1
                self._op_queue.put(("log", f"🗑 Deleted: {remote_path}"))
                self._op_queue.put(("progress", done))
            self._op_queue.put(("done", True, "✔ Delete finished"))
        except Exception as e:
            self._op_queue.put(("error", f"Delete failed: {e}"))
            self._op_queue.put(("done", False, ""))
        finally:
            try:
                if sftp:
                    sftp.close()
            except Exception:
                pass
            try:
                if transport:
                    transport.close()
            except Exception:
                pass
