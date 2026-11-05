"""Dedicated-process guards tested against synthetic files and denied endpoints."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ProcessGuardTests(unittest.TestCase):
    def test_guard_denies_core_state_and_code_writes_but_allows_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);projection=root/'projection';projection.mkdir(mode=0o700)
            code_root=root/'code';code_root.mkdir();(code_root/'module.py').write_text('reviewed code')
            (root/'core.sqlite3').write_text('synthetic private state')
            script='''
import pathlib,sqlite3,sys
from okal_core.cognitive.providers import install_file_guard
root=pathlib.Path(sys.argv[1]);projection=root/'projection'
install_file_guard(projection,root/'code')
for operation in [lambda:(root/'core.sqlite3').read_text(),lambda:sqlite3.connect(root/'core.sqlite3'),
                  lambda:(root/'code/module.py').write_text('bad')]:
 try:operation()
 except PermissionError:pass
 else:raise AssertionError('guard failed')
(projection/'derived.json').write_text('allowed')
assert (root/'code/module.py').read_text()=='reviewed code'
print('guards passed')
'''
            result=subprocess.run([sys.executable,'-c',script,str(root)],capture_output=True,text=True,
                timeout=10,env={'PYTHONPATH':str(Path(__file__).parents[1]/'src'),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('guards passed',result.stdout)
            self.assertEqual((root/'core.sqlite3').read_text(),'synthetic private state')

    def test_network_guard_rejects_external_dns_other_loopback_and_subprocess(self):
        script='''
import socket,subprocess
from okal_core.cognitive.providers import install_network_guard
install_network_guard()
for operation in [lambda:socket.create_connection(('example.com',443),1),
                  lambda:socket.create_connection(('127.0.0.1',8766),1),
                  lambda:subprocess.run(['/usr/bin/true'])]:
 try:operation()
 except PermissionError:pass
 else:raise AssertionError('guard failed')
print('guards passed')
'''
        result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=10,
            env={'PYTHONPATH':str(Path(__file__).parents[1]/'src'),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('guards passed',result.stdout)


if __name__=='__main__':unittest.main()
