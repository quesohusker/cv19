"""API key resolution.

You are running this locally and do not want to fiddle with environment
variables every session. Put your key in ONE of these places -- they are tried
in order, and the first non-empty one wins:

  1. ``cfbd_pull/local_key.py``   <-- recommended; git-ignored, cannot leak
         Create the file with a single line:

             API_KEY = "your-key-here"

  2. ``API_KEY`` below            <-- edit this line directly if you prefer
  3. ``CFBD_API_KEY`` env var
  4. ``--api-key`` on the command line

NOTE ON HARD-CODING: quesohusker/cv19 is a *public* repository. A key pasted
into option 2 gets published on GitHub the moment this is pushed, and stays in
the git history even if a later commit removes it -- scrapers find those within
minutes. Option 1 is git-ignored, so it gives you the same "just run it"
behaviour with none of that exposure. Get or regenerate a key any time at
https://collegefootballdata.com/key
"""

from __future__ import annotations

import os
from typing import Optional

#: Optional hard-coded key. Leave empty on any repo you push publicly.
API_KEY = ""


def _from_local_module() -> str:
    """Read the key from the git-ignored ``local_key.py`` if it exists."""
    try:
        from . import local_key  # type: ignore[attr-defined]
    except ImportError:
        return ""
    return str(getattr(local_key, "API_KEY", "") or "").strip()


def resolve_api_key(explicit: Optional[str] = None) -> str:
    """Return the API key from the first source that provides one."""
    for candidate in (
        explicit,
        _from_local_module(),
        API_KEY,
        os.environ.get("CFBD_API_KEY", ""),
    ):
        if candidate and candidate.strip():
            return candidate.strip()
    return ""
