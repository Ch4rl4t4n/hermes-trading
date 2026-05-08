#!/usr/bin/env python3
"""Check whether a route exists in FastAPI OpenAPI spec.

Usage:
  python3 scripts/check_swarm_openapi_route.py
  OPENAPI_URL="http://127.0.0.1:8001/openapi.json" \
    ROUTE_PATH="/api/v2/swarm/capabilities" \
    python3 scripts/check_swarm_openapi_route.py
"""

from __future__ import annotations

import json
import os
import sys
from urllib.request import urlopen


def main() -> int:
    openapi_url = os.getenv("OPENAPI_URL", "http://127.0.0.1:8001/openapi.json").strip()
    route_path = os.getenv("ROUTE_PATH", "/api/v2/swarm/capabilities").strip()

    try:
        with urlopen(openapi_url, timeout=10) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to fetch/parse {openapi_url}: {exc}", file=sys.stderr)
        return 2

    paths = data.get("paths") or {}
    has_route = route_path in paths
    print(f"OPENAPI_URL={openapi_url}")
    print(f"ROUTE_PATH={route_path}")
    print(f"HAS_ROUTE={str(has_route).lower()}")
    return 0 if has_route else 1


if __name__ == "__main__":
    raise SystemExit(main())
