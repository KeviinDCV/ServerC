# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for ServerC."""

import os
from PIL import Image

# Convert favicon.png to icon.ico — always regenerate with BMP format for max compatibility
png_path = os.path.join('assets', 'favicon.png')
ico_path = os.path.join('assets', 'icon.ico')
if os.path.exists(png_path):
    img = Image.open(png_path).convert('RGBA')
    # Create properly sized BMP-format ICO (not PNG-compressed)
    # Only sizes <= 256 are valid for ICO
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Build the ICO file manually for maximum compatibility
    import struct, io
    
    entries = []
    for w, h in sizes:
        resized = img.resize((w, h), Image.LANCZOS)
        
        if w >= 256:
            # 256x256 stored as PNG inside ICO
            buf = io.BytesIO()
            resized.save(buf, format='PNG')
            raw = buf.getvalue()
        else:
            # Smaller sizes stored as BMP (DIB) inside ICO
            # Convert RGBA to BGRA for BMP
            pixels = list(resized.getdata())
            bmp_data = bytearray()
            
            # BITMAPINFOHEADER (40 bytes)
            bmp_data += struct.pack('<I', 40)        # biSize
            bmp_data += struct.pack('<i', w)          # biWidth
            bmp_data += struct.pack('<i', h * 2)      # biHeight (doubled for AND mask)
            bmp_data += struct.pack('<H', 1)          # biPlanes
            bmp_data += struct.pack('<H', 32)         # biBitCount (32-bit BGRA)
            bmp_data += struct.pack('<I', 0)          # biCompression (BI_RGB)
            bmp_data += struct.pack('<I', 0)          # biSizeImage
            bmp_data += struct.pack('<i', 0)          # biXPelsPerMeter
            bmp_data += struct.pack('<i', 0)          # biYPelsPerMeter
            bmp_data += struct.pack('<I', 0)          # biClrUsed
            bmp_data += struct.pack('<I', 0)          # biClrImportant
            
            # Pixel data (bottom-up, BGRA)
            for y in range(h - 1, -1, -1):
                for x in range(w):
                    r, g, b, a = pixels[y * w + x]
                    bmp_data += struct.pack('BBBB', b, g, r, a)
            
            # AND mask (1-bit, bottom-up, padded to 4 bytes per row)
            row_bytes = ((w + 31) // 32) * 4
            bmp_data += b'\x00' * (row_bytes * h)
            
            raw = bytes(bmp_data)
        
        entries.append((w, h, raw))
    
    # Write ICO file
    with open(ico_path, 'wb') as f:
        num = len(entries)
        # ICONDIR header
        f.write(struct.pack('<HHH', 0, 1, num))
        
        offset = 6 + num * 16  # After header + directory entries
        for w, h, raw in entries:
            bw = 0 if w >= 256 else w
            bh = 0 if h >= 256 else h
            f.write(struct.pack('<BBBBHHII', bw, bh, 0, 0, 1, 32, len(raw), offset))
            offset += len(raw)
        
        for w, h, raw in entries:
            f.write(raw)
    
    print(f'  Icono generado: {ico_path} ({os.path.getsize(ico_path)} bytes)')

icon_file = os.path.abspath(ico_path) if os.path.exists(ico_path) else None
print(f'  Usando icono: {icon_file}')

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
        'win10toast',
        'sqlite3',
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
