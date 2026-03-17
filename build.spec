# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for ServerC."""

import os
from PIL import Image

# Convert favicon.png to icon.ico — always regenerate
png_path = os.path.join('assets', 'favicon.png')
ico_path = os.path.join('assets', 'icon.ico')
if os.path.exists(png_path):
    img = Image.open(png_path).convert('RGBA')
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [img.resize((s, s), Image.LANCZOS) for s in sizes]
    # Largest as base, rest as append
    imgs[-1].save(ico_path, format='ICO', append_images=imgs[:-1])
    print(f'  Icono generado: {ico_path} ({os.path.getsize(ico_path)} bytes)')

icon_file = ico_path if os.path.exists(ico_path) else None

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'winrm',
        'winrm.transport',
        'requests',
        'requests_ntlm',
        'xmltodict',
        'cryptography',
        'customtkinter',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ServerC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ServerC',
)
