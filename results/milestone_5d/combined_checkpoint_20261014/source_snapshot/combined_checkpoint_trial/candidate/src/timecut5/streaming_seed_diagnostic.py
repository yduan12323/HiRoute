"""Explicit streaming-only diagnostic entrypoint; never invokes an exact solver."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class StreamingSeedObserver:
    """Constant proposal memory and bounded durable journal; snapshots replace.

    Timers come from active computation hooks, never callback wall time. A
    incomplete digest is explicitly a JSON-array prefix, not a completed list.
    """
    def __init__(self, query, catalog, *, output_dir, provenance,
                 checkpoint_seconds=5, max_journal_events=128):
        if (type(checkpoint_seconds) not in (int, float) or
                not math.isfinite(checkpoint_seconds) or checkpoint_seconds <= 0 or
                type(max_journal_events) is not int or not 2 <= max_journal_events <= 4096):
            raise ValueError("Positive checkpoint interval and journal limit 2..4096 required")
        self.output = Path(output_dir)
        self.output.mkdir(parents=True, exist_ok=False)
        self.provider = catalog.provider
        source = Path(__file__).parent
        self.state = dict(schema="hiroute.streaming_seed_diagnostic.v1",
            run_id=uuid.uuid4().hex, status="incomplete", generation_complete=False,
            canonical_query_sha256=digest(query), domain_sha256=catalog.domain_sha256,
            source_sha256=dict(catalog.provider.source_sha256),
            graph_node_count=catalog.provider.graph.node_count,
            native_stage_visibility="unavailable; active stages cover whole generation/replay calls",
            cache_configuration={name:getattr(catalog.provider,name) for name in
                ("source_cache_max_bytes", "source_cache_max_sources") if hasattr(catalog.provider,name)},
            code_sha256={name:hashlib.sha256((source/name).read_bytes()).hexdigest()
                for name in ("deployable.py", "sparse_seed.py", "road_provider.py", "streaming_seed_diagnostic.py")},
            caller_provenance=dict(provenance), proposal_count=0, replay_attempts=0,
            accepted_count=0, rejected_count=0, provisional_incumbent=None,
            exact_optimum_claimed=False, solver_started=False, denominator_included=False,
            timings={name:dict(wall_ns=0,cpu_ns=0) for name in
                ("generation_active", "replay_active", "fresh_replay_active")},
            observer_io_wall_ns=0, observer_io_cpu_ns=0, journal_events=0, journal_suppressed=0)
        estimator=getattr(self.provider,"source_cache_entry_bytes",None)
        if estimator is not None:
            estimate=estimator(self.provider.graph.node_count)
            self.state["source_cache_entry_estimated_bytes"]=estimate
            config=self.state["cache_configuration"]
            self.state["source_cache_one_entry_fits"]=(
                config.get("source_cache_max_sources",0)>0 and
                estimate<=config.get("source_cache_max_bytes",0))
        self.hasher=hashlib.sha256(b"[")
        self.checkpoint_ns=int(checkpoint_seconds*1e9)
        self.last_checkpoint=0
        self.max_journal_events=max_journal_events
        self.journal=(self.output/"progress.jsonl").open("x")
        try:
            self.persist("observer_begin", journal=True)
        except BaseException:
            self.journal.close()
            raise

    def metrics(self):
        names=("source_run_count", "route_wall_ns", "route_process_cpu_ns",
               "source_cache_bytes", "source_cache_hits", "source_cache_evictions", "source_cache_skips")
        return {name:getattr(self.provider,name) for name in names if hasattr(self.provider,name)}

    def persist(self,event, *, journal=False):
        started=time.monotonic_ns(), time.process_time_ns()
        self.state.update(last_event=event, provider_metrics=self.metrics())
        complete=self.state["generation_complete"]
        h=self.hasher.copy()
        if complete: h.update(b"]")
        self.state["ordered_proposal_sha256"]=h.hexdigest() if complete else None
        self.state["ordered_proposal_prefix_sha256"]=self.hasher.hexdigest()
        self.state["proposal_digest_scope"]="complete_json_array" if complete else "incomplete_json_array_prefix"
        if journal:
            # Reserve a final terminal row; all interim history has a fixed cap.
            terminal=event in ("complete", "error")
            limit=self.max_journal_events if terminal else self.max_journal_events-1
            if self.state["journal_events"] < limit:
                self.state["journal_events"]+=1
                self.journal.write(canonical(dict(event=event,run_id=self.state["run_id"],
                    status=self.state["status"],proposal_count=self.state["proposal_count"],
                    accepted_count=self.state["accepted_count"],generation_complete=complete))+"\n")
                self.journal.flush();os.fsync(self.journal.fileno())
            else:self.state["journal_suppressed"]+=1
        temp=self.output/"snapshot.tmp"
        with temp.open("w") as f:
            f.write(canonical(self.state)+"\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,self.output/"snapshot.json")
        fd=os.open(self.output,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        self.state["observer_io_wall_ns"]+=time.monotonic_ns()-started[0]
        self.state["observer_io_cpu_ns"]+=time.process_time_ns()-started[1]
        self.last_checkpoint=time.monotonic_ns()

    def __call__(self,event,**data):
        timers={"generation_step":"generation_active", "replay_step":"replay_active",
                "fresh_replay_step":"fresh_replay_active"}
        if event in timers:
            for key in ("wall_ns","cpu_ns"):
                self.state["timings"][timers[event]][key]+=data[key]
        elif event=="proposal":
            if self.state["proposal_count"]:self.hasher.update(b",")
            self.hasher.update(canonical((data["sequence"],data["charges"])).encode())
            self.state["proposal_count"]+=1
        elif event=="replay_attempt":self.state["replay_attempts"]+=1
        elif event=="replay_rejected":self.state["rejected_count"]+=1
        elif event in ("incumbent","replay_accepted"):
            self.state["accepted_count"]+=1
            if event=="incumbent":
                self.state["provisional_incumbent"]={key:data[key] for key in
                    ("lex_key","sequence","charges","edge_witnesses","status")}
        elif event=="generation_end":self.state["generation_complete"]=True
        elif event=="seed_verified":
            self.state["verified_seed"]={key:data[key] for key in
                ("lex_key","sequence","charges","max_depth")}
        if event.endswith("_step_begin"):
            self.state["active_stage"]=event.removesuffix("_begin")
        elif event in timers:
            self.state["active_stage"]=None
        important=event in ("incumbent","generation_end","seed_verified") or event.endswith("_step_begin")
        if important or time.monotonic_ns()-self.last_checkpoint>=self.checkpoint_ns:
            self.persist(event,journal=True)

    def finish(self, *, result=None, error=None):
        self.state["status"]="complete" if error is None else "error"
        self.state["result_status"]=None if result is None else result["status"]
        self.state["error"]=None if error is None else dict(type=type(error).__name__,message=str(error))
        self.state["io_measurement_excludes_current_snapshot"]=True
        self.persist(self.state["status"],journal=True)


def observe_streaming_seed(query, catalog, *, output_dir, provenance, **options):
    """Run streaming seed admission only; provenance/resource admission is caller-owned."""
    from .sparse_seed import admit_sparse_seed
    observer=StreamingSeedObserver(query,catalog,output_dir=output_dir,provenance=provenance,**options)
    try:
        result=admit_sparse_seed(query,catalog,observer=observer)
    except BaseException as error:
        try:observer.finish(error=error)
        except BaseException as diagnostic_error:
            error.add_note("Streaming diagnostic finalization failed: "+repr(diagnostic_error))
        try:observer.journal.close()
        except BaseException as close_error:
            error.add_note("Streaming diagnostic close failed: "+repr(close_error))
        raise
    else:
        try:observer.finish(result=result)
        except BaseException as error:
            try:observer.journal.close()
            except BaseException as close_error:
                error.add_note("Streaming diagnostic close failed: "+repr(close_error))
            raise
        observer.journal.close()
        return result
