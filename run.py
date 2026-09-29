"""Portable project entrypoint. Python 3.11+; default command starts the dashboard."""
import sys
if sys.version_info<(3,11):raise SystemExit('Python 3.11+ required.')
for stream in (sys.stdout,sys.stderr):
    if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
from launcher import main
from scm_db.common import safe_error
if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)
    except Exception as e:print('ERROR:',safe_error(e),file=sys.stderr);raise SystemExit(1)
