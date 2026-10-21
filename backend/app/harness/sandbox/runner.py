"""Executing one script inside the cage.

Platform-specific because the kernel primitives are: Seatbelt on macOS,
bubblewrap on Linux. Same approach Claude Code takes, for the same reason --
enforcement below the application means a clever script cannot argue its way
past it.

**When neither is available the answer is no.** Falling back to "run it
anyway, unconfined" would turn a security boundary into a suggestion, and the
failure would be silent on exactly the machines that need it most.
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import limits
from .policy import Profile, SandboxLevel, profile_for

# The macOS directories where this machine's own data lives. The Seatbelt
# policy denies reads across all of them and then punches back out only the
# interpreter and the skill's own files. Ordered widest first for readability;
# Seatbelt itself does not care about order among denials.
_DATA_REGIONS = (
    "/Users",               # every home directory, so notes and the knowledge base
    "/Volumes",             # anything mounted, including other people's disks
    "/private/tmp",         # /tmp
    "/private/var/folders", # the per-user temp trees TMPDIR points into
    "/private/var/root",
)


class SandboxError(RuntimeError):
    """The script could not be run safely. Never means "ran but failed"."""


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    produced: tuple[Path, ...] = ()


def available() -> bool:
    """Whether this machine can confine a process at all."""
    if sys.platform == "darwin":
        return shutil.which("sandbox-exec") is not None
    if sys.platform.startswith("linux"):
        return shutil.which("bwrap") is not None
    return False


def _seatbelt_profile(prof: Profile, scratch: Path) -> str:
    """A Seatbelt policy: allow by default, then deny what must not be reached.

    The intended shape was ``(deny default)`` with named allowances -- a true
    allow-list. It does not work: CPython under deny-default aborts during
    interpreter startup (SIGABRT, no diagnostic), and getting it to boot means
    enumerating every path, mach service and sysctl the interpreter touches.
    That enumeration is as open-ended as the deny-lists this module distrusts
    elsewhere. A blanket ``(deny file-read-data)`` with an allow-list fails the
    same way, even when the list already covers every directory the process is
    known to open.

    What does work, and what is written below, is allow-default plus denial of
    whole regions:

      * the network, at every level and for every skill
      * writing anywhere but the scratch directory (and, at FILES level, the
        one output path the user chose)
      * reading any region where this machine's *data* lives -- home
        directories, mounted volumes, the temp trees -- with the interpreter's
        own installation and the skill's own directory punched back out

    So a script can still read ``/usr`` and ``/System``. It cannot read the
    knowledge base, the user's notes, another skill's files, or anything under
    ``$HOME``, because all of those are inside the denied regions. That is a
    weaker guarantee than the Linux path, where bubblewrap builds a fresh
    mount namespace that simply does not contain the rest of the disk; the
    asymmetry is real and is not worth papering over.
    """
    read_ok = [Path(sys.base_prefix), Path(sys.prefix), *prof.read_paths, scratch]
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        '(allow file-write* (literal "/dev/null") (literal "/dev/stdout")'
        ' (literal "/dev/stderr"))',
        '(allow file-read-data (subpath "/"))',
        # Every region on a Mac where user data can live. Denying these is
        # what stands between a skill script and the knowledge base.
        "(deny file-read-data " + " ".join(
            f'(subpath "{d}")' for d in _DATA_REGIONS) + ")",
    ]
    for path in sorted({p.resolve() for p in prof.write_paths} | {scratch.resolve()}):
        lines.append(f'(allow file-write* (subpath "{path}"))')
    for path in sorted({p.resolve() for p in read_ok}):
        lines.append(f'(allow file-read-data (subpath "{path}"))')
    return "\n".join(lines)


def _command(prof: Profile, script: Path, scratch: Path) -> list[str]:
    if sys.platform == "darwin":
        policy = scratch / "policy.sb"
        policy.write_text(_seatbelt_profile(prof, scratch), encoding="utf-8")
        return ["sandbox-exec", "-f", str(policy), sys.executable, str(script)]

    if sys.platform.startswith("linux"):
        cmd = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
               "--ro-bind", sys.prefix, sys.prefix,
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
               "--proc", "/proc", "--dev", "/dev"]
        for path in prof.read_paths:
            cmd += ["--ro-bind", str(path), str(path)]
        for path in prof.write_paths:
            cmd += ["--bind", str(path), str(path)]
        # --unshare-all already removes the network namespace; spelled out
        # again so it survives someone editing the flag list.
        cmd += ["--unshare-net", sys.executable, str(script)]
        return cmd

    raise SandboxError(f"no sandbox available on {platform.system()}")


def _apply_limits() -> None:
    import resource

    for what, value in ((resource.RLIMIT_CPU, limits.CPU_SECONDS),
                        (resource.RLIMIT_AS, limits.MEMORY_BYTES)):
        try:
            resource.setrlimit(what, (value, value))
        except (ValueError, OSError):
            pass


def enforced_limits() -> dict[str, bool]:
    import json
    import subprocess
    import sys

    src = (
        "import json,resource\n"
        "def t(w,v):\n"
        "    try:\n"
        "        resource.setrlimit(w,(v,v)); return True\n"
        "    except (ValueError,OSError): return False\n"
        "print(json.dumps({'cpu_seconds':t(resource.RLIMIT_CPU,%d),"
        "'memory_bytes':t(resource.RLIMIT_AS,%d)}))"
    ) % (limits.CPU_SECONDS, limits.MEMORY_BYTES)
    out = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, timeout=30)
    got = json.loads(out.stdout) if out.returncode == 0 else {"cpu_seconds": False, "memory_bytes": False}
    return {"wall_clock": True, "output_bytes": True, **got}


async def run(skill_dir: Path, script: str, args: dict,
              level: SandboxLevel, output: Path | None = None) -> SandboxResult:
    """Run one script from a skill directory, confined to ``level``.

    Arguments reach the script as a JSON file in the scratch directory rather
    than on the command line -- argv is visible to other processes, and skill
    arguments can carry note content.
    """
    if level is SandboxLevel.NONE:
        raise SandboxError("this skill has not been granted permission to run scripts")
    if not available():
        raise SandboxError(
            "no sandbox on this machine (needs sandbox-exec on macOS, bwrap on "
            "Linux); refusing to run third-party code unconfined")

    target = (skill_dir / "scripts" / script).resolve()
    try:
        target.relative_to(skill_dir.resolve())
    except ValueError:
        raise SandboxError("script path escapes the skill directory") from None
    if not target.is_file():
        raise SandboxError(f"no such script: {script}")

    with tempfile.TemporaryDirectory(prefix="skill-run-") as tmp:
        scratch = Path(tmp)
        (scratch / "args.json").write_text(_json_dumps(args), encoding="utf-8")
        prof = profile_for(level, skill_dir, scratch, output)

        proc = await asyncio.create_subprocess_exec(
            *_command(prof, target, scratch),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(scratch),
            env={"SKILL_ARGS": str(scratch / "args.json"),
                 "SKILL_OUT": str(scratch),
                 "PATH": "/usr/bin:/bin"},
            preexec_fn=_apply_limits,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(), timeout=limits.WALL_CLOCK_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise SandboxError(
                f"script exceeded {limits.WALL_CLOCK_SECONDS}s and was killed"
            ) from None

        produced = tuple(p for p in scratch.iterdir()
                         if p.is_file() and p.name not in {"args.json", "policy.sb"})
        total = sum(p.stat().st_size for p in produced)
        if total > limits.OUTPUT_BYTES:
            raise SandboxError(
                f"script produced {total} bytes, over the {limits.OUTPUT_BYTES} limit")

        return SandboxResult(
            ok=proc.returncode == 0,
            stdout=out.decode("utf-8", "replace")[:limits.STDOUT_CHARS],
            stderr=err.decode("utf-8", "replace")[:2000],
            produced=produced,
        )


def _json_dumps(value: dict) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
