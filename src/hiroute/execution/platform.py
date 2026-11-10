"""Platform sampling adapters for the existing resource supervisor."""
from unittest.mock import patch

def mac_monitors(stack):
    """Adapt existing supervisor samples on macOS; retain its enforcement loop."""
    import psutil
    import hiroute.runtime as runtime
    def members(pgid):
        # Worker is single-process; include all current descendants defensively.
        try:
            leader=psutil.Process(pgid)
            return [leader,*leader.children(recursive=True)]
        except psutil.NoSuchProcess:
            return []
    def memory(pgid, field):
        total=0
        for p in members(pgid):
            try: total+=getattr(p.memory_info(),field)
            except psutil.NoSuchProcess: pass
        return total
    def cpu(pgid):
        total=0.
        for p in members(pgid):
            try:
                t=p.cpu_times();total+=t.user+t.system
            except psutil.NoSuchProcess: pass
        return total
    for name,fn in (('_group_rss_bytes',lambda p:memory(p,'rss')),
                    ('_group_vmsize_bytes',lambda p:memory(p,'vms')),
                    ('_group_cpu_seconds',cpu),
                    ('system_mem_available_bytes',lambda:psutil.virtual_memory().available)):
        stack.enter_context(patch.object(runtime,name,fn))

