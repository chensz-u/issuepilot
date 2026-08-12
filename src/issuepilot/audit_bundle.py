import hashlib
import io
import json
import zipfile

from issuepilot.investigation_domain import Investigation, InvestigationEvent


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def build_audit_bundle(investigation: Investigation, events: list[InvestigationEvent]) -> bytes:
    files = {
        "events.json": _json_bytes([event.model_dump(mode="json") for event in events]),
        "investigation.json": _json_bytes(investigation.model_dump(mode="json")),
    }
    manifest = {
        "schema": "issuepilot-audit-v1",
        "investigation_id": investigation.id,
        "repository": investigation.repository.full_name,
        "contains_user_input": True,
        "sha256": {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()},
    }
    files["manifest.json"] = _json_bytes(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()
