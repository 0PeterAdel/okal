"""No-network synthetic tests for private OKAL idle resource sampling."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "benchmark-okal-idle.py"
spec = importlib.util.spec_from_file_location("okal_idle_benchmark", SCRIPT)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class IdleBenchmarkTests(unittest.TestCase):
    def test_parse_proc_stat_handles_parenthesized_process_name(self):
        # Field 3 starts after the rightmost ')', field 14=utime, field 15=stime.
        values = ["S"] + ["0"] * 19
        values[11], values[12] = "500", "200"
        self.assertEqual(bench.parse_proc_stat(
            "225 (okal  worker) ) " + " ".join(values)), 700)
        with self.assertRaises(ValueError):
            bench.parse_proc_stat("broken")

    def test_idle_service_has_zero_cpu_percent_without_private_content(self):
        rows = [
            {"elapsed": 0, "metrics": {"pid": 123, "cpu_ticks": 100, "rss_kib": 51200}},
            {"elapsed": 5, "metrics": {"pid": 123, "cpu_ticks": 100, "rss_kib": 52224}},
            {"elapsed": 10, "metrics": {"pid": 123, "cpu_ticks": 100, "rss_kib": 54272}},
        ]
        result=bench.summarize(rows,100)
        self.assertEqual(result["cpu_percent_avg_single_core"],0)
        self.assertEqual(result["rss_mib_peak"],53)
        self.assertEqual(result["samples"],3)
        self.assertNotIn("token",str(result).lower())

    def test_pid_restart_and_service_absence_are_not_fake_cpu(self):
        rows=[
            {"elapsed":0,"metrics":{"pid":12,"cpu_ticks":5,"rss_kib":2048}},
            {"elapsed":1,"metrics":None},
            {"elapsed":2,"metrics":{"pid":24,"cpu_ticks":200,"rss_kib":4096}},
            {"elapsed":3,"metrics":{"pid":24,"cpu_ticks":205,"rss_kib":4096}},
        ]
        result=bench.summarize(rows,100)
        self.assertEqual(result["cpu_percent_avg_single_core"],5)
        self.assertEqual(result["available_samples"],3)
        self.assertEqual(result["duration_seconds"],3)

    def test_pid_change_is_counted_and_not_compared(self):
        rows=[
            {"elapsed":0,"metrics":{"pid":12,"cpu_ticks":100,"rss_kib":1024}},
            {"elapsed":5,"metrics":{"pid":99,"cpu_ticks":10,"rss_kib":1024}},
        ]
        r=bench.summarize(rows,100)
        self.assertEqual(r["pid_changes"],1)
        self.assertIsNone(r["cpu_percent_avg_single_core"])

    def test_measure_has_no_network_and_bounded_sample_parameters(self):
        ticks=[100,105,110]
        times=[0.0,0.0,5.0,10.0]
        with patch.object(bench.os,"sysconf",return_value=100):
            r=bench.measure(3,5,pid_reader=lambda:123,
                sampler=lambda pid:{"pid":pid,"cpu_ticks":ticks.pop(0),
                                     "rss_kib":1024},
                sleeper=lambda _:None,clock=lambda:times.pop(0))
        self.assertEqual(r["cpu_percent_avg_single_core"],1)
        for invalid in (0,1,241,True):
            with self.assertRaises(ValueError):
                bench.measure(invalid,5)
        for invalid in (0,-1,float("nan"),float("inf"),True,61):
            with self.assertRaises(ValueError):
                bench.measure(2,invalid)

    def test_private_export_never_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as d:
            destination=Path(d)/"measurement.json"
            destination.write_text("protected")
            with patch.object(bench,"measure",return_value={"ok":True}):
                self.assertEqual(bench.main(["--out",str(destination)]),1)
            self.assertEqual(destination.read_text(),"protected")
