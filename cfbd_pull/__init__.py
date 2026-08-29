"""Pull every available statistic from the CollegeFootballData.com API.

Quick start::

    python -m cfbd_pull --years 2024 --dry-run     # see the plan
    python -m cfbd_pull --years 2024               # pull it

Programmatic use::

    from cfbd_pull import CFBDClient, Store
    client = CFBDClient()
    games = client.get("/games", {"year": 2024, "seasonType": "both"})
"""

from .client import AuthError, CFBDClient, CFBDError
from .endpoints import ENDPOINTS, Endpoint, select
from .store import DEFAULT_OUT, Store

__version__ = "1.0.0"

__all__ = [
    "CFBDClient",
    "CFBDError",
    "AuthError",
    "Store",
    "DEFAULT_OUT",
    "Endpoint",
    "ENDPOINTS",
    "select",
]
