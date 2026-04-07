import os
import posixpath
import queue
import socket
import stat
import threading
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import PARAMIKO_OK
from ..config import (
    delete_password,
    load_password,
    load_sftp_accounts,
    save_password,
    save_sftp_accounts,
    sftp_password_id,
)
from .jobs import collect_upload_tasks, open_client_from_params, run_delete_job, run_upload_job
from .widgets import SFTPDropTree

if PARAMIKO_OK:
    import paramiko


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
    _PROFILE_GRID_MIN_COLUMNS = 1
    _PROFILE_GRID_MAX_COLUMNS = 3
    _PROFILE_CARD_MIN_WIDTH = 260
    _PROFILE_CARD_ICON_NAMES = (
        "network-server",
        "folder-remote",
        "drive-harddisk",
        "security-high",
    )

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
        self._file_progress_rows: dict[str, tuple[QTreeWidgetItem, QProgressBar]] = {}
        # self._pulse_on = True
        # self._cursor_on = True
        self._connected_profile_name: str | None = None
        self._build_ui()
        self._load_accounts()
        # self._visual_timer = QTimer(self)
        # self._visual_timer.timeout.connect(self._tick_visuals)
        # self._visual_timer.start(650)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        # Shared form widgets (used in Add/Edit and connect flow)
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("example.com")
        self.host_edit.setClearButtonEnabled(True)
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("root")
        self.user_edit.setClearButtonEnabled(True)
        self.account_name_edit = QLineEdit()
        self.account_name_edit.setPlaceholderText("my-prod-server")
        self.account_name_edit.setClearButtonEnabled(True)
        self.save_account_btn = QPushButton("SAVE_PROFILE")
        self.delete_account_btn = QPushButton("DELETE_PROFILE")
        self.save_account_btn.clicked.connect(self._save_account)
        self.delete_account_btn.clicked.connect(lambda: self._delete_account())
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
        self.pass_edit.setPlaceholderText("PASSWORD_OPTIONAL_IF_KEY_IS_USED")
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("~/.ssh/id_rsa_OPTIONAL")
        self.key_edit.setClearButtonEnabled(True)
        self.connect_btn = QPushButton("CONNECT")
        self.disconnect_btn = QPushButton("DISCONNECT")
        self.test_btn = QPushButton("TEST_ENDPOINT")
        self.add_profile_btn = QPushButton("ADD SFTP")
        self.back_profiles_btn = QPushButton("BACK_TO_PROFILES")
        self.cancel_form_btn = QPushButton("CANCEL")
        self.form_save_btn = QPushButton("SAVE_PROFILE")
        self.ws_disconnect_btn = QPushButton("DISCONNECT")
        self.connect_btn.setStyleSheet(f"background-color:{self._COLOR_CONNECT_BTN};color:#ffffff;")
        self.disconnect_btn.setStyleSheet(f"background-color:{self._COLOR_DISCONNECT_BTN};color:#ffffff;")
        self.ws_disconnect_btn.setStyleSheet(f"background-color:{self._COLOR_DISCONNECT_BTN};color:#ffffff;")
        self.test_btn.setStyleSheet("background-color:#f39c12;color:#ffffff;")
        self.disconnect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(lambda: self._disconnect(show_profiles=False))
        self.ws_disconnect_btn.clicked.connect(lambda: self._disconnect(show_profiles=True))
        self.test_btn.clicked.connect(self._test_connection)
        self.add_profile_btn.clicked.connect(self._open_add_form)
        self.back_profiles_btn.clicked.connect(self._show_profiles_page)
        self.cancel_form_btn.clicked.connect(self._show_profiles_page)
        self.form_save_btn.clicked.connect(self._save_account)
        self.conn_status = QLabel("● DISCONNECTED")
        self.conn_status.setStyleSheet(f"color:{self._COLOR_STATUS_OFF};font-weight:700;")
        self.active_profile_label = QLabel("CONNECTED TO: NONE")

        # Page 1: Profiles grid
        self.page_profiles = QWidget()
        profiles_layout = QVBoxLayout(self.page_profiles)
        profiles_layout.setContentsMargins(6, 6, 6, 6)
        profiles_top = QHBoxLayout()
        profiles_title = QLabel("SFTP PROFILES")
        profiles_title.setStyleSheet(
            "font-size:32px;font-weight:700;color:#ece9f7;letter-spacing:-0.5px;"
        )
        # profiles_sub = QLabel(
        #     "Secure File Transfer Management Protocol Cluster. Encrypted tunneling active."
        # )
        # profiles_sub.setWordWrap(True)
        # profiles_sub.setStyleSheet("font-size:13px;color:#aca9b6;max-width:420px;")
        title_col = QVBoxLayout()
        title_col.addWidget(profiles_title)
        # title_col.addWidget(profiles_sub)
        profiles_top.addLayout(title_col)
        profiles_top.addStretch()
        profiles_top.addWidget(self.add_profile_btn)
        profiles_layout.addLayout(profiles_top)

        self.profile_grid_widget = QWidget()
        self.profile_grid_layout = QGridLayout(self.profile_grid_widget)
        self.profile_grid_layout.setHorizontalSpacing(10)
        self.profile_grid_layout.setVerticalSpacing(10)
        self.profile_grid_layout.setContentsMargins(0, 0, 0, 0)
        profile_scroll = QScrollArea()
        profile_scroll.setWidgetResizable(True)
        profile_scroll.setWidget(self.profile_grid_widget)
        profiles_layout.addWidget(profile_scroll, 1)

        stats_wrap = QWidget()
        stats_layout = QGridLayout(stats_wrap)
        stats_layout.setContentsMargins(0, 16, 0, 0)
        stats_layout.setHorizontalSpacing(16)
        stats_layout.setVerticalSpacing(0)

        def _stat_cell(title: str, value: str, accent: str) -> tuple[QFrame, QLabel]:
            box = QFrame()
            box.setStyleSheet("background:#191924;border-radius:2px;padding:0px;")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(12, 10, 12, 10)
            t = QLabel(title)
            t.setStyleSheet(
                "font-size:10px;color:#767480;font-weight:600;"
                "letter-spacing:1px;text-transform:uppercase;border:none;background:transparent;"
            )
            v = QLabel(value)
            v.setStyleSheet(
                f"font-size:22px;font-weight:700;color:{accent};border:none;background:transparent;"
            )
            bl.addWidget(t)
            bl.addWidget(v)
            return box, v

        # self._stat_active_box, self._stat_active_val = _stat_cell("Active Tunnels", "00", "#00fd93")
        # self._stat_total_box, self._stat_total_val = _stat_cell("Total Profiles", "00", "#aca3ff")
        # self._stat_latency_box, self._stat_latency_val = _stat_cell("Latency Avg", "—", "#ece9f7")
        # self._stat_data_box, self._stat_data_val = _stat_cell("Data Shifted", "—", "#ece9f7")
        # for c, w in enumerate(
        #     (
        #         self._stat_active_box,
        #         self._stat_total_box,
        #         self._stat_latency_box,
        #         self._stat_data_box,
        #     )
        # ):
            stats_layout.addWidget(w, 0, c)

        profiles_layout.addWidget(stats_wrap)
        # self._profile_active_pulse_labels: list[QLabel] = []
        self.pages.addWidget(self.page_profiles)

        # Page 2: Add/Edit profile form
        self.page_form = QWidget()
        form_page_layout = QVBoxLayout(self.page_form)
        form_page_layout.setContentsMargins(6, 6, 6, 6)
        form_header = QHBoxLayout()
        form_title = QLabel("SFTP PROFILE CONFIGURATION")
        form_title.setStyleSheet("font-size:18px;font-weight:800;letter-spacing:1px;color:#ece9f7;")
        form_header.addWidget(form_title)
        form_header.addStretch()
        form_header.addWidget(self.cancel_form_btn)
        form_header.addWidget(self.form_save_btn)
        form_page_layout.addLayout(form_header)

        profile_box = QGroupBox("PROFILE")
        profile_form = QFormLayout(profile_box)
        profile_form.setLabelAlignment(Qt.AlignRight)
        profile_form.addRow("PROFILE_NAME:", self.account_name_edit)

        server_box = QGroupBox("SERVER")
        server_form = QFormLayout(server_box)
        server_form.setLabelAlignment(Qt.AlignRight)
        server_form.addRow("HOST_IP:", self.host_edit)
        server_form.addRow("USERNAME:", self.user_edit)
        server_form.addRow("SSH_PORT:", self.port_spin)
        server_form.addRow("TIMEOUT_SEC:", self.timeout_spin)

        auth_box = QGroupBox("AUTHENTICATION")
        auth_form = QFormLayout(auth_box)
        auth_form.setLabelAlignment(Qt.AlignRight)
        auth_form.addRow("PASSWORD_AUTH:", self.pass_edit)
        auth_form.addRow("IDENTITY_KEY:", self.key_edit)
        auth_form.addRow("MAX_UPLOAD_WORKERS:", self.worker_spin)

        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(10)
        form_grid.setVerticalSpacing(8)
        form_grid.addWidget(profile_box, 0, 0)
        form_grid.addWidget(server_box, 0, 1)
        form_grid.addWidget(auth_box, 1, 0, 1, 2)
        form_page_layout.addLayout(form_grid)

        row_btn = QHBoxLayout()
        row_btn.setSpacing(8)
        row_btn.addWidget(self.conn_status)
        row_btn.addStretch()
        row_btn.addWidget(self.test_btn)
        row_btn.addWidget(self.connect_btn)
        row_btn.addWidget(self.disconnect_btn)
        form_page_layout.addLayout(row_btn)
        self.pages.addWidget(self.page_form)

        # Page 3: Connected workspace
        self.page_workspace = QWidget()
        ws_layout = QVBoxLayout(self.page_workspace)
        ws_layout.setContentsMargins(6, 6, 6, 6)
        ws_header = QHBoxLayout()
        self.active_profile_label.setStyleSheet("font-size:12px;color:#00fd93;font-weight:700;")
        ws_title = QLabel("SFTP_EXPLORER")
        ws_title.setStyleSheet("font-size:20px;font-weight:800;letter-spacing:1px;color:#ece9f7;")
        ws_title_col = QVBoxLayout()
        ws_title_col.addWidget(ws_title)
        ws_status_row = QHBoxLayout()
        self.ws_status_dot = QLabel("●")
        self.ws_status_dot.setStyleSheet("color:#00fd93;font-size:11px;")
        ws_status_row.addWidget(self.ws_status_dot)
        ws_status_row.addWidget(self.active_profile_label)
        ws_status_row.addStretch()
        ws_title_col.addLayout(ws_status_row)
        ws_header.addLayout(ws_title_col)
        ws_header.addStretch()
        ws_header.addWidget(self.back_profiles_btn)
        ws_header.addWidget(self.ws_disconnect_btn)
        ws_layout.addLayout(ws_header)
        nav = QHBoxLayout()
        self.path_edit = QLineEdit(".")
        self.path_edit.returnPressed.connect(self._goto_path)
        self.refresh_btn = QPushButton("REFRESH")
        self.up_btn = QPushButton("UP")
        self.mkdir_btn = QPushButton("NEW_FOLDER")
        self.refresh_btn.clicked.connect(self._refresh)
        self.up_btn.clicked.connect(self._up_dir)
        self.mkdir_btn.clicked.connect(self._mkdir)
        nav.addWidget(QLabel("REMOTE_PATH:"))
        nav.addWidget(self.path_edit)
        nav.addWidget(self.up_btn)
        nav.addWidget(self.refresh_btn)
        nav.addWidget(self.mkdir_btn)
        ws_layout.addLayout(nav)

        self.tree = SFTPDropTree()
        self.tree.setHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.tree.header().setStretchLastSection(False)
        self.tree.setColumnWidth(0, 380)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 110)
        self.tree.setColumnWidth(3, 170)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setStyleSheet(
            "QTreeWidget::item{padding:2px 0;}"
            "QTreeWidget::item:selected{background:#7300ff;color:#ffffff;}"
        )
        self.tree.itemDoubleClicked.connect(self._open_item)
        self.tree.paths_dropped.connect(self._upload_local_paths)
        self.tree.itemSelectionChanged.connect(self._update_selected_count)
        ws_layout.addWidget(self.tree, 1)

        self.drop_hint = QLabel("TIP: DRAG_AND_DROP_FILE_OR_FOLDER_TO_UPLOAD")
        self.drop_hint.setStyleSheet("color:#9fc3ff;font-style:italic;")
        ws_layout.addWidget(self.drop_hint)

        self.progress_label = QLabel("")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        ws_layout.addWidget(self.progress_label)
        ws_layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.file_progress_tree = QTreeWidget()
        self.file_progress_tree.setHeaderLabels(["File", "Progress", "Status"])
        self.file_progress_tree.setColumnWidth(0, 220)
        self.file_progress_tree.setColumnWidth(1, 130)
        self.file_progress_tree.setColumnWidth(2, 90)
        self.file_progress_tree.setMinimumHeight(110)

        bottom_split = QHBoxLayout()
        bottom_split.addWidget(self.log, 1)
        bottom_split.addWidget(self.file_progress_tree, 1)
        ws_layout.addLayout(bottom_split)
        self.log_cursor = QLabel("█")
        self.log_cursor.setStyleSheet("color:#00fd93;font-size:12px;")
        ws_layout.addWidget(self.log_cursor)

        self.transfers_overlay = QFrame(self.page_workspace)
        self.transfers_overlay.setObjectName("TransfersOverlay")
        self.transfers_overlay.setStyleSheet(
            "#TransfersOverlay {"
            "background: rgba(43,43,57,0.60);"
            "border: 1px solid rgba(72,71,82,0.35);"
            "border-radius: 3px;"
            "}"
        )
        self.transfers_overlay.setMinimumWidth(260)
        self.transfers_overlay.setMaximumWidth(320)
        overlay_layout = QVBoxLayout(self.transfers_overlay)
        overlay_title_row = QHBoxLayout()
        overlay_title = QLabel("ACTIVE_TRANSFERS")
        overlay_title.setStyleSheet("font-size:10px;font-weight:800;letter-spacing:1px;color:#00fd93;")
        self.overlay_live_chip = QLabel("LIVE")
        self.overlay_live_chip.setStyleSheet(
            "background:rgba(0,253,147,0.12);color:#00fd93;padding:2px 6px;font-size:9px;font-weight:700;"
        )
        overlay_title_row.addWidget(overlay_title)
        overlay_title_row.addStretch()
        overlay_title_row.addWidget(self.overlay_live_chip)
        overlay_layout.addLayout(overlay_title_row)
        self.overlay_status_label = QLabel("NO_ACTIVE_TRANSFER")
        self.overlay_status_label.setStyleSheet("font-size:10px;color:#aca9b6;")
        overlay_layout.addWidget(self.overlay_status_label)
        self.overlay_bar = QProgressBar()
        self.overlay_bar.setRange(0, 100)
        self.overlay_bar.setValue(0)
        self.overlay_bar.setFormat("%p%")
        overlay_layout.addWidget(self.overlay_bar)
        self.transfers_overlay.hide()

        ws_footer = QHBoxLayout()
        ws_footer.addWidget(QLabel("SELECTED:"))
        self.selected_count_label = QLabel("0 ITEM")
        self.selected_count_label.setStyleSheet(
            "background:rgba(172,163,255,0.2);color:#aca3ff;padding:2px 8px;font-size:10px;font-weight:700;"
        )
        ws_footer.addWidget(self.selected_count_label)
        ws_footer.addStretch()
        self.upload_btn = QPushButton("UPLOAD_FILES_FOLDER")
        self.download_btn = QPushButton("DOWNLOAD_SELECTED")
        self.delete_btn = QPushButton("DELETE_SELECTED")
        self.upload_btn.setStyleSheet(f"background-color:{self._COLOR_UPLOAD_BTN};color:#ffffff;")
        self.download_btn.setStyleSheet(f"background-color:{self._COLOR_DOWNLOAD_BTN};color:#ffffff;")
        self.delete_btn.setStyleSheet(f"background-color:{self._COLOR_DELETE_BTN};color:#ffffff;")
        self.upload_btn.clicked.connect(self._upload_pick)
        self.download_btn.clicked.connect(self._download_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        ws_footer.addWidget(self.upload_btn)
        ws_footer.addWidget(self.download_btn)
        ws_footer.addWidget(self.delete_btn)
        ws_layout.addLayout(ws_footer)
        self.pages.addWidget(self.page_workspace)
        self.pages.setCurrentWidget(self.page_profiles)
        style = QApplication.style()
        self._folder_icon = style.standardIcon(QStyle.SP_DirIcon) if style else QIcon()
        self._file_icon = style.standardIcon(QStyle.SP_FileIcon) if style else QIcon()
        self._apply_button_icons()
        if not PARAMIKO_OK:
            self._append("❌ paramiko not installed. Run: pip install paramiko")
        self._apply_design_style()

    def _apply_design_style(self):
        self.setStyleSheet(
            """
            QWidget { background:#0d0d16; color:#ece9f7; }
            QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget { background:#0d0d16; }
            QGroupBox {
                border:1px solid #252532;
                background:#12121d;
                margin-top:8px;
                padding-top:8px;
                border-radius:4px;
                color:#aca3ff;
                font-weight:700;
            }
            QLineEdit, QSpinBox, QTextEdit {
                background:#000000;
                border:1px solid #252532;
                border-radius:3px;
                padding:6px 8px;
                color:#ece9f7;
            }
            QTreeWidget {
                background:#12121d;
                border:1px solid #252532;
                color:#ece9f7;
            }
            QTreeWidget::item:hover {
                background:#252532;
            }
            QHeaderView::section {
                background:#1f1e2b;
                color:#00fd93;
                border:none;
                padding:6px;
                font-weight:700;
                letter-spacing:1px;
            }
            QPushButton {
                border:none;
                border-radius:3px;
                padding:6px 10px;
                font-weight:700;
            }
            QPushButton:hover {
                background-color: #252532;
            }
            QPushButton:disabled {
                background:#252532;
                color:#767480;
            }
            QProgressBar {
                background:#12121d;
                border:1px solid #252532;
                border-radius:2px;
                color:#ece9f7;
                text-align:center;
                min-height:16px;
            }
            QProgressBar::chunk {
                background:#00fd93;
            }
            """
        )
        self.connect_btn.setStyleSheet(
            "background:#00fd93;color:#004624;"
            "font-weight:800;"
        )
        self.upload_btn.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #aca3ff,stop:1 #6f5fea);"
            "color:#1d007a;font-weight:800;"
        )
        self.add_profile_btn.setStyleSheet(
            "QPushButton{background:#aca3ff;color:#000000;font-weight:800;padding:10px 22px;"
            "border-radius:2px;border:none;font-size:11px;letter-spacing:0.5px;}"
            "QPushButton:hover{background:#9e93ff;}"
            "QPushButton:pressed{background:#8f83ff;}"
            "QPushButton:disabled{background:#252532;color:#767480;}"
        )

    def _apply_button_icons(self):
        def set_theme_icon(button: QPushButton, icon_name: str):
            icon = QIcon.fromTheme(icon_name)
            if not icon.isNull():
                button.setIcon(icon)

        set_theme_icon(self.connect_btn, "network-connect")
        set_theme_icon(self.disconnect_btn, "network-disconnect")
        set_theme_icon(self.ws_disconnect_btn, "network-disconnect")
        set_theme_icon(self.test_btn, "network-wired")
        set_theme_icon(self.add_profile_btn, "list-add")
        set_theme_icon(self.form_save_btn, "document-save")
        set_theme_icon(self.cancel_form_btn, "go-previous")
        set_theme_icon(self.back_profiles_btn, "go-previous")
        set_theme_icon(self.save_account_btn, "document-save")
        set_theme_icon(self.delete_account_btn, "edit-delete")
        set_theme_icon(self.refresh_btn, "view-refresh")
        set_theme_icon(self.up_btn, "go-up")
        set_theme_icon(self.mkdir_btn, "folder-new")
        set_theme_icon(self.upload_btn, "go-up")
        set_theme_icon(self.download_btn, "go-down")
        set_theme_icon(self.delete_btn, "edit-delete")

    def _update_selected_count(self):
        if not hasattr(self, "selected_count_label"):
            return
        n = len(self.tree.selectedItems()) if hasattr(self, "tree") else 0
        self.selected_count_label.setText(f"{n} ITEM" if n == 1 else f"{n} ITEMS")

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
        if hasattr(self, "overlay_bar"):
            self.overlay_bar.setValue(self.progress.value())
        self._yield_ui()

    def _reset_file_progress_view(self):
        self.file_progress_tree.clear()
        self._file_progress_rows.clear()

    def _ensure_file_progress_row(self, file_id: str, file_label: str):
        row = self._file_progress_rows.get(file_id)
        if row:
            return row
        item = QTreeWidgetItem([file_label, "", "Queued"])
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        self.file_progress_tree.addTopLevelItem(item)
        self.file_progress_tree.setItemWidget(item, 1, bar)
        self._file_progress_rows[file_id] = (item, bar)
        return item, bar

    def _update_file_progress(self, file_id: str, sent: int, total: int):
        item, bar = self._ensure_file_progress_row(file_id, file_id)
        base = max(int(total or 0), 1)
        pct = int((int(sent) * 100) / base)
        bar.setValue(max(0, min(100, pct)))
        item.setText(2, f"{pct}%")

    def _finish_file_progress(self, file_id: str, ok: bool, status_text: str):
        item_bar = self._file_progress_rows.get(file_id)
        if not item_bar:
            return
        item, bar = item_bar
        if ok:
            bar.setValue(100)
            item.setText(2, "Done")
        else:
            item.setText(2, "Failed")
        if status_text and not ok:
            item.setToolTip(2, status_text)
        if hasattr(self, "overlay_status_label"):
            self.overlay_status_label.setText(f"{'Completed' if ok else 'Failed'}: {item.text(0)}")

    def _set_progress_total(self, total: int, label: str | None = None):
        total = max(total, 1)
        if label:
            self.progress_label.setText(label)
            if hasattr(self, "overlay_status_label"):
                self.overlay_status_label.setText(label)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        if hasattr(self, "overlay_bar"):
            self.overlay_bar.setRange(0, total)
            self.overlay_bar.setValue(0)
        if hasattr(self, "transfers_overlay"):
            self.transfers_overlay.show()
            self._position_transfers_overlay()
        self._yield_ui()

    def _end_progress(self):
        self.progress.setVisible(False)
        self.progress_label.setText("")
        if hasattr(self, "overlay_status_label"):
            self.overlay_status_label.setText("NO_ACTIVE_TRANSFER")
        if hasattr(self, "overlay_bar"):
            self.overlay_bar.setRange(0, 100)
            self.overlay_bar.setValue(0)
        if hasattr(self, "transfers_overlay"):
            self.transfers_overlay.hide()
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
            elif kind == "file_progress_init":
                _, file_id, file_label = event
                self._ensure_file_progress_row(file_id, file_label)
            elif kind == "file_progress":
                _, file_id, sent, total = event
                self._update_file_progress(file_id, sent, total)
            elif kind == "file_progress_done":
                _, file_id, ok, status_text = event
                self._finish_file_progress(file_id, bool(ok), str(status_text))
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
            self._end_progress()
            self._set_busy(False)
            self._op_name = None
            self._op_thread = None

    @staticmethod
    def _open_client_from_params(params):
        return open_client_from_params(params)

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
            self.conn_status.setText("● CONNECTED")
            self.conn_status.setStyleSheet(f"color:{self._COLOR_STATUS_OK};font-weight:700;")
        else:
            self.conn_status.setText("● DISCONNECTED")
            self.conn_status.setStyleSheet(f"color:{self._COLOR_STATUS_OFF};font-weight:700;")
        self.connect_btn.setEnabled(not busy and PARAMIKO_OK and self._sftp is None)
        self.disconnect_btn.setEnabled(not busy and self._sftp is not None)
        self.ws_disconnect_btn.setEnabled(not busy and self._sftp is not None)
        self.test_btn.setEnabled(not busy and PARAMIKO_OK)
        self.add_profile_btn.setEnabled(not busy)
        self.back_profiles_btn.setEnabled(not busy)
        self.cancel_form_btn.setEnabled(not busy)
        self.form_save_btn.setEnabled(not busy)
        self.timeout_spin.setEnabled(not busy)
        self.worker_spin.setEnabled(not busy)
        self.save_account_btn.setEnabled(not busy)
        self.delete_account_btn.setEnabled(not busy)
        self.upload_btn.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)
        self.delete_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.up_btn.setEnabled(not busy)
        self.mkdir_btn.setEnabled(not busy)

    # def _tick_visuals(self):
    #     self._pulse_on = not self._pulse_on
    #     if hasattr(self, "ws_status_dot"):
    #         if self._sftp is not None:
    #             color = "#00fd93" if self._pulse_on else "#00ed89"
    #             self.ws_status_dot.setStyleSheet(f"color:{color};font-size:11px;")
    #         else:
    #             self.ws_status_dot.setStyleSheet("color:#ff6e84;font-size:11px;")
    #     if hasattr(self, "log_cursor"):
    #         self._cursor_on = not self._cursor_on
    #         self.log_cursor.setVisible(self._cursor_on)
    #     if hasattr(self, "_profile_active_pulse_labels"):
    #         dot_color = "#00fd93" if self._pulse_on else "#00c97a"
    #         for lbl in self._profile_active_pulse_labels:
    #             lbl.setStyleSheet(
    #                 f"min-width:8px;max-width:8px;min-height:8px;max-height:8px;"
    #                 f"border-radius:4px;background:{dot_color};"
    #             )

    def _position_transfers_overlay(self):
        if not hasattr(self, "transfers_overlay"):
            return
        m = 12
        w = self.transfers_overlay.width()
        h = self.transfers_overlay.sizeHint().height()
        x = max(m, self.page_workspace.width() - w - m)
        y = max(m, self.page_workspace.height() - h - m)
        self.transfers_overlay.move(x, y)

    def _load_accounts(self):
        self._accounts = load_sftp_accounts()
        self._rebuild_profile_grid()

    def _show_profiles_page(self):
        if self._busy:
            return
        self.pages.setCurrentWidget(self.page_profiles)
        self._rebuild_profile_grid()

    def _open_add_form(self):
        self.account_name_edit.clear()
        self.host_edit.clear()
        self.user_edit.clear()
        self.port_spin.setValue(22)
        self.pass_edit.clear()
        self.key_edit.clear()
        self.pages.setCurrentWidget(self.page_form)

    def _open_edit_form(self, name: str):
        acc = next((a for a in self._accounts if a["name"] == name), None)
        if not acc:
            return
        self.account_name_edit.setText(acc["name"])
        self.host_edit.setText(acc.get("host", ""))
        self.user_edit.setText(acc.get("username", ""))
        self.port_spin.setValue(int(acc.get("port", 22) or 22))
        self.key_edit.setText(acc.get("key_file", ""))
        self.pass_edit.setText(load_password(sftp_password_id(acc["name"])))
        self.pages.setCurrentWidget(self.page_form)

    def _connect_profile(self, name: str):
        acc = next((a for a in self._accounts if a["name"] == name), None)
        if not acc:
            return
        self.account_name_edit.setText(acc["name"])
        self.host_edit.setText(acc.get("host", ""))
        self.user_edit.setText(acc.get("username", ""))
        self.port_spin.setValue(int(acc.get("port", 22) or 22))
        self.key_edit.setText(acc.get("key_file", ""))
        self.pass_edit.setText(load_password(sftp_password_id(acc["name"])))
        if self._connect():
            self._connected_profile_name = name
            self.active_profile_label.setText(f"CONNECTED TO: {name}")
            self.pages.setCurrentWidget(self.page_workspace)

    def _update_profiles_stats(self):
        if not hasattr(self, "_stat_active_val"):
            return
        tunnels = 1 if self._sftp is not None else 0
        total = len(self._accounts)
        self._stat_active_val.setText(f"{tunnels:02d}")
        self._stat_total_val.setText(f"{total:02d}" if total < 100 else str(total))

    def _profile_card_icon(self, idx: int) -> QIcon:
        iname = self._PROFILE_CARD_ICON_NAMES[idx % len(self._PROFILE_CARD_ICON_NAMES)]
        return QIcon.fromTheme(iname)

    def _make_profile_action_button(self, text: str, variant: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        if variant == "connect_active":
            btn.setStyleSheet(
                "QPushButton{background:#00fd93;color:#004624;font-size:11px;font-weight:800;"
                "letter-spacing:1px;padding:8px 10px;border:none;border-radius:2px;}"
                "QPushButton:hover{background:#00ed89;}"
                "QPushButton:disabled{background:#252532;color:#767480;}"
            )
        elif variant == "connect":
            btn.setStyleSheet(
                "QPushButton{background:#252532;color:#ece9f7;font-size:11px;font-weight:800;"
                "letter-spacing:1px;padding:8px 10px;border:none;border-radius:2px;}"
                "QPushButton:hover{background:#00fd93;color:#004624;}"
                "QPushButton:disabled{background:#1a1a24;color:#767480;}"
            )
        elif variant == "edit":
            btn.setStyleSheet(
                "QPushButton{background:transparent;color:#aca3ff;font-size:11px;font-weight:800;"
                "letter-spacing:1px;padding:8px 12px;border:1px solid #484752;border-radius:2px;}"
                "QPushButton:hover{background:rgba(172,163,255,0.12);}"
            )
        elif variant == "delete":
            btn.setStyleSheet(
                "QPushButton{background:transparent;color:#ff6e84;font-size:11px;font-weight:800;"
                "letter-spacing:1px;padding:8px 12px;border:1px solid rgba(255,110,132,0.35);"
                "border-radius:2px;}"
                "QPushButton:hover{background:rgba(255,110,132,0.12);}"
            )
        return btn

    def _make_profile_dashboard_card(
        self,
        name: str,
        host: str,
        port: int,
        user: str,
        idx: int,
        is_active_tunnel: bool,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("SftpProfileCard")
        card.setMinimumWidth(self._PROFILE_CARD_MIN_WIDTH)
        card.setMinimumHeight(188)
        card.setToolTip(f"{user}@{host}:{port}")
        card.setStyleSheet(
            "QFrame#SftpProfileCard{background:#12121d;border:none;border-radius:2px;}"
            "QFrame#SftpProfileCard:hover{background:#1f1e2b;}"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(0)

        # if is_active_tunnel:
        #     top = QHBoxLayout()
        #     top.addStretch()
        #     badge = QFrame()
        #     badge.setStyleSheet(
        #         "QFrame{background:#006d3c;border:none;border-radius:10px;padding:0px;}"
        #     )
        #     bl = QHBoxLayout(badge)
        #     bl.setContentsMargins(8, 4, 10, 4)
        #     bl.setSpacing(6)
            # dot = QLabel()
            # dot_color = "#00fd93" if self._pulse_on else "#00c97a"
            # dot.setStyleSheet(
            #     f"min-width:8px;max-width:8px;min-height:8px;max-height:8px;"
            #     f"border-radius:4px;background:{dot_color};"
            # )
            # self._profile_active_pulse_labels.append(dot)
            # active_lbl = QLabel("ACTIVE")
            # active_lbl.setStyleSheet(
            #     "font-size:10px;font-weight:800;color:#00fd93;letter-spacing:1px;border:none;"
            #     "background:transparent;"
            # )
            # # bl.addWidget(dot)
            # bl.addWidget(active_lbl)
            # top.addWidget(badge, 0, Qt.AlignRight | Qt.AlignTop)
            # outer.addLayout(top)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        ic = self._profile_card_icon(idx)
        if not ic.isNull():
            icon_lbl.setPixmap(ic.pixmap(QSize(32, 32)))
        else:
            icon_lbl.setText("◇")
            icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"color:{'#aca3ff' if is_active_tunnel else '#767480'};background:transparent;"
            "font-size:26px;"
        )
        outer.addWidget(icon_lbl)

        title = QLabel(name)
        title.setStyleSheet(
            "font-size:19px;font-weight:700;color:#ece9f7;background:transparent;border:none;"
        )
        outer.addWidget(title)
        sub = QLabel(f"{host}:{port}")
        sub.setStyleSheet(
            "font-size:12px;color:#767480;background:transparent;border:none;margin-top:2px;"
        )
        outer.addWidget(sub)
        outer.addStretch()

        row = QHBoxLayout()
        row.setSpacing(10)
        connect_variant = "connect_active" if is_active_tunnel else "connect"
        connect_btn = self._make_profile_action_button("Connect", connect_variant)
        connect_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit_btn = self._make_profile_action_button("Edit", "edit")
        del_btn = self._make_profile_action_button("Delete", "delete")
        connect_btn.clicked.connect(lambda _=False, n=name: self._connect_profile(n))
        edit_btn.clicked.connect(lambda _=False, n=name: self._open_edit_form(n))
        del_btn.clicked.connect(lambda _=False, n=name: self._delete_account(n))
        row.addWidget(connect_btn, 1)
        row.addWidget(edit_btn, 0)
        row.addWidget(del_btn, 0)
        outer.addLayout(row)
        return card

    def _make_new_profile_tile(self) -> QToolButton:
        btn = QToolButton()
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.setMinimumHeight(188)
        btn.setMinimumWidth(self._PROFILE_CARD_MIN_WIDTH)
        ic = QIcon.fromTheme("list-add")
        if not ic.isNull():
            btn.setIcon(ic)
            btn.setIconSize(QSize(48, 48))
        btn.setText("NEW_PROFILE_INSTANCE")
        btn.setStyleSheet(
            "QToolButton{background:transparent;border:2px dashed rgba(72,71,82,0.45);"
            "border-radius:2px;color:#767480;font-size:11px;font-weight:800;letter-spacing:1px;"
            "padding:20px;}"
            "QToolButton:hover{border-color:rgba(172,163,255,0.55);color:#aca3ff;"
            "background:rgba(172,163,255,0.05);}"
        )
        btn.clicked.connect(self._open_add_form)
        return btn

    def _rebuild_profile_grid(self):
        # self._profile_active_pulse_labels.clear()
        while self.profile_grid_layout.count():
            item = self.profile_grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        cols = self._profile_grid_columns()
        is_connected = self._sftp is not None
        active_name = self._connected_profile_name
        for idx, acc in enumerate(self._accounts):
            name = acc["name"]
            host = acc.get("host", "")
            user = acc.get("username", "")
            port = int(acc.get("port", 22) or 22)
            is_active = bool(is_connected and active_name == name)
            card = self._make_profile_dashboard_card(name, host, port, user, idx, is_active)
            self.profile_grid_layout.addWidget(card, idx // cols, idx % cols)
        add_i = len(self._accounts)
        self.profile_grid_layout.addWidget(self._make_new_profile_tile(), add_i // cols, add_i % cols)
        self._update_profiles_stats()

    def _profile_grid_columns(self):
        width = max(self.profile_grid_widget.width(), 1)
        cols_by_width = max(1, width // self._PROFILE_CARD_MIN_WIDTH)
        return min(self._PROFILE_GRID_MAX_COLUMNS, max(self._PROFILE_GRID_MIN_COLUMNS, cols_by_width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "pages") and self.pages.currentWidget() is self.page_profiles:
            self._rebuild_profile_grid()
        self._position_transfers_overlay()

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
        self.pages.setCurrentWidget(self.page_profiles)
        self._append(f"💾 Saved account: {name}")

    def _delete_account(self, name: str | None = None):
        name = (name or self.account_name_edit.text().strip()).strip()
        if not name:
            return
        if QMessageBox.question(self, "Delete account", f"Delete saved account '{name}'?") != QMessageBox.Yes:
            return
        self._accounts = [a for a in self._accounts if a["name"] != name]
        save_sftp_accounts(self._accounts)
        delete_password(sftp_password_id(name))
        self._load_accounts()
        self.account_name_edit.clear()
        self.pages.setCurrentWidget(self.page_profiles)
        self._append(f"🗑 Deleted account: {name}")

    def _ensure_connected(self):
        if self._sftp is None:
            QMessageBox.information(self, "SFTP", "Connect first.")
            return False
        return True

    def _connect(self):
        if self._busy:
            return False
        if not PARAMIKO_OK:
            QMessageBox.critical(
                self,
                "SFTP unavailable",
                "Python package 'paramiko' is not installed.\n\nInstall it in your active environment:\npip install paramiko",
            )
            return False
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        if not host or not user:
            QMessageBox.warning(self, "SFTP", "Host and Username are required.")
            return False
        timeout = int(self.timeout_spin.value())
        try:
            self._set_busy(True)
            self._append(f"🔌 Connecting to {user}@{host}:{self.port_spin.value()} ...")
            self._disconnect()
            self._append(f"⏱ Connection timeout: {timeout}s")
            sock = socket.create_connection((host, int(self.port_spin.value())), timeout=timeout)
            self._transport = paramiko.Transport(sock)
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
            nm = self.account_name_edit.text().strip()
            self._connected_profile_name = nm if nm else None
            return True
        except socket.timeout:
            self._append("❌ Connect timeout. Host unreachable or SSH service too slow.")
            self._disconnect()
            return False
        except TimeoutError:
            self._append("❌ Connect timeout. Host unreachable or SSH service too slow.")
            self._disconnect()
            return False
        except paramiko.ssh_exception.SSHException as e:
            msg = str(e)
            if "Error reading SSH protocol banner" in msg:
                self._append("❌ SSH banner timeout. Check host/port and ensure target is an SSH server.")
            else:
                self._append(f"❌ SSH error: {msg}")
            self._disconnect()
            return False
        except Exception as e:
            self._append(f"❌ Connect failed: {e}")
            self._disconnect()
            return False
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

    def _disconnect(self, show_profiles: bool = False):
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
        self._connected_profile_name = None
        self.active_profile_label.setText("CONNECTED TO: NONE")
        self._set_busy(False)
        if show_profiles:
            self.pages.setCurrentWidget(self.page_profiles)
            self._rebuild_profile_grid()

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
                item = QTreeWidgetItem(
                    [
                        a.filename,
                        "dir" if is_dir else "file",
                        "" if is_dir else str(a.st_size),
                        datetime.fromtimestamp(a.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    ]
                )
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
        name, ok = QInputDialog.getText(self, "NEW_FOLDER", "FOLDER_NAME:")
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
        self._reset_file_progress_view()
        params = self._sftp_connection_params()
        params["cwd"] = self._cwd
        self._start_background_job(
            "upload", self._run_upload_job, params, list(paths), int(self.worker_spin.value())
        )

    def _collect_upload_tasks(self, paths):
        return collect_upload_tasks(self._cwd, paths)

    def _sftp_connection_params(self):
        return {
            "host": self.host_edit.text().strip(),
            "port": int(self.port_spin.value()),
            "username": self.user_edit.text().strip(),
            "password": self.pass_edit.text(),
            "key_file": self.key_edit.text().strip(),
            "timeout": int(self.timeout_spin.value()),
        }

    def _run_upload_job(self, params, paths, workers):
        run_upload_job(params, self._cwd, paths, workers, self._op_queue.put)

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

    def _run_delete_job(self, params, delete_targets):
        run_delete_job(params, delete_targets, self._op_queue.put)
