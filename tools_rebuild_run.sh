#!/usr/bin/env bash
# Single-slot/single-native-thread command capture for formal rebuild calls.
set -euo pipefail
if [[ $# -lt 3 ]]; then
  echo "usage: $0 RUN_ID WALL_SECONDS COMMAND [ARGS...]" >&2
  exit 64
fi
run_id=$1
wall_seconds=$2
shift 2
root=$(cd "$(dirname "$0")" && pwd)
out="$root/runs/supervised/$run_id"
mkdir -p "$out"
exec 9>/tmp/hiroute-r0-r4-numeric-worker.lock
if ! flock -n 9; then
  echo "another rebuild worker holds the single-worker lock" >&2
  exit 75
fi
python3 - "$root/runs/rebuild_budget.json" "$run_id" <<'PY'
import json,sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text())
a=d.get("accounting",{})
spent=sum(float(a.get(k,0)) for k in ("measured_cpu_seconds","estimated_cpu_seconds","reserved_cpu_seconds"))
if spent >= float(d["budget_cpu_hours"])*3600:
    raise SystemExit("24 CPU-hour rebuild budget is exhausted")
PY
python3 - "$out/command.json" "$@" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"argv":sys.argv[2:]},indent=2)+"\n")
PY
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
cpu=$(taskset -pc $$ | sed 's/.*: //' | cut -d, -f1 | cut -d- -f1)
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'started_at=%s\n' "$start" > "$out/timing.txt"
set +e
/usr/bin/time -v -o "$out/time.txt" timeout --signal=TERM --kill-after=5 "$wall_seconds" taskset -c "$cpu" "$@" > "$out/stdout.log" 2> "$out/stderr.log"
status=$?
set -e
end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'finished_at=%s\nexit_code=%s\ncpu_affinity=%s\n' "$end" "$status" "$cpu" >> "$out/timing.txt"
python3 - "$root/runs/rebuild_budget.json" "$run_id" "$status" "$out" <<'PY'
import json,re,sys
from pathlib import Path
ledger=Path(sys.argv[1]); run_id=sys.argv[2]; status=int(sys.argv[3]); out=Path(sys.argv[4])
d=json.loads(ledger.read_text())
timing=(out/"time.txt").read_text()
u=re.search(r"User time \(seconds\): ([0-9.]+)",timing)
s=re.search(r"System time \(seconds\): ([0-9.]+)",timing)
cpu=round(float(u.group(1))+float(s.group(1)),3) if u and s else None
row={"run_id":run_id,"measured_cpu_seconds":cpu,"exit_code":status,"evidence":str(out.relative_to(ledger.parent.parent))}
d.setdefault("accounting",{}).setdefault("measured_cpu_seconds",0)
if cpu is not None:
    d["accounting"]["measured_cpu_seconds"]=round(d["accounting"]["measured_cpu_seconds"]+cpu,3)
d.setdefault("runs",[]).append(row)
ledger.write_text(json.dumps(d,indent=2)+"\n")
PY
exit "$status"
