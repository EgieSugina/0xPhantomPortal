import json
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QStyle,
)

from .config import (
    APP_DISPLAY_NAME,
    CONFIG_FILE,
    KIND_SOCKS,
    KIND_LOCAL,
    KIND_REMOTE,
    KEYRING_OK,
    STATUS_CONNECTED,
    STATUS_CONNECTING,
    STATUS_DISABLED,
    STATUS_DISCONNECTED,
    THEME_BG_WIDGET,
    THEME_BG_TABLE,
    THEME_BG_TABLE_ALT,
    THEME_BORDER,
    THEME_HEADER_BG,
    THEME_HEADER_FG,
    THEME_BTN_DISABLED,
    THEME_INPUT_BG,
    THEME_INPUT_BORDER,
    THEME_LOG_BG,
    THEME_LOG_FG,
    THEME_SPLITTER,
    THEME_TITLE,
    THEME_PRIMARY,
    THEME_PRIMARY_DARK,
    THEME_PRIMARY_MUTED,
    THEME_BTN_SECONDARY,
    TUNNEL_KINDS,
    TITLE_FONT_FAMILY,
    load_app_icon,
    resource_dir,
    delete_password,
    load_password,
    normalize_tunnel_record,
    parse_tunnels_json,
    save_password,
)
from .dialogs import TunnelDialog
from .sftp import SFTPPanel
from .worker import TunnelWorker


class MainWindow(QMainWindow):
    _TAB_KINDS = [KIND_SOCKS, KIND_LOCAL, KIND_REMOTE]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setMinimumSize(920, 600)
        self._tunnels: list[dict] = []
        self._workers: dict[str, TunnelWorker] = {}
        self._statuses: dict[str, str] = {}
        self._logs: dict[str, list[str]] = {}
        self._kind_tables: dict[str, QTableWidget] = {}
        self._load_config()
        self._build_ui()
        self._refresh_tables()
        self._auto_start_tunnels()

    def _build_ui(self):
        self._apply_style()
        central = QWidget()
        central.setObjectName("AppCentral")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        logo = QLabel()
        logo_icon = load_app_icon()
        logo_pix = logo_icon.pixmap(22, 22) if not logo_icon.isNull() else QPixmap()
        if not logo_pix.isNull():
            logo.setPixmap(logo_pix)
            logo.setFixedSize(24, 24)
        title = QLabel(APP_DISPLAY_NAME)
        title_font = QFont("Noto Sans", 16)
        if TITLE_FONT_FAMILY:
            title_font = QFont(TITLE_FONT_FAMILY, 18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"letter-spacing:1px;color:{THEME_TITLE};")
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{THEME_BORDER};")
        root.addWidget(sep)

        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)
        root.addWidget(self.main_tabs, 1)

        tunnels_page = QWidget()
        tunnels_layout = QVBoxLayout(tunnels_page)
        tunnels_layout.setContentsMargins(0, 0, 0, 0)
        tunnels_layout.setSpacing(8)
        tunnels_toolbar = QHBoxLayout()
        add_btn = self._btn("＋ Add", THEME_PRIMARY, self._add_tunnel)
        edit_btn = self._btn("✏ Edit", THEME_BTN_SECONDARY, self._edit_tunnel)
        del_btn = self._btn("✕ Delete", "#9b1c3a", self._delete_tunnel)
        exp_btn = self._btn("⭳ Export", THEME_BTN_SECONDARY, self._export_config)
        imp_btn = self._btn("⭱ Import", THEME_BTN_SECONDARY, self._import_config)
        tunnels_toolbar.addWidget(add_btn)
        tunnels_toolbar.addWidget(edit_btn)
        tunnels_toolbar.addWidget(del_btn)
        tunnels_toolbar.addStretch()
        tunnels_toolbar.addWidget(exp_btn)
        tunnels_toolbar.addWidget(imp_btn)
        tunnels_layout.addLayout(tunnels_toolbar)
        splitter = QSplitter(Qt.Vertical)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(lambda _i: self._on_select())
        tab_defs = [
            (KIND_SOCKS, "SOCKS5 (-D)", ["Name", "Host", "User", "SSH", "SOCKS port", "", "Auth", "Status"]),
            (KIND_LOCAL, "Local (-L)", ["Name", "Host", "User", "SSH", "Listen", "→ Target", "Auth", "Status"]),
            (KIND_REMOTE, "Remote (-R)", ["Name", "Host", "User", "SSH", "On server", "→ Local", "Auth", "Status"]),
        ]
        for kind, ttitle, headers in tab_defs:
            wrap = QWidget()
            v = QVBoxLayout(wrap)
            v.setContentsMargins(4, 8, 4, 4)
            tbl = QTableWidget(0, 8)
            tbl.setHorizontalHeaderLabels(headers)
            hh = tbl.horizontalHeader()
            hh.setSectionResizeMode(QHeaderView.Interactive)
            hh.setStretchLastSection(False)
            hh.resizeSection(0, 220)  # Name
            hh.resizeSection(1, 180)  # Host
            hh.resizeSection(2, 120)  # User
            hh.resizeSection(3, 80)   # SSH
            hh.resizeSection(4, 180)
            hh.resizeSection(5, 200)
            hh.resizeSection(6, 110)  # Auth
            hh.resizeSection(7, 140)  # Status
            tbl.setSelectionBehavior(QTableWidget.SelectRows)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            tbl.verticalHeader().setVisible(False)
            tbl.setAlternatingRowColors(True)
            tbl.selectionModel().selectionChanged.connect(self._on_select)
            tbl.doubleClicked.connect(self._toggle_tunnel)
            if kind == KIND_SOCKS:
                tbl.horizontalHeader().hideSection(5)
            self._kind_tables[kind] = tbl
            v.addWidget(tbl)
            self.tabs.addTab(wrap, ttitle)
        splitter.addWidget(self.tabs)

        log_group = QGroupBox("Connection Log")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Monospace", 9))
        self.log_view.setMaximumHeight(170)
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_group)
        splitter.setSizes([360, 170])
        tunnels_layout.addWidget(splitter, 1)

        ab = QHBoxLayout()
        self.connect_btn = self._btn("▶ Connect", "#2ecc71", self._connect_selected)
        self.disconnect_btn = self._btn("■ Disconnect", STATUS_DISCONNECTED, self._disconnect_selected)
        self.connect_all_btn = self._btn("▶▶ All On", "#27ae60", self._connect_all)
        self.disconnect_all_btn = self._btn("■■ All Off", "#9b1c3a", self._disconnect_all)
        ab.addWidget(self.connect_btn)
        ab.addWidget(self.disconnect_btn)
        ab.addStretch()
        ab.addWidget(self.connect_all_btn)
        ab.addWidget(self.disconnect_all_btn)
        tunnels_layout.addLayout(ab)

        self.main_tabs.addTab(tunnels_page, "Port Forward")
        self.sftp_panel = SFTPPanel(self)
        self.main_tabs.addTab(self.sftp_panel, "SFTP")
        self._apply_tab_icons()

        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label)
        self._blink = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _apply_style(self):
        # bg_img = resource_dir() / "img" / "bg.jpg"
        bg_img = None
        bg_css = ""
        # if bg_img and bg_img.exists():
        #     bg_css = (
        #         "QWidget#AppCentral {"
        #         f"background-image: url('{bg_img.as_posix()}');"
        #         "background-position: center;"
        #         "background-repeat: no-repeat;"
        #         "}"
        #     )
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background-color: {THEME_BG_WIDGET};
                color: #e8e0f2;
                font-family: 'Noto Sans', 'DejaVu Sans', sans-serif;
                font-size: 13px;
            }}
            QTableWidget {{ background-color: {THEME_BG_TABLE}; alternate-background-color: {THEME_BG_TABLE_ALT}; gridline-color: {THEME_BORDER}; border: 1px solid {THEME_BORDER}; border-radius: 4px; }}
            QTableWidget::item:selected {{ background-color: {THEME_PRIMARY}; color: #fff; }}
            QHeaderView::section {{ background-color: {THEME_HEADER_BG}; color: {THEME_HEADER_FG}; padding: 6px; border: none; font-weight: 600; }}
            QPushButton {{ border-radius: 4px; padding: 6px 14px; font-weight: 600; border: none; color: #fff; }}
            QPushButton:disabled {{ background-color: {THEME_BTN_DISABLED} !important; color: #9a8aad; }}
            QLineEdit, QSpinBox {{ background-color: {THEME_INPUT_BG}; border: 1px solid {THEME_INPUT_BORDER}; border-radius: 4px; padding: 5px 8px; color: #e8e0f2; }}
            QGroupBox {{ border: 1px solid {THEME_BORDER}; border-radius: 6px; margin-top: 8px; padding-top: 6px; font-weight: 600; color: {THEME_HEADER_FG}; }}
            QTextEdit {{ background-color: {THEME_LOG_BG}; border: none; color: {THEME_LOG_FG}; }}
            QSplitter::handle {{ background-color: {THEME_SPLITTER}; }}
            QTabWidget::pane {{ border: 1px solid {THEME_BORDER}; border-radius: 4px; top: -1px; }}
            QTabBar::tab {{ background: {THEME_HEADER_BG}; color: {THEME_HEADER_FG}; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
            QTabBar::tab:selected {{ background: {THEME_BG_TABLE}; color: #fff; font-weight: 600; }}
            QTabBar::tab:hover {{ color: #f1dbff; }}
            {bg_css}
            """
        )

    def _apply_tab_icons(self):
        style = self.style()
        if style is None:
            return
        self.main_tabs.setTabIcon(0, style.standardIcon(QStyle.SP_ComputerIcon))
        self.main_tabs.setTabIcon(1, style.standardIcon(QStyle.SP_DirOpenIcon))
        tab_icon_map = {
            0: QStyle.SP_BrowserReload,
            1: QStyle.SP_ArrowForward,
            2: QStyle.SP_ArrowBack,
        }
        for i, icon_kind in tab_icon_map.items():
            self.tabs.setTabIcon(i, style.standardIcon(icon_kind))

    @staticmethod
    def _btn(text, color, slot):
        b = QPushButton(text)
        b.setStyleSheet(f"background-color:{color};")
        b.clicked.connect(slot)
        return b

    def _load_config(self):
        if CONFIG_FILE.exists():
            try:
                self._tunnels = json.loads(CONFIG_FILE.read_text())
            except Exception:
                self._tunnels = []
        if not isinstance(self._tunnels, list):
            self._tunnels = []
        for t in self._tunnels:
            t.setdefault("kind", KIND_SOCKS)
            if t["kind"] not in TUNNEL_KINDS:
                t["kind"] = KIND_SOCKS
            self._statuses[t["id"]] = "disconnected"
            self._logs[t["id"]] = []

    def _save_config(self):
        CONFIG_FILE.write_text(json.dumps(self._tunnels, indent=2))

    def _export_config(self):
        path, _flt = QFileDialog.getSaveFileName(self, "Export tunnel configuration", str(Path.home() / "ssh-tunnel-manager-tunnels.json"), "JSON (*.json);;All files (*)")
        if not path:
            return
        Path(path).write_text(json.dumps(self._tunnels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        QMessageBox.information(self, "Export", "Configuration exported.\n\nPasswords are not included.")

    def _import_config(self):
        path, _flt = QFileDialog.getOpenFileName(self, "Import tunnel configuration", str(Path.home()), "JSON (*.json);;All files (*)")
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8")
        raw_list, err = parse_tunnels_json(text)
        if err is not None:
            QMessageBox.critical(self, "Import failed", f"Invalid JSON: {err}")
            return
        normalized = []
        for item in raw_list or []:
            t = normalize_tunnel_record(item) if isinstance(item, dict) else None
            if t:
                normalized.append(t)
        if not normalized:
            QMessageBox.warning(self, "Import", "No valid tunnel entries found.")
            return
        self._apply_import_merge(normalized)

    def _apply_import_merge(self, tunnels: list[dict]) -> None:
        used = {t["id"] for t in self._tunnels}
        added = 0
        for t in tunnels:
            t = dict(t)
            n = 0
            while t["id"] in used:
                n += 1
                t["id"] = f"{int(time.time() * 1000)}_{n}"
            used.add(t["id"])
            self._tunnels.append(t)
            self._statuses[t["id"]] = "disconnected"
            self._logs[t["id"]] = []
            added += 1
        self._save_config()
        self._refresh_tables()
        self.status_label.setText(f"Merged {added} tunnel(s)")

    def _tunnels_for_kind(self, kind: str) -> list[dict]:
        return [t for t in self._tunnels if t.get("kind", KIND_SOCKS) == kind]

    def _current_kind(self) -> str:
        i = self.tabs.currentIndex()
        if 0 <= i < len(self._TAB_KINDS):
            return self._TAB_KINDS[i]
        return KIND_SOCKS

    def _refresh_tables(self):
        for kind in TUNNEL_KINDS:
            self._fill_kind_table(kind, self._kind_tables[kind])

    def _fill_kind_table(self, kind: str, table: QTableWidget):
        rows = self._tunnels_for_kind(kind)
        table.setRowCount(len(rows))
        for row, t in enumerate(rows):
            status = self._statuses.get(t["id"], "disconnected")
            auth = "🔑 Key" if t.get("identity_file") else ("🔒 Password" if t.get("use_password") else "⚠ None")
            col4 = col5 = ""
            if kind == KIND_SOCKS:
                col4 = str(t.get("local_port", 1080))
            elif kind == KIND_LOCAL:
                col4 = f"{(t.get('local_bind') or '127.0.0.1').strip() or '127.0.0.1'}:{t.get('local_port', '')}"
                rh = (t.get("remote_host") or "").strip()
                col5 = f"{rh}:{t.get('remote_port', '')}" if rh else ""
            else:
                rb = (t.get("remote_bind") or "").strip()
                rp = t.get("remote_port", "")
                col4 = f"{rb}:{rp}" if rb else str(rp)
                col5 = f"{(t.get('local_host') or '127.0.0.1').strip() or '127.0.0.1'}:{t.get('local_port', '')}"
            table.setItem(row, 0, QTableWidgetItem(t.get("name", "")))
            table.setItem(row, 1, QTableWidgetItem(t.get("host", "")))
            table.setItem(row, 2, QTableWidgetItem(t.get("username", "")))
            table.setItem(row, 3, QTableWidgetItem(str(t.get("ssh_port", 22))))
            table.setItem(row, 4, QTableWidgetItem(col4))
            table.setItem(row, 5, QTableWidgetItem(col5))
            a = QTableWidgetItem(auth)
            a.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 6, a)
            s = QTableWidgetItem(self._status_label(status))
            s.setForeground(QColor(self._status_color(status)))
            s.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 7, s)

    def _status_label(self, s):
        return {"connected": "● Connected", "connecting": "◌ Connecting…", "disconnected": "○ Disconnected"}.get(s, s)

    def _status_color(self, s):
        return {"connected": STATUS_CONNECTED, "connecting": STATUS_CONNECTING, "disconnected": STATUS_DISCONNECTED}.get(s, STATUS_DISABLED)

    def _selected_tunnel(self) -> dict | None:
        tbl = self._kind_tables[self._current_kind()]
        row = tbl.currentRow()
        lst = self._tunnels_for_kind(self._current_kind())
        return lst[row] if tbl.selectedItems() and 0 <= row < len(lst) else None

    def _on_select(self):
        # During tab construction, currentChanged can fire before log_view exists.
        if not hasattr(self, "log_view"):
            return
        tun = self._selected_tunnel()
        if not tun:
            self.log_view.clear()
            return
        self.log_view.setPlainText("\n".join(self._logs.get(tun["id"], [])[-200:]))

    def _add_tunnel(self):
        dlg = TunnelDialog(self, kind=self._current_kind())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            t = dlg.get_data()
            pw = dlg.get_password()
            if pw:
                save_password(t["id"], pw)
            self._tunnels.append(t)
            self._statuses[t["id"]] = "disconnected"
            self._logs[t["id"]] = []
            self._save_config()
            self._refresh_tables()

    def _edit_tunnel(self):
        cur = self._selected_tunnel()
        if not cur:
            QMessageBox.information(self, "Edit", "Select a tunnel first.")
            return
        dlg = TunnelDialog(self, cur)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            tid = cur["id"]
            if tid in self._workers:
                self._workers[tid].stop()
                del self._workers[tid]
            pw = dlg.get_password()
            if pw:
                save_password(tid, pw)
            elif not dlg.pw_group.isChecked():
                delete_password(tid)
            idx = next(i for i, x in enumerate(self._tunnels) if x["id"] == tid)
            self._tunnels[idx] = dlg.get_data()
            self._save_config()
            self._refresh_tables()

    def _delete_tunnel(self):
        t = self._selected_tunnel()
        if not t:
            QMessageBox.information(self, "Delete", "Select a tunnel first.")
            return
        if QMessageBox.question(self, "Delete", f"Delete tunnel '{t['name']}'?") == QMessageBox.Yes:
            tid = t["id"]
            if tid in self._workers:
                self._workers[tid].stop()
                del self._workers[tid]
            delete_password(tid)
            self._tunnels.remove(t)
            self._save_config()
            self._refresh_tables()

    def _connect(self, tunnel: dict):
        tid = tunnel["id"]
        if tid in self._workers:
            return
        pw = load_password(tid) if tunnel.get("use_password") else ""
        w = TunnelWorker(tunnel, password=pw)
        w.status_changed.connect(self._on_status)
        w.log_message.connect(self._on_log)
        self._workers[tid] = w
        w.start()

    def _disconnect(self, tunnel: dict):
        tid = tunnel["id"]
        if tid in self._workers:
            self._workers[tid].stop()
            del self._workers[tid]
        self._statuses[tid] = "disconnected"
        self._refresh_tables()

    def _connect_selected(self):
        t = self._selected_tunnel()
        if t:
            self._connect(t)

    def _disconnect_selected(self):
        t = self._selected_tunnel()
        if t:
            self._disconnect(t)

    def _toggle_tunnel(self):
        t = self._selected_tunnel()
        if not t:
            return
        self._disconnect(t) if t["id"] in self._workers else self._connect(t)

    def _connect_all(self):
        for t in self._tunnels_for_kind(self._current_kind()):
            self._connect(t)

    def _disconnect_all(self):
        for t in list(self._tunnels_for_kind(self._current_kind())):
            self._disconnect(t)

    def _auto_start_tunnels(self):
        for t in self._tunnels:
            if t.get("auto_start"):
                self._connect(t)

    def _on_status(self, tid: str, status: str):
        self._statuses[tid] = status
        self._refresh_tables()
        n = sum(1 for s in self._statuses.values() if s == "connected")
        self.status_label.setText(f"{n}/{len(self._tunnels)} tunnels connected")

    def _on_log(self, tid: str, message: str):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self._logs.setdefault(tid, []).append(line)
        sel = self._selected_tunnel()
        if sel and sel["id"] == tid:
            self.log_view.append(line)

    def _tick(self):
        self._blink = not self._blink
        for kind in TUNNEL_KINDS:
            table = self._kind_tables[kind]
            for row, t in enumerate(self._tunnels_for_kind(kind)):
                status = self._statuses.get(t["id"], "disconnected")
                item = table.item(row, 7)
                if item and status == "connecting":
                    item.setForeground(QColor(STATUS_CONNECTING if self._blink else THEME_PRIMARY_MUTED))

    def closeEvent(self, event):
        active = list(self._workers)
        if active:
            r = QMessageBox.question(self, "Quit", f"{len(active)} tunnel(s) active. Disconnect and quit?", QMessageBox.Yes | QMessageBox.No)
            if r == QMessageBox.No:
                event.ignore()
                return
        for tid in list(self._workers):
            self._workers[tid].stop()
        if hasattr(self, "sftp_panel"):
            self.sftp_panel._disconnect()
        event.accept()
