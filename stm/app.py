import sys

from PySide6.QtWidgets import QApplication

from . import config
from .main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_DISPLAY_NAME)
    config.TITLE_FONT_FAMILY = config.load_title_font()
    icon = config.load_app_icon()
    app.setWindowIcon(icon)
    win = MainWindow()
    win.setWindowIcon(icon)
    win.show()
    sys.exit(app.exec())
