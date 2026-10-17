import resource,signal
resource.setrlimit(resource.RLIMIT_CPU,(15,18));resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(30)
import os,sys,time
from pathlib import Path
from unittest.mock import patch
from test_energy import EnergyTests,digest,observation,_solve_problem
out=Path(sys.argv[1]);behavior=sys.argv[2]
EnergyTests.setUpClass();test=EnergyTests()
def notify(error):
    # Explicit caller policy: durable fatal notification, parent owns killing.
    with (out/'failed').open('x') as f:f.write(str(error));f.flush();os.fsync(f.fileno())
obs=observation.EnergyObservation(out/'evidence',run_identity={'run':'contained'},interval=.01,on_async_error=notify)
c=test.context(obs=obs);p=test.problem(c)
p.finish((p.initial_piece(),));obs.sample(force=True)
progress=observation.EnergyProgress(out/'progress',energy_observation=obs,query_sha256=digest(p.case),
    domain_sha256=digest('tiny'),source_sha256={'test':digest('source')},provider=c.provider,interval=.01)
original=c.provider.leg;published=observation._publish;blocked=False

def leg(*args,**kw):
    global blocked
    value=original(*args,**kw)
    if not blocked:
        blocked=True;(out/'ready').write_text('after actual native selected-leg return')
        while True:time.sleep(.01)
    return value

def publish(path,*a,**kw):
    if behavior=='fail' and blocked and path.name=='status.json':raise OSError('controlled asynchronous sink failure')
    return published(path,*a,**kw)
c.provider.leg=leg
with patch.object(observation,'_publish',publish):_solve_problem(p,progress_hook=progress)
raise RuntimeError('Controlled wait unexpectedly returned')
