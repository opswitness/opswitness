# PyInstaller specification for a signing-friendly directory bundle.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


PREFIX = Path(sys.prefix).resolve(strict=True)
RAW_ENTRYPOINT = Path(sys.prefix) / "bin" / "opswitness"
try:
    ENTRYPOINT = RAW_ENTRYPOINT.resolve(strict=True)
except OSError as exc:
    raise SystemExit("the isolated wheel did not install its opswitness entrypoint") from exc
if (
    ENTRYPOINT.name != "opswitness"
    or RAW_ENTRYPOINT.is_symlink()
    or not RAW_ENTRYPOINT.is_file()
    or not os.access(RAW_ENTRYPOINT, os.X_OK)
    or not ENTRYPOINT.is_relative_to(PREFIX)
):
    raise SystemExit("PyInstaller entrypoint must be the isolated wheel's opswitness script")

datas, binaries, hiddenimports = collect_all("opswitness")
mcp_datas, mcp_binaries, mcp_hiddenimports = collect_all("mcp")
semantic_datas = []
semantic_binaries = []
semantic_hiddenimports = []
for package in ("numpy", "onnxruntime", "sqlite_vec", "tokenizers"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    semantic_datas.extend(package_datas)
    semantic_binaries.extend(package_binaries)
    semantic_hiddenimports.extend(package_hiddenimports)

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[],
    binaries=[*binaries, *mcp_binaries, *semantic_binaries],
    datas=[*datas, *mcp_datas, *semantic_datas],
    hiddenimports=[*hiddenimports, *mcp_hiddenimports, *semantic_hiddenimports],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="opswitness-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    argv_emulation=False,
    target_arch="arm64",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="opswitness-backend",
)
