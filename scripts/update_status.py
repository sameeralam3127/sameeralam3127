#!/usr/bin/env python3
"""Check the live tool sites and write a status table into README.md.

The table goes between <!-- STATUS:START --> and <!-- STATUS:END -->.
The block is only rewritten when a tool changes state (up/down) or the
previous check is older than STATUS_REFRESH_HOURS, so scheduled runs don't
produce a commit every time just because the timestamp moved.

Usage: python3 scripts/update_status.py [README.md]
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

TOOLS = [
    ("IPMG", "https://sameeralam3127.github.io/ipmg/"),
    ("KubeRescue", "https://sameeralam3127.github.io/KubeRescue/"),
    ("Linux Vitals", "https://sameeralam3127.github.io/linux-vitals/"),
]

START = "<!-- STATUS:START -->"
END = "<!-- STATUS:END -->"
STATE_RE = re.compile(r"<!-- status-state: (\{.*?\}) -->")
REFRESH = timedelta(hours=float(os.environ.get("STATUS_REFRESH_HOURS", "24")))
TIME_FMT = "%Y-%m-%d %H:%M"


def check(url):
    """Return (http_code, response_ms) using curl: 15s timeout, 2 retries."""
    result = subprocess.run(
        [
            "curl", "-s", "-o", "/dev/null", "-L",
            "--max-time", "15",
            "--retry", "2", "--retry-delay", "2", "--retry-all-errors",
            "-w", "%{http_code} %{time_total}",
            url,
        ],
        capture_output=True,
        text=True,
    )
    try:
        code, seconds = result.stdout.split()
        return int(code), round(float(seconds) * 1000)
    except ValueError:
        return 0, None


def render(results, checked):
    state = {name: up for name, _, _, _, up in results}
    lines = [
        START,
        f"<!-- status-state: {json.dumps({'checked': checked, 'up': state})} -->",
        "| Tool | Status | Response ms | Last checked (UTC) |",
        "| --- | --- | --- | --- |",
    ]
    for name, url, code, ms, up in results:
        status = "🟢 Up" if up else f"🔴 Down ({code or 'no response'})"
        lines.append(f"| [{name}]({url}) | {status} | {ms if ms is not None else '–'} | {checked} |")
    lines.append(END)
    return "\n".join(lines)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "README.md"
    with open(path, encoding="utf-8") as f:
        readme = f.read()

    if readme.count(START) != 1 or readme.count(END) != 1 or readme.index(START) > readme.index(END):
        print(f"::error file={path}::expected exactly one {START} ... {END} block", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    checked = now.strftime(TIME_FMT)
    results = []
    for name, url in TOOLS:
        code, ms = check(url)
        up = 200 <= code < 400
        results.append((name, url, code, ms, up))
        print(f"{name}: {code or 'no response'} {ms} ms {'up' if up else 'DOWN'}")

    block_start = readme.index(START)
    block_end = readme.index(END) + len(END)
    old_block = readme[block_start:block_end]

    match = STATE_RE.search(old_block)
    if match:
        previous = json.loads(match.group(1))
        last = datetime.strptime(previous["checked"], TIME_FMT).replace(tzinfo=timezone.utc)
        same_state = previous["up"] == {name: up for name, _, _, _, up in results}
        if same_state and now - last < REFRESH:
            print("No state change and last check is recent; leaving README untouched.")
            return 0

    with open(path, "w", encoding="utf-8") as f:
        f.write(readme[:block_start] + render(results, checked) + readme[block_end:])
    print("Status block updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
