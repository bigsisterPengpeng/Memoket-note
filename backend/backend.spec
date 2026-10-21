# Bundle the backend so desktop installations do not require system Python.
# Explicitly collect dynamic imports that PyInstaller's static analysis cannot see.
from importlib.util import find_spec
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

if find_spec("mcp") is None:
    raise RuntimeError("Install backend/requirements-agents.txt before packaging the CLI/MCP-enabled desktop app")

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("memoket_kite")
    + collect_submodules("app")
    + [
        "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    ]
)

datas = collect_data_files("memoket_kite")
# Dictionary data is not an importable module. Include it explicitly: omitting it
# silently disables dictionary segmentation and changes retrieval behavior.
datas += [("app/database/kb/cn_words.txt.gz", "app/database/kb")]
datas += [("../docs/licenses/jieba-MIT.txt", "licenses")]

a = Analysis(
    ["entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    # Development tools are not needed in the installed application.
    excludes=["pytest", "pyflakes", "coverage", "PyInstaller"],
    noarchive=False,
)
# Never ship a development library or backups. Runtime data belongs outside the
# bundle; frozen configuration also rejects relative data directories.
a.datas = [d for d in a.datas if not str(d[0]).replace("\\", "/").startswith(("data/", "backend/data/"))]
assert not any(str(d[0]).replace("\\", "/").startswith("data/") for d in a.datas), "data/ must not be bundled"

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="memoket-note-backend",
    console=True,          # Electron captures the backend's stdout for logging.
    strip=False, upx=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="memoket-note-backend",
)
