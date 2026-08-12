from importlib.metadata import metadata

REQUIRED_LICENSES = {
    "langgraph": {"MIT"},
    "langgraph-checkpoint-sqlite": {"MIT"},
    "rank-bm25": {"Apache2.0", "Apache-2.0"},
}


def audit_required_licenses() -> dict[str, str]:
    observed = {}
    for package, allowed in REQUIRED_LICENSES.items():
        package_metadata = metadata(package)
        license_name = package_metadata.get("License-Expression") or package_metadata.get("License")
        if license_name not in allowed:
            raise RuntimeError(f"{package} has unexpected license: {license_name}")
        observed[package] = str(license_name)
    return observed


def main() -> None:
    for package, license_name in audit_required_licenses().items():
        print(f"{package}: {license_name}")
