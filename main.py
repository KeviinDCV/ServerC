"""ServerC — Monitor de Servidores Windows.

Entry point for the application.
"""

import sys
import os
import logging
import customtkinter as ctk


def _setup_logging():
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(app_data, "ServerC")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "serverc_debug.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )
    # Also capture unhandled exceptions
    def _exc_handler(exc_type, exc_value, exc_tb):
        logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = _exc_handler
    logging.info("ServerC starting")


def main():
    _setup_logging()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    from app.ui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
