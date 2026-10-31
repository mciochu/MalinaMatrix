#!/usr/bin/env python3
"""Validate dashboard locale configuration, dictionaries and translation references."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
CONFIG_PATH = WEB / "config" / "languages.json"
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")
REFERENCE_RE = re.compile(r"(?:\bt|\btr)\(\s*['\"]([^'\"]+)['\"]")

def fail(message: str) -> None:
    print(f"[locales] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)

try:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"cannot read {CONFIG_PATH}: {exc}")

languages = config.get("languages")
if not isinstance(languages, list) or not languages:
    fail("config.languages must be a non-empty array")

codes = [item.get("code") for item in languages]
if len(codes) != len(set(codes)):
    fail("language codes must be unique")
for field in ("defaultLanguage", "fallbackLanguage"):
    if config.get(field) not in codes:
        fail(f"{field} must refer to a configured language")

dictionaries = {}
for item in languages:
    code = item["code"]
    path = WEB / "locales" / f"{code}.json"
    try:
        dictionary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read locale {code}: {exc}")
    if not isinstance(dictionary, dict):
        fail(f"locale {code} must be a JSON object")
    dictionaries[code] = dictionary

fallback_code = config["fallbackLanguage"]
fallback_keys = set(dictionaries[fallback_code])
for code, dictionary in dictionaries.items():
    keys = set(dictionary)
    missing = sorted(fallback_keys - keys)
    extra = sorted(keys - fallback_keys)
    if missing or extra:
        fail(f"{code}: missing keys={missing}; extra keys={extra}")
    for key in sorted(fallback_keys):
        base_vars = set(PLACEHOLDER_RE.findall(str(dictionaries[fallback_code][key])))
        vars_here = set(PLACEHOLDER_RE.findall(str(dictionary[key])))
        if base_vars != vars_here:
            fail(f"{code}.{key}: placeholder mismatch {base_vars} != {vars_here}")

source_files = [WEB / "i18n.js", WEB / "message-studio.js", WEB / "index.html"]
references = set()
for source in source_files:
    if source.exists():
        references.update(REFERENCE_RE.findall(source.read_text(encoding="utf-8")))
dynamic_prefixes = {'range.', 'duration.'}\nunknown = sorted(ref for ref in references - fallback_keys if ref not in dynamic_prefixes)
if unknown:
    fail(f"translation references without dictionary entries: {unknown}")

print(f"[locales] OK: {len(codes)} languages, {len(fallback_keys)} matching keys, {len(references)} static references.")
print(f"[locales] Default: {config['defaultLanguage']}; fallback: {fallback_code}.")
