import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('build_monitor',Path(__file__).parent.parent/'deploy/build-resource-monitor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MonitorTests(unittest.TestCase):
    def test_each_exact_boundary(self):
        row={'free':40000,'available':4096,'swap':1256}
        self.assertIsNone(m.reason(row,50000,1000,2099.9))
        for changed,want in [({'free':35839},'disk-floor'),({'free':36000},'disk-growth'),({'available':4095},'ram-floor'),({'swap':1257},'swap-growth')]:
            baseline=53000 if want=='disk-growth' else 50000
            self.assertEqual(m.reason({**row,**changed},baseline,1000,1),want)
        self.assertEqual(m.reason(row,50000,1000,2100),'overall-timeout')

    def test_success_heartbeat_and_fixed_phase(self):
        now=[0.0];count=[0];sleeps=[]
        def read():count[0]+=1;now[0]+=.2;return {'free':50000,'available':9000,'swap':1000}
        def sleep(seconds):sleeps.append(seconds);now[0]+=seconds
        with tempfile.TemporaryDirectory() as directory:
            result=m.monitor(directory,1,50000,1000,0,read=read,clock=lambda:now[0],sleep=sleep,alive=lambda:count[0]<3,signal_parent=lambda:self.fail('unexpectedsignal'))
            self.assertEqual(result,0);self.assertTrue((Path(directory)/'resource.heartbeat').exists())
            self.assertEqual(len((Path(directory)/'resources-python.jsonl').read_text().splitlines()),3)
        self.assertTrue(all(abs(s-4.8)<.001 for s in sleeps))

    def test_breach_immediate_no_heartbeat(self):
        signaled=[]
        with tempfile.TemporaryDirectory() as directory:
            result=m.monitor(directory,1,50000,1000,0,read=lambda:{'free':35000,'available':9000,'swap':1000},clock=lambda:0,sleep=lambda n:self.fail('mustnotwait'),alive=lambda:True,signal_parent=lambda:signaled.append(True))
            self.assertEqual(result,1);self.assertFalse((Path(directory)/'resource.heartbeat').exists())
            self.assertIn('disk-floor',(Path(directory)/'STOPPED').read_text())
        self.assertEqual(signaled,[True])

    def test_sample_failure_signals_without_refresh(self):
        signaled=[]
        def bad():raise OSError('fixture')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):m.monitor(directory,1,50000,1000,0,read=bad,clock=lambda:0,alive=lambda:True,signal_parent=lambda:signaled.append(True))
            self.assertFalse((Path(directory)/'resource.heartbeat').exists())
            self.assertIn('OSError',(Path(directory)/'STOPPED').read_text())
        self.assertEqual(signaled,[True])
