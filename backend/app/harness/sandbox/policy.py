"""What a sandbox level is allowed to touch.

Three levels, and deliberately no fourth: **no level gets network access.**
Anything that needs to reach the outside world goes through the tool pool,
where there is authorisation, an audit trail and rate limiting. A script
with a socket has none of that.

The level is **granted by the user at install time**, not declared by the
skill. A skill saying "I need to write files" is a request, the same way an
app asking for the camera is a request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path


class SandboxLevel(IntEnum):
    NONE = 0        # scripts don't run at all -- the default for anything imported
    COMPUTE = 1     # read the skill's own directory, write one scratch dir
    FILES = 2       # the above, plus write to a path the user explicitly chose

    @classmethod
    def parse(cls, value: str | None) -> "SandboxLevel":
        return {"compute": cls.COMPUTE, "files": cls.FILES}.get(
            (value or "").strip().lower(), cls.NONE)


@dataclass(frozen=True)
class Profile:
    """Concrete paths for one run, derived from a level.

    Read paths are the skill's own directory and nothing else: a script must
    not be able to read the user's notes, the knowledge base, or another
    skill's files.
    """

    level: SandboxLevel
    read_paths: tuple[Path, ...]
    write_paths: tuple[Path, ...]
    network: bool = False           # never true; kept explicit so it reads as a decision


def profile_for(level: SandboxLevel, skill_dir: Path, scratch: Path,
                output: Path | None = None) -> Profile:
    if level is SandboxLevel.NONE:
        return Profile(level, (), ())
    read = (skill_dir,)
    write = (scratch,)
    if level is SandboxLevel.FILES and output is not None:
        write = (scratch, output)
    return Profile(level, read, write)
