"""Synthetic frame-log checks: entrance stalls and missing GPU samples stay visible."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('frame_report', Path(__file__).resolve().parents[1] / 'scripts/linux/frame_report.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrameReportTests(unittest.TestCase):
    def frame(self, fighters, wall, gpu=''):
        return dict(fighters=str(fighters), wall_ms=str(wall), gpu_ms=str(gpu),
                    replay_ms='1', gpu_wait_ms='0', pipeline_ms='0')

    def test_first_entrance_frame_is_included(self):
        rows = [self.frame(0, 300)] + [self.frame(1, 50, 40)] + [self.frame(1, 16, 4)] * 100
        result = module.report(rows, 30)
        self.assertEqual(result['entrance']['frames'], 30)
        self.assertEqual(result['entrance']['wall_ms']['max'], 50)
        self.assertEqual(result['entrance']['over_20_ms'], 1)
        self.assertEqual(result['after_entrance']['wall_ms']['max'], 16)

    def test_missing_gpu_data_is_not_reported_as_zero(self):
        result = module.report([self.frame(1, 16), self.frame(1, 17, 0)])
        self.assertEqual(result['entrance']['gpu_ms']['samples'], 1)
        self.assertIsNone(module.report([self.frame(1, 16)])['entrance']['gpu_ms'])
        self.assertIsNone(module.report([])['all']['wall_ms'])


if __name__ == '__main__':
    unittest.main()
