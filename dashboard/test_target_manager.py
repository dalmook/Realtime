"""Runs the synthetic acceptance suite, never copies or writes the company database."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_dashboard import DashboardTests
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DashboardTests))
    raise SystemExit(not result.wasSuccessful())
