"""Deterministic live-output churn races; no road graph or large worker."""
import errno
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from experiments.mechanism_recovery_v1 import supervisor as s


def test_deleted_file_between_enumeration_and_stat(tmp_path):
    (tmp_path/'temporary').write_bytes(b'gone')
    original=os.stat
    def deleting_stat(path, *args, **kwargs):
        if path == 'temporary':
            os.unlink(path,dir_fd=kwargs['dir_fd'])
        return original(path,*args,**kwargs)
    with patch.object(s.os,'stat',side_effect=deleting_stat):
        assert s._files(tmp_path,20) == (0,None)


def test_deleted_build_directory_between_stat_and_open(tmp_path):
    (tmp_path/'.build-race').mkdir()
    (tmp_path/'retained').write_bytes(b'kept')
    original=os.open
    def deleting_open(path,*args,**kwargs):
        if path == '.build-race':
            os.rmdir(path,dir_fd=kwargs['dir_fd'])
        return original(path,*args,**kwargs)
    with patch.object(s.os,'open',side_effect=deleting_open):
        assert s._files(tmp_path,20) == (4,None)


def test_directory_swap_to_outside_symlink_is_never_followed(tmp_path):
    root=tmp_path/'owned';root.mkdir()
    outside=tmp_path/'outside';outside.mkdir()
    (outside/'must-not-scan').write_bytes(b'x'*100)
    (root/'.build-race').mkdir()
    original=os.open
    def swapping_open(path,*args,**kwargs):
        if path == '.build-race':
            os.rmdir(path,dir_fd=kwargs['dir_fd'])
            os.symlink(outside,path,dir_fd=kwargs['dir_fd'])
        return original(path,*args,**kwargs)
    with patch.object(s.os,'open',side_effect=swapping_open):
        size,reason=s._files(root,20)
    assert size == 0
    assert reason == 'output_directory_changed'


def test_initial_symlink_and_special_file_still_fail_closed(tmp_path):
    root=tmp_path/'owned';root.mkdir()
    os.symlink(tmp_path,root/'link')
    assert s._files(root,20)[1] == 'output_symlink'
    (root/'link').unlink()
    os.mkfifo(root/'pipe')
    assert s._files(root,20)[1] == 'output_special_file'


def test_non_enoent_error_is_not_suppressed(tmp_path):
    (tmp_path/'entry').write_bytes(b'a')
    with patch.object(s.os,'stat',side_effect=PermissionError(errno.EACCES,'denied')):
        with pytest.raises(PermissionError):s._files(tmp_path,20)


def test_deleted_root_is_not_ignored(tmp_path):
    with pytest.raises(FileNotFoundError):s._files(tmp_path/'missing',20)


def test_entry_and_byte_accounting_still_enforced(tmp_path):
    (tmp_path/'one').write_bytes(b'abc')
    (tmp_path/'two').mkdir()
    (tmp_path/'two'/'three').write_bytes(b'defgh')
    assert s._files(tmp_path,20) == (8,None)
    assert s._files(tmp_path,1)[1] == 'output_entry_limit'


def test_root_symlink_is_never_opened(tmp_path):
    outside=tmp_path/'outside';outside.mkdir()
    root=tmp_path/'root';root.symlink_to(outside,target_is_directory=True)
    with pytest.raises(OSError):s._files(root,20)


def test_replaced_directory_identity_is_rejected(tmp_path):
    (tmp_path/'changing').mkdir()
    original=os.open
    def replacing_open(path,*args,**kwargs):
        if path == 'changing':
            fd=kwargs['dir_fd']
            os.rename(path,'old',src_dir_fd=fd,dst_dir_fd=fd)
            os.mkdir(path,dir_fd=fd)
        return original(path,*args,**kwargs)
    with patch.object(s.os,'open',side_effect=replacing_open):
        with pytest.raises(ValueError,match='identity changed'):s._files(tmp_path,20)


def test_early_rejection_closes_all_scan_descriptors(tmp_path):
    (tmp_path/'nested').mkdir()
    (tmp_path/'nested'/'link').symlink_to(tmp_path,target_is_directory=True)
    before=len(os.listdir('/proc/self/fd'))
    for _ in range(5):
        assert s._files(tmp_path,20)[1] == 'output_symlink'
    assert len(os.listdir('/proc/self/fd')) == before
