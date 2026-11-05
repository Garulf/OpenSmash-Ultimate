"""Host compiler/cache regression tests; made-up sources and a fake compiler."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BUILD = Path(__file__).resolve().parents[1] / 'tools/lifter/build.py'


class HostFlagsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location('host_build_test', BUILD)
        self.build = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, RECOMP_TARGET='windows', RECOMP_HOST_OPT='-O1'):
            spec.loader.exec_module(self.build)
        b = self.build
        b.HERE = str(self.root)
        b.HOST_SOURCES = ['host.c']
        b.HOST_FLAGS = ['-O1']
        b.CXX_FLAGS = ['-O1']
        b.CXX_SOURCES = [str(self.root / 'menu.cpp')]
        b.HAVE_IMGUI = True
        b.TARGET_LINUX = b.TARGET_POSIX = True
        b.TARGET_MACOS = False
        b.LIBS = []
        b.build_game_dll = lambda: 0
        for name in ('host.c', 'gamedll.c', 'menu.cpp', 'runtime.h', 'menu_imconfig.h', 'build.py'):
            p = self.root / name
            p.write_text('/* synthetic fixture */\n')
            os.utime(p, (1000000000, 1000000000))
        self.calls = []
        self.fail = False
        env = patch.dict(os.environ, RECOMP_EXE='synthetic', RECOMP_R1='0')
        env.start()
        self.addCleanup(env.stop)
        runner = patch.object(b.subprocess, 'run', self.compiler)
        runner.start()
        self.addCleanup(runner.stop)

    def compiler(self, argv, **kwargs):
        if '-c' in argv:
            src = Path(argv[argv.index('-o') - 1])
            self.calls.append(src.name)
            if self.fail and src.name == 'host.c':
                return subprocess.CompletedProcess(argv, 1, '', 'synthetic compile failure')
        Path(argv[argv.index('-o') + 1]).write_text('fake object or executable')
        return subprocess.CompletedProcess(argv, 0, '', '')

    def link(self):
        self.calls.clear()
        return self.build.cmd_link()

    def test_reuses_objects_until_flags_change(self):
        self.assertEqual(self.link(), 0)
        self.assertCountEqual(self.calls, ['host.c', 'gamedll.c', 'menu.cpp'])
        self.assertEqual(self.link(), 0)
        self.assertEqual(self.calls, ['gamedll.c'])
        self.build.HOST_FLAGS = ['-O2']
        self.assertEqual(self.link(), 0)
        self.assertCountEqual(self.calls, ['host.c', 'gamedll.c', 'menu.cpp'])
        self.build.CXX_FLAGS = ['-O2']
        self.assertEqual(self.link(), 0)
        self.assertCountEqual(self.calls, ['host.c', 'gamedll.c', 'menu.cpp'])

    def test_failed_change_cannot_poison_previous_cache(self):
        self.assertEqual(self.link(), 0)
        self.build.HOST_FLAGS = ['-O2']
        self.fail = True
        self.assertEqual(self.link(), 1)
        self.assertFalse((self.root / 'obj_host/synthetic/build-flags.json').exists())
        self.build.HOST_FLAGS = ['-O1']
        self.fail = False
        self.assertEqual(self.link(), 0)
        self.assertCountEqual(self.calls, ['host.c', 'gamedll.c', 'menu.cpp'])

    def test_rejects_fast_math(self):
        spec = importlib.util.spec_from_file_location('invalid_host_flags', BUILD)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, RECOMP_TARGET='windows', RECOMP_HOST_OPT='-Ofast'):
            with self.assertRaisesRegex(SystemExit, 'RECOMP_HOST_OPT must be'):
                spec.loader.exec_module(module)


if __name__ == '__main__':
    unittest.main()
