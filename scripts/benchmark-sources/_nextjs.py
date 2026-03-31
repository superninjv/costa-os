"""
Shared utility for extracting JSON data from Next.js server-side rendered pages.

Two common patterns:
  1. <script id="__NEXT_DATA__"> — classic Next.js RSC payload
  2. self.__next_f.push([index, payload]) — App Router flight data
"""

import re
import json
import sys


def extract_nextjs_data(html: str) -> list[dict]:
    """
    Extract JSON data from a Next.js page.

    Returns a list of parsed JSON objects found via either extraction strategy.
    The list may be empty if neither pattern is found or all parses fail.
    """
    results = []

    # --- Pattern 1: classic __NEXT_DATA__ script tag ---
    match = re.search(
        r'<script\s+id=["\']__NEXT_DATA__["\'][^>]*>\s*(.*?)\s*</script>',
        html,
        re.DOTALL,
    )
    if match:
        try:
            results.append(json.loads(match.group(1)))
        except json.JSONDecodeError as exc:
            print(f"[_nextjs] __NEXT_DATA__ parse error: {exc}", file=sys.stderr)

    # --- Pattern 2: self.__next_f.push([index, payload_string]) ---
    # The App Router serialises RSC payloads as an array where index 0 is a
    # small integer and index 1 is either a raw JSON string or a JSON-like
    # string that starts with specific type prefixes.
    for raw in re.finditer(
        r'self\.__next_f\.push\(\s*\[(.*?)\]\s*\)',
        html,
        re.DOTALL,
    ):
        inner = raw.group(1).strip()
        # Split on the first comma to separate index from payload
        comma_pos = inner.find(",")
        if comma_pos == -1:
            continue
        payload_raw = inner[comma_pos + 1:].strip()

        # The payload is itself a JSON-encoded string (i.e. a string whose
        # value is more JSON).  Strip the outer string quotes first.
        if payload_raw.startswith('"') or payload_raw.startswith("'"):
            try:
                # Decode the outer string layer
                outer = json.loads(payload_raw)
            except json.JSONDecodeError:
                # Try stripping quotes manually
                outer = payload_raw.strip('"\'')
        else:
            outer = payload_raw

        if not isinstance(outer, str):
            # Already a dict/list — keep as-is
            if isinstance(outer, (dict, list)):
                results.append(outer)
            continue

        # The RSC flight format prefixes each line with a type byte.
        # Lines that begin with digits (row index + colon) carry JSON data.
        # Try parsing each colon-delimited row.
        for line in outer.splitlines():
            colon_pos = line.find(":")
            if colon_pos == -1:
                continue
            data_part = line[colon_pos + 1:].strip()
            if not data_part or data_part[0] not in "{[\"":
                continue
            try:
                parsed = json.loads(data_part)
                if isinstance(parsed, (dict, list)):
                    results.append(parsed)
            except json.JSONDecodeError:
                pass

    return results


def flatten_nextjs_data(items: list) -> list[dict]:
    """
    Recursively flatten a list of parsed Next.js payloads into a flat list
    of leaf dict objects.  Useful for searching for model/score keys.
    """
    flat = []
    stack = list(items)
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            flat.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return flat
