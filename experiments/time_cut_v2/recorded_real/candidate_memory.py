"""Linux memory high-water for the candidate's current exec address space.

getrusage counters survive exec and may include the large family coordinator's
pre-exec image. VmHWM belongs to the current mm, so it retains the candidate's
own peak after memory is released. These are kernel RSS observations, not an
exact Python heap census; the hard AS and outer process-group caps still apply.
"""
import os
import sys

SOURCE='linux-exec-vmhwm-v1'
STATUS_BYTES=65536

def parse_status(raw,pid):
 if type(raw) is not bytes or len(raw)>STATUS_BYTES:raise ValueError('candidate status byte cap')
 if type(pid) is not int or pid<=0:raise ValueError('candidate PID required')
 wanted={}
 for line in raw.decode('ascii').splitlines():
  key,separator,value=line.partition(':')
  if not separator or key not in ('Pid','VmHWM','VmRSS'):continue
  if key in wanted:raise ValueError('duplicate candidate memory field')
  fields=value.split()
  if len(fields)!=(1 if key=='Pid' else 2) or not fields[0].isascii() or not fields[0].isdigit():
   raise ValueError('invalid candidate memory field')
  if key!='Pid' and fields[1]!='kB':raise ValueError('candidate RSS unit changed')
  number=int(fields[0]);wanted[key]=number if key=='Pid' else number*1024
 if set(wanted)!={'Pid','VmHWM','VmRSS'} or wanted['Pid']!=pid or min(wanted['VmHWM'],wanted['VmRSS'])<=0:
  raise ValueError('missing or foreign candidate memory observation')
 # VmHWM normally includes VmRSS. max also handles a concurrent allocation
 # between the kernel's field reads without undercounting that observation.
 return max(wanted['VmHWM'],wanted['VmRSS'])

def peak_rss_bytes():
 if not sys.platform.startswith('linux'):raise ValueError('Linux candidate RSS source required')
 with open('/proc/self/status','rb') as stream:raw=stream.read(STATUS_BYTES+1)
 return parse_status(raw,os.getpid())
