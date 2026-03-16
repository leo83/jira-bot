#!/usr/bin/env python3
"""
Output the next version based on existing tags in the registry.

Usage:
  python next_rc_version.py        -> next RC version (e.g. 20260224.5.rc)
  python next_rc_version.py --prod  -> next prod version (e.g. 20260224.5)

Uses Docker Registry V2 API. Requires docker login for private registries.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REGISTRY = "proget.aeroclub.ru"
REPOSITORY = "aeroclub-infrastructure/library/services-ai-jira-bot"
IMAGE = f"{REGISTRY}/{REPOSITORY}"


def _get_docker_auth(registry: str) -> tuple[str, str] | None:
    config_path = Path(
        os.environ.get("DOCKER_CONFIG", "~/.docker/config.json")
    ).expanduser()
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
        auths = data.get("auths") or {}
        entry = auths.get(registry) or auths.get(f"https://{registry}")
        if not entry or "auth" not in entry:
            return None
        decoded = base64.b64decode(entry["auth"]).decode()
        if ":" in decoded:
            user, _, password = decoded.partition(":")
            return (user, password)
    except Exception:
        pass
    return None


def _fetch_tags(registry: str, repository: str) -> list[str]:
    base = f"https://{registry}"
    tags_url = f"{base}/v2/{repository}/tags/list"
    headers: dict[str, str] = {}

    auth = _get_docker_auth(registry)
    if auth:
        user, password = auth
        b64 = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {b64}"

    try:
        req = Request(tags_url, headers=headers)
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("tags") or []
    except HTTPError as e:
        if e.code == 401 and "Www-Authenticate" in (e.headers or {}):
            # Try to get Bearer token
            auth_header = e.headers.get("Www-Authenticate", "")
            if "realm=" in auth_header:
                import urllib.parse

                realm = re.search(r'realm="([^"]+)"', auth_header)
                service = re.search(r'service="([^"]*)"', auth_header)
                scope = re.search(r'scope="([^"]*)"', auth_header)
                if realm:
                    token_url = realm.group(1)
                    params = []
                    if service:
                        params.append(f"service={service.group(1)}")
                    if scope:
                        params.append(f"scope={scope.group(1)}")
                    if params:
                        token_url += "&" if "?" in token_url else "?" + "&".join(params)
                    token_req = Request(token_url, headers=headers)
                    with urlopen(token_req, timeout=15) as token_resp:
                        token_data = json.loads(token_resp.read().decode())
                        token = token_data.get("token")
                        if token:
                            headers["Authorization"] = f"Bearer {token}"
                            req = Request(tags_url, headers=headers)
                            with urlopen(req, timeout=15) as resp:
                                data = json.loads(resp.read().decode())
                                return data.get("tags") or []
        raise
    except Exception as e:
        print(f"Error fetching tags from {registry}: {e}", file=sys.stderr)
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Get next version from registry")
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Production format: YYYYMMDD.N (default: RC format YYYYMMDD.N.rc)",
    )
    args = parser.parse_args()

    today = date.today().strftime("%Y%m%d")
    suffix = "" if args.prod else ".rc"
    # Match YYYYMMDD.N or YYYYMMDD.N.rc
    pattern = re.compile(rf"^{re.escape(today)}\.(\d+)(?:\.rc)?$")

    tags = _fetch_tags(REGISTRY, REPOSITORY)
    max_num = 0
    for tag in tags:
        m = pattern.match(tag)
        if m:
            max_num = max(max_num, int(m.group(1)))

    next_num = max_num + 1
    print(f"{today}.{next_num}{suffix}")


if __name__ == "__main__":
    main()
