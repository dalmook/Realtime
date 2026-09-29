"""Standalone collector using the same settings, initialization and OS writer lock."""
from pathlib import Path
from scm_db.settings import Settings
from scm_db.database import Database
from scm_db.common import ProcessLock
from scm_db.engine import Engine
from scm_db.cli import logging_setup
from dashboard import runtime
ROOT=Path(__file__).resolve().parent

def main():
    s=Settings(ROOT);db=Database(s.db_path,ROOT)
    with ProcessLock(s.data_dir/'writer.lock'):
        db.initialize(s.config);runtime.configure(s);runtime.ensure_runtime();logging_setup(s)
        print('DB:',db.path);Engine(s,db).loop()
if __name__=='__main__':main()
