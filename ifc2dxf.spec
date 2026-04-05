# ifc2dxf.spec
# ────────────────────────────────────────────────────────────────────────────
# PyInstaller spec file for IFC → DXF Converter
#
# Usage:
#   pyinstaller ifc2dxf.spec
#
# The resulting distributable folder will be:
#   dist\IFC2DXF\          (--onedir, recommended for ifcopenshell)
#
# If you prefer a single .exe, change onefile=True below — but note that
# ifcopenshell's native .dll/.so files make startup noticeably slower.
# ────────────────────────────────────────────────────────────────────────────

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

# ── Gather everything ifcopenshell ships (dlls, schema files, etc.) ──────────
ifc_datas, ifc_binaries, ifc_hiddenimports = collect_all("ifcopenshell")

# ── Gather customtkinter theme/image assets ───────────────────────────────────
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")

# ── Gather numpy (required by ifcopenshell.sql) ───────────────────────────────
np_datas, np_binaries, np_hiddenimports = collect_all("numpy")

# ── Merge ─────────────────────────────────────────────────────────────────────
all_datas    = ifc_datas    + ctk_datas + np_datas + [("P.ico", ".")]
all_binaries = ifc_binaries + ctk_binaries + np_binaries
all_hidden   = ifc_hiddenimports + ctk_hiddenimports + np_hiddenimports + [
    "ifcopenshell",
    "ifcopenshell.geom",
    "ifcopenshell.util",
    "ifcopenshell.util.element",
    "ifcopenshell.util.selector",
    "ifcopenshell.util.placement",
    "ifcopenshell.util.unit",
    "ezdxf",
    "ezdxf.math",
    "ezdxf.entities",
    "customtkinter",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "PIL",          # Pillow — used by customtkinter for image rendering
    "PIL.Image",
    "PIL.ImageTk",
    "numpy",
    "numpy.core",
    "numpy.core._multiarray_umath",
]

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "pytest"],
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
    name="IFC2DXF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No black console window (windowed app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="P.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="IFC2DXF",
)
