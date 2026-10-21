"""Running a skill's bundled scripts, confined.

Skills may ship executable code, and some jobs genuinely need it -- producing
a .pptx, rendering against a template. Running third-party code in our own
process is not an option, so it runs in a cage.

**Why an OS-level sandbox and not a WebAssembly one.** Pyodide-under-Deno
looks lighter and several agent frameworks use it, but two real escapes are
on record (Grist-Core's Pyodide escape leading to RCE; n8n's CVE-2025-68668,
scored 9.9). The structural problem is that those approaches tend to be
*deny-lists*: they assume the defender can enumerate every dangerous
capability, and that enumeration is never finished. Seatbelt and bubblewrap
are allow-lists enforced by the kernel: nothing is permitted until it is
named.

**Why not a hosted sandbox.** E2B and Modal would both mean shipping the
code and its data off the machine, which contradicts the two promises this
product is built on -- images never leave the network, the knowledge base is
a local file.
"""

from .policy import SandboxLevel, profile_for
from .runner import SandboxError, SandboxResult, available, run

__all__ = ["SandboxError", "SandboxLevel", "SandboxResult", "available",
           "profile_for", "run"]
