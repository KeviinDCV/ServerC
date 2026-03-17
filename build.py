"""Build script — compiles the app with PyInstaller."""

import subprocess
import sys
import os


def build():
    print("=" * 50)
    print("  ServerC — Build")
    print("=" * 50)

    # Ensure dependencies
    print("\n[1/3] Instalando dependencias...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Run PyInstaller
    print("\n[2/3] Compilando con PyInstaller...")
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "build.spec",
    ])

    print("\n[3/3] ¡Compilación exitosa!")
    print(f"  Ejecutable en: {os.path.abspath('dist/ServerC/ServerC.exe')}")
    print()
    print("Para crear el instalador:")
    print("  1. Instala Inno Setup: https://jrsoftware.org/isinfo.php")
    print("  2. Abre installer.iss con Inno Setup y compila")
    print("  3. El instalador se creará en installer_output/")


if __name__ == "__main__":
    build()
