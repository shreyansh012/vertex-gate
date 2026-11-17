"""A tiny model registry kept in one JSON file.

Shape of the file:

    {"deployed": null or "v1",
     "versions": [{"version": "v1", "metrics": {"rmse": 1.2}}]}
"""

import json
import os
import tempfile


class RegistryError(Exception):
    """The registry file is missing, unreadable or has the wrong shape."""


def new_registry():
    return {"deployed": None, "versions": []}


def validate(reg):
    """Check the outer shape. Raise RegistryError if it is wrong."""
    if not isinstance(reg, dict):
        raise RegistryError("registry must be a JSON object")
    versions = reg.get("versions")
    if not isinstance(versions, list):
        raise RegistryError("'versions' must be a list")
    seen = set()
    for item in versions:
        if not isinstance(item, dict) or not isinstance(item.get("version"), str):
            raise RegistryError("each version needs a text 'version' field")
        name = item["version"]
        if name in seen:
            raise RegistryError("duplicate version: " + name)
        seen.add(name)
    deployed = reg.get("deployed")
    if deployed is not None and not isinstance(deployed, str):
        raise RegistryError("'deployed' must be null or a version name")
    return reg


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            reg = json.load(handle)
    except (OSError, ValueError) as exc:
        raise RegistryError("cannot read registry: %s" % exc) from exc
    return validate(reg)


def save(path, reg):
    """Write the registry in one step so a process crash cannot leave half a file."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(reg, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def add_version(reg, version, metrics):
    if any(v.get("version") == version for v in reg["versions"]):
        raise RegistryError("version already registered: " + version)
    reg["versions"].append({"version": version, "metrics": dict(metrics)})
    return reg


def find(reg, version):
    for item in reg["versions"]:
        if item.get("version") == version:
            return item
    return None
