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

# Every configurable option exposed by the dashboard must have a label in
# every supported language. This catches dynamic keys that static JS scanning
# cannot see (for example config.field.<section>.<key>).
EXAMPLE_CONFIG = ROOT / "zegar.conf.example"
if EXAMPLE_CONFIG.exists():
    section = None
    for line in EXAMPLE_CONFIG.read_text(encoding="utf-8").splitlines():
        header = re.match(r"\\s*\\[([^]]+)\\]", line)
        if header:
            section = header.group(1).strip()
            continue
        option = re.match(r"\\s*([A-Za-z0-9_.-]+)\\s*=", line)
        if section and option:
            key = f"config.field.{section}.{option.group(1)}"
            for code, dictionary in dictionaries.items():
                if key not in dictionary:
                    fail(f"{code}: missing dashboard setting label {key}")

required_ui_keys = [
    "config.title", "config.subtitle", "config.search", "config.reload",
    "config.expand", "config.collapse", "config.loading",
    "config.position.title", "config.position.help", "config.position.foot",
    "ui.weatherTest.title", "ui.weatherTest.copy",
]
for code, dictionary in dictionaries.items():
    missing = [key for key in required_ui_keys if key not in dictionary]
    if missing:
        fail(f"{code}: missing dashboard UI translations {missing}")

source_files = [WEB / "i18n.js", WEB / "message-studio.js", WEB / "index.html"]
references = set()
for source in source_files:
    if source.exists():
        references.update(REFERENCE_RE.findall(source.read_text(encoding="utf-8")))
dynamic_prefixes = {'range.', 'duration.'}
unknown = sorted(ref for ref in references - fallback_keys if ref not in dynamic_prefixes)
if unknown:
    fail(f"translation references without dictionary entries: {unknown}")

print(f"[locales] OK: {len(codes)} languages, {len(fallback_keys)} matching keys, {len(references)} static references.")
print(f"[locales] Default: {config['defaultLanguage']}; fallback: {fallback_code}.")
