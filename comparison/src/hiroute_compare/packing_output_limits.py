"""Exact byte admission before output writes; stopping never truncates values."""
from pathlib import Path
from .streaming_road_graph import ResourceStop


def limit_value(value):
    if value is not None and (type(value) is not int or value<0):raise ValueError('nonnegative integer output byte quota')
    return value


class LimitedFile:
    def __init__(self,path,mode,limit=None):
        self.limit=limit_value(limit);self.bytes=0
        self.stream=Path(path).open(mode) if 'b' in mode else Path(path).open(mode,encoding='utf-8',newline='')
    def __enter__(self):return self
    def __exit__(self,*args):self.stream.close()
    def __getattr__(self,name):return getattr(self.stream,name)
    def write(self,value):
        size=len(value.encode('utf-8')) if isinstance(value,str) else len(value)
        if self.limit is not None and self.bytes+size>self.limit:raise ResourceStop('output byte quota before write')
        result=self.stream.write(value)
        if result!=len(value):raise OSError('short output write')
        self.bytes+=size;return result
