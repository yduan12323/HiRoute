"""Freeze a small Geofabrik polygon solely for boundary diagnostics."""
import argparse
from datetime import datetime, timezone
import json
import urllib.request

import yaml

from _common import ROOT, sha256
from _envelope_common import envelope_config, envelope_run
from envelope.boundary import read_poly


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/envelope.yaml")
    args = parser.parse_args()
    config = envelope_config(args.config)
    _, _, run = envelope_run("boundary_download", config)
    boundary = config["boundary"]
    path = ROOT / boundary["path"]
    metadata_path = path.with_suffix(".metadata.json")
    if path.exists():
        metadata = json.loads(metadata_path.read_text())
        if sha256(path) != boundary["sha256"] or metadata["sha256"] != boundary["sha256"]:
            raise ValueError("Frozen polygon checksum mismatch")
        read_poly(path)
        print("Verified existing frozen boundary; no replacement")
        return
    with urllib.request.urlopen(boundary["source_url"], timeout=120) as response:
        payload = response.read()
        modified = response.headers.get("Last-Modified")
    import hashlib
    digest = hashlib.sha256(payload).hexdigest()
    if boundary["sha256"] and digest != boundary["sha256"]:
        raise ValueError("Publisher polygon changed; restore the archived frozen polygon")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
    read_poly(path)
    path.chmod(0o444)
    if not metadata_path.exists():
        metadata_path.write_text(json.dumps({"source_url": boundary["source_url"], "sha256": digest,
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(), "http_last_modified": modified,
            "scope": "Approximate extract boundary; publisher polygon is not PBF-date versioned.", "run": run}, indent=2) + "\n")
    if not boundary["sha256"]:
        boundary["sha256"] = digest
        (ROOT / args.config).write_text(yaml.safe_dump(config, sort_keys=False))
    envelope_run("boundary_download_complete", config)
    print(f"Frozen boundary SHA256: {digest}")


if __name__ == "__main__":
    main()
