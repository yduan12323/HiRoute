"""Render and preflight a caller-supplied HiRoute input and resource profile."""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, tempfile
from fractions import Fraction
from pathlib import Path

_SHA = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(value, parameters):
    if isinstance(value, str):
        match = _PLACEHOLDER.fullmatch(value)
        if match:
            key = match.group(1)
            if key not in parameters:
                raise ValueError(f"missing parameter {key}")
            return parameters[key]
        if "${" in value:
            raise ValueError("placeholder must occupy the complete string value")
        return value
    if isinstance(value, list):
        return [render(item, parameters) for item in value]
    if isinstance(value, dict):
        return {key: render(item, parameters) for key, item in value.items()}
    return value


def rational(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{field} must be an exact string or integer")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{field} must be a finite rational") from exc


def resolve_file(ref, root, name):
    if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
        raise ValueError(f"{name}.path is required")
    expected = ref.get("sha256")
    if not isinstance(expected, str) or not _SHA.fullmatch(expected):
        raise ValueError(f"{name}.sha256 must be lowercase SHA-256")
    path = Path(ref["path"])
    path = path if path.is_absolute() else root / path
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"{name} is not a regular file")
    actual = digest(path.read_bytes())
    if actual != expected:
        raise ValueError(f"{name} checksum mismatch")
    return path


def validate_request(request, root):
    if not isinstance(request, dict) or request.get("schema") != "hiroute.run_request.v1":
        raise ValueError("unsupported request schema")
    raw = resolve_file(request.get("raw_source"), root, "raw_source")
    boundary = resolve_file(request.get("boundary"), root, "boundary")
    routing = resolve_file(request.get("routing_config"), root, "routing_config")
    try:
        policy = json.loads(routing.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("routing config must be UTF-8 JSON") from exc
    if not all(key in policy for key in ("access", "speed_model", "attachment", "site_policy")):
        raise ValueError("routing config lacks required public policy sections")
    model = request.get("model")
    if not isinstance(model, dict) or type(model.get("H_ref")) is not int or model["H_ref"] < 1:
        raise ValueError("model.H_ref must be a positive integer")
    for key in ("capacity_kwh", "initial_energy_kwh", "minimum_energy_kwh", "consumption_kwh_per_m"):
        v = rational(model.get(key), f"model.{key}")
        if v < 0 or (key in {"capacity_kwh", "consumption_kwh_per_m"} and v == 0):
            raise ValueError(f"model.{key} is outside its positive domain")
    segments = model.get("charging_segments")
    if not isinstance(segments, list) or len(segments) < 2:
        raise ValueError("model.charging_segments needs at least two exact points")
    previous_t = previous_e = None
    for index, pair in enumerate(segments):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("each charging segment point must be [energy, time]")
        energy = rational(pair[0], f"charging_segments[{index}].energy")
        time = rational(pair[1], f"charging_segments[{index}].time")
        if energy < 0 or time < 0 or (previous_e is not None and energy <= previous_e) or (previous_t is not None and time < previous_t):
            raise ValueError("charging curve points must increase in energy and not decrease in time")
        previous_e, previous_t = energy, time
    queries = request.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("queries must be a nonempty array")
    ids = set()
    for i, query in enumerate(queries):
        if not isinstance(query, dict) or not isinstance(query.get("id"), str) or not query["id"] or query["id"] in ids:
            raise ValueError("query IDs must be nonempty and unique")
        ids.add(query["id"])
        for endpoint in ("origin", "destination"):
            point = query.get(endpoint)
            if not isinstance(point, dict) or not isinstance(point.get("osm_identity"), str) or not point["osm_identity"]:
                raise ValueError(f"query[{i}].{endpoint} needs an OSM identity")
            coords = point.get("coordinates_lon_lat")
            if not isinstance(coords, list) or len(coords) != 2:
                raise ValueError(f"query[{i}].{endpoint} needs lon/lat")
            lon, lat = (rational(v, f"query[{i}].{endpoint}.coordinate") for v in coords)
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("endpoint coordinates out of range")
        candidates = query.get("candidate_site_ids")
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 4 or any(not isinstance(x, str) or not x for x in candidates) or len(set(candidates)) != len(candidates):
            raise ValueError("candidate_site_ids must contain one to four unique nonempty IDs in supplied order")
        if "initial_remaining_schedule" in query and (type(query["initial_remaining_schedule"]) is not int or query["initial_remaining_schedule"] not in (0, 1)):
            raise ValueError("initial_remaining_schedule must be explicitly 0 or 1")
        schedule = query.get("schedule")
        if schedule is not None:
            if not isinstance(schedule, dict) or not all(k in schedule for k in ("a", "b", "D")):
                raise ValueError("schedule requires a, b, and D")
            a, b, d = (rational(schedule[k], f"query[{i}].schedule.{k}") for k in ("a", "b", "D"))
            if a > b or d <= 0:
                raise ValueError("schedule requires a <= b and D > 0")
    return {"raw_source": str(raw), "boundary": str(boundary), "routing_config": str(routing)}


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get("schema") != "hiroute.resource_profile.v1":
        raise ValueError("unsupported resource profile schema")
    for key in ("wall_limit_seconds", "cpu_limit_seconds", "memory_limit_bytes"):
        if type(profile.get(key)) is not int or profile[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    for key in ("host_headroom_bytes", "growth_margin_bytes"):
        if type(profile.get(key)) is not int or profile[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer")


def system_mem_available_bytes():
    info = Path("/proc/meminfo")
    if not info.is_file():
        raise RuntimeError("host memory admission requires Linux /proc/meminfo")
    match = re.search(r"^MemAvailable:\s+(\d+)\s+kB$", info.read_text(), re.M)
    if not match:
        raise RuntimeError("MemAvailable could not be read; fail closed")
    return int(match.group(1)) * 1024


def make_admission(request, profile, available_bytes):
    validate_profile(profile)
    required = profile["memory_limit_bytes"] + profile["host_headroom_bytes"] + profile["growth_margin_bytes"]
    request_sha, profile_sha = digest(canonical(request)), digest(canonical(profile))
    return {
        "schema": "hiroute.run_admission.v1",
        "status": "admitted" if required <= available_bytes else "insufficient_headroom",
        "request_sha256": request_sha,
        "profile_sha256": profile_sha,
        "sampled_mem_available_bytes": available_bytes,
        "memory_limit_bytes": profile["memory_limit_bytes"],
        "host_headroom_bytes": profile["host_headroom_bytes"],
        "growth_margin_bytes": profile["growth_margin_bytes"],
        "required_mem_available_bytes": required,
        "admission_is_snapshot_not_runtime_enforcement": True,
    }


def prepare(request_template, profile_template, parameters, root, available_bytes):
    request = render(request_template, parameters)
    profile = render(profile_template, parameters)
    unresolved = json.dumps([request, profile])
    if "${" in unresolved:
        raise ValueError("unresolved template placeholder")
    resolved = validate_request(request, root)
    for key in ("raw_source", "boundary", "routing_config"):
        request[key]["path"] = resolved[key]
    validate_profile(profile)
    return request, profile, make_admission(request, profile, available_bytes)


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            body = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False).encode() + b"\n"
            f.write(body); f.flush(); os.fsync(f.fileno())
        os.link(name, path); os.unlink(name)
    except BaseException:
        try: os.unlink(name)
        except FileNotFoundError: pass
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--request-template", required=True)
    p.add_argument("--profile-template", required=True)
    p.add_argument("--parameters", required=True)
    p.add_argument("--root", default=".")
    p.add_argument("--output-dir", required=True)
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    request_template = json.loads(Path(a.request_template).read_text())
    profile_template = json.loads(Path(a.profile_template).read_text())
    parameters = json.loads(Path(a.parameters).read_text())
    request, profile, admission = prepare(request_template, profile_template, parameters, root, system_mem_available_bytes())
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / "request.json", request)
    write_new(out / "resource-profile.json", profile)
    write_new(out / "admission.json", admission)
    print(json.dumps({"status": admission["status"], "output_files": 3}, sort_keys=True))
    return 0 if admission["status"] == "admitted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
