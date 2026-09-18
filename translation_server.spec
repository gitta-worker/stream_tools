# -*- mode: python ; coding: utf-8 -*-

assets = [
    ("index.html", "."),
    ("translation.js", "."),
    ("translation.css", "."),
    ("setup.html", "."),
    ("setup.js", "."),
    ("setup.css", "."),
]

a = Analysis(
    ["translation_server.py"],
    pathex=[],
    binaries=[],
    datas=assets,
    hiddenimports=["speech_recognition", "pyaudio"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="translation_server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
