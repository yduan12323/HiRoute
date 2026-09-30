"""Exercise exclusive raw writes, checksum pinning and manifest restoration."""
import hashlib
from io import BytesIO
import struct
import sys
import zlib

import pytest
import yaml

import download_data


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(number, value):
    if isinstance(value, bytes):
        return varint(number * 8 + 2) + varint(len(value)) + value
    return varint(number * 8) + varint(value)


def fixture_pbf():
    header = field(32, 1790713371)
    blob = field(2, len(header)) + field(3, zlib.compress(header))
    blob_header = field(1, b"OSMHeader") + field(3, len(blob))
    return struct.pack(">I", len(blob_header)) + blob_header + blob


@pytest.fixture
def acquisition(tmp_path, monkeypatch):
    data = {"dataset": {"region": "fixture", "source_url": "https://example.test/fixture-260929.osm.pbf",
                        "checksum_url": "https://example.test/fixture.md5", "raw_path": "data/raw/osm/fixture.osm.pbf",
                        "manifest_path": "data/raw/DATA_MANIFEST.yaml", "sha256": None},
            "seed": 1}
    monkeypatch.setattr(download_data, "ROOT", tmp_path)
    monkeypatch.setattr(download_data, "configs", lambda *args: (data, {}))
    monkeypatch.setattr(download_data, "record_run", lambda *args: {})
    monkeypatch.setattr(sys, "argv", ["download_data.py"])
    (tmp_path / "configs").mkdir()
    payload = fixture_pbf()

    def response(url, timeout):
        if url.endswith(".md5"):
            stream = BytesIO(hashlib.md5(payload).hexdigest().encode() + b"  fixture.osm.pbf")
            stream.headers = {}
        else:
            stream = BytesIO(payload)
            stream.headers = {"Content-Length": str(len(payload))}
        return stream

    monkeypatch.setattr(download_data.urllib.request, "urlopen", response)
    return tmp_path, data, payload


def test_download_and_manifest_preserved_on_restore(acquisition):
    root, data, payload = acquisition
    download_data.main()
    raw = root / data["dataset"]["raw_path"]
    manifest = root / data["dataset"]["manifest_path"]
    assert raw.read_bytes() == payload
    assert raw.stat().st_mode & 0o222 == 0
    assert data["dataset"]["sha256"] == hashlib.sha256(payload).hexdigest()
    original_manifest = manifest.read_bytes()
    assert yaml.safe_load(original_manifest)["dataset"]["osm_snapshot_timestamp"] is not None
    raw.unlink()
    download_data.main()
    assert raw.read_bytes() == payload
    assert manifest.read_bytes() == original_manifest


def test_bad_sha_never_publishes_raw(acquisition):
    root, data, _ = acquisition
    data["dataset"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="pinned"):
        download_data.main()
    assert not (root / data["dataset"]["raw_path"]).exists()


def test_existing_partial_not_removed(acquisition):
    root, data, _ = acquisition
    partial = (root / data["dataset"]["raw_path"]).with_suffix(".pbf.partial")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"another process owns this")
    with pytest.raises(FileExistsError):
        download_data.main()
    assert partial.read_bytes() == b"another process owns this"
