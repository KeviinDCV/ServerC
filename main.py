"""ServerC — Monitor de Servidores Windows.

Entry point for the application.
"""

import customtkinter as ctk


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    from app.ui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
