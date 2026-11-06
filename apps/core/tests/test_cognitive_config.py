"""Interpreter trust remains narrow when systemd masks host-root ownership."""
import os
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from okal_core.cognitive.config import trusted_executable


def executable(uid, mode=0o755, device=17, inode=91):
    return SimpleNamespace(st_uid=uid, st_mode=stat.S_IFREG | mode,
                           st_dev=device, st_ino=inode)


class ExecutableOwnershipTests(unittest.TestCase):
    def test_root_and_owner_executables_remain_accepted(self):
        self.assertTrue(trusted_executable(executable(0)))
        self.assertTrue(trusted_executable(executable(os.getuid())))

    def test_unmapped_owner_is_accepted_only_for_running_executable_inode(self):
        # Real-device systemd namespace maps host-root files to overflow UID.
        with patch('okal_core.cognitive.config.os.stat', return_value=executable(65534)):
            self.assertTrue(trusted_executable(executable(65534)))
            self.assertFalse(trusted_executable(executable(65534, inode=92)))
            self.assertFalse(trusted_executable(executable(65534, device=18)))

    def test_other_foreign_executable_and_missing_proc_fail_closed(self):
        with patch('okal_core.cognitive.config.os.stat', side_effect=OSError('unavailable')):
            self.assertFalse(trusted_executable(executable(65534)))
        with patch('okal_core.cognitive.config.os.stat', return_value=executable(0, inode=3)):
            self.assertFalse(trusted_executable(executable(65533)))

    def test_write_bits_and_nonregular_files_never_gain_inode_exception(self):
        with patch('okal_core.cognitive.config.os.stat', return_value=executable(65534)):
            for uid in (0, os.getuid(), 65534):
                for mode in (0o775, 0o757, 0o777):
                    with self.subTest(uid=uid, mode=mode):
                        self.assertFalse(trusted_executable(executable(uid, mode)))
            directory = executable(65534)
            directory.st_mode = stat.S_IFDIR | 0o755
            self.assertFalse(trusted_executable(directory))


if __name__ == '__main__':
    unittest.main()
