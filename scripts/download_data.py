"""Acquire one dated Geofabrik PBF; never replace an existing raw file."""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import urllib.request
import zlib
from datetime import datetime, timezone

import yaml

from _common import ROOT, configs, record_run, sha256, verified_dataset


def protobuf_fields(data: bytes) -> dict:
    """Read scalar/byte fields of the small PBF header, not OSM entities."""
    pos, fields = 0, {}

    def varint() -> int:
        nonlocal pos
        value, shift = 0, 0
        while True:
            byte = data[pos]
            pos += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7
            if shift > 63:
                raise ValueError("Malformed protobuf varint")

    while pos < len(data):
        key = varint()
        field, wire = key >> 3, key & 7
        if wire == 0:
            value = varint()
        elif wire == 2:
            length = varint()
            value = data[pos:pos + length]
            pos += length
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            value = data[pos:pos + length]
            pos += length
        else:
            raise ValueError("Unsupported PBF header wire type")
        fields[field] = value
    return fields


def snapshot_timestamp(path) -> str | None:
    with path.open("rb") as stream:
        size = struct.unpack(">I", stream.read(4))[0]
        if not 0 < size < 65536:
            raise ValueError("Invalid PBF header length")
        header = protobuf_fields(stream.read(size))
        if header[1] != b"OSMHeader":
            raise ValueError("Missing OSMHeader")
        blob = protobuf_fields(stream.read(header[3]))
    payload = blob.get(1) if 1 in blob else zlib.decompress(blob[3])
    timestamp = protobuf_fields(payload).get(32)
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-config", default="configs/data.yaml")
    args = parser.parse_args()
    data, _ = configs(args.data_config)
    dataset = data["dataset"]
    path = ROOT / dataset["raw_path"]
    manifest_path = ROOT / dataset["manifest_path"]
    if "latest" in dataset["source_url"]:
        raise ValueError("Use a dated URL, never a moving latest URL")
    if path.exists():
        frozen = verified_dataset(data)
        record_run("download_verify", data, None, data["seed"])
        print(f"Verified immutable snapshot: {frozen['sha256']}")
        return
    existing_manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else None
    if existing_manifest:
        frozen = existing_manifest["dataset"]
        for key in ["source_url", "raw_path", "sha256"]:
            if frozen[key] != dataset[key]:
                raise ValueError(f"Frozen manifest/configuration mismatch: {key}")
    record_run("download_start", data, None, data["seed"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    md5 = hashlib.md5()
    created_temporary = False
    try:
        with urllib.request.urlopen(dataset["source_url"], timeout=120) as response, temporary.open("xb") as stream:
            created_temporary = True
            headers = dict(response.headers)
            content_length = response.headers.get("Content-Length")
            while block := response.read(8 * 1024 * 1024):
                stream.write(block)
                md5.update(block)
                print(f"Downloaded {stream.tell() / 1e6:.1f} MB", flush=True)
        if content_length and temporary.stat().st_size != int(content_length):
            raise ValueError("Incomplete HTTP download")
        with urllib.request.urlopen(dataset["checksum_url"], timeout=120) as response:
            expected_md5 = response.read().decode().split()[0]
        if md5.hexdigest() != expected_md5:
            raise ValueError("Geofabrik MD5 verification failed")
        digest = sha256(temporary)
        if dataset.get("sha256") and dataset["sha256"] != digest:
            raise ValueError("Downloaded PBF differs from pinned SHA256")
        metadata = dict(dataset)
        metadata.update({"sha256": digest, "file_name": path.name, "size_bytes": temporary.stat().st_size,
                         "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                         "osm_snapshot_timestamp": snapshot_timestamp(temporary),
                         "geofabrik_md5": expected_md5, "http_last_modified": headers.get("Last-Modified"),
                         "license": "ODbL-1.0", "attribution": "OpenStreetMap contributors; extract by Geofabrik"})
        # Hard link is exclusive: it cannot replace an existing raw path.
        os.link(temporary, path)
        path.chmod(0o444)
        if not existing_manifest:
            with manifest_path.open("x") as stream:
                yaml.safe_dump({"schema_version": 1, "dataset": metadata}, stream, sort_keys=False)
        if not data["dataset"].get("sha256"):
            data["dataset"]["sha256"] = digest
            (ROOT / args.data_config).write_text(yaml.safe_dump(data, sort_keys=False))
    finally:
        # Remove only the temporary file created by this invocation.
        if created_temporary and temporary.exists():
            temporary.unlink()
    record_run("download_complete", data, None, data["seed"])
    print(yaml.safe_dump(metadata, sort_keys=False))


if __name__ == "__main__":
    main()
