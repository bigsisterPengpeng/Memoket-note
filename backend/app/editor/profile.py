"""The user's stated writing preferences.

One line, previously defined in ``routers/compose`` and imported by three
other routers. It reads the store and is used by every writing path, which
makes it a capability, not part of any one endpoint.
"""

from __future__ import annotations

from ..database import store

# Enough to shape the writing without crowding out the material. Past this,
# preferences start competing with the facts for the model's attention.
PROFILE_LIMIT = 20


def entries(user: str) -> list[str]:
    return [p["text"] for p in store.list_profile(user)[:PROFILE_LIMIT]]
