"""Compatibility command: continuous KZWI3 source, never DROP/REPLACE an amount table.
Usage: python collect_kzwi3.py [--from-date YYYY-MM-DD]
"""
import sys
from scm_db.cli import main
if __name__=='__main__':
    raise SystemExit(main(['collect','--source','shipment_amount_dep',*sys.argv[1:]]))
