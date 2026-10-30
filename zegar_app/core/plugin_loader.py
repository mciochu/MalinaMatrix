"""Safe, explicit loading of opt-in local extensions."""
import importlib
import re

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_ALLOWED_KINDS = {"screens", "sensors", "modules"}


def load_extension(kind, name):
    """Load one package-local extension by name; never scan/import directories."""
    if kind not in _ALLOWED_KINDS or not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise ValueError("Invalid extension name or type")
    return importlib.import_module(f"zegar_app.extensions.{kind}.{name}")
