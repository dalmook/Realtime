"""Run the actual demo launcher against temporary SQLite; never contact company services."""
from __future__ import annotations
import json, math, os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='scm-launch-test-') as directory:
        logpath = Path(directory) / 'launcher.txt'
        with logpath.open('w', encoding='utf-8') as log:
            proc = subprocess.Popen([sys.executable, '-S', 'run.py', 'demo', '--no-browser', '--port', str(port), '--data-dir', directory], cwd=ROOT, stdout=log, stderr=log)
            base = f'http://127.0.0.1:{port}'
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def get(path: str):
                with opener.open(base + path, timeout=5) as response:
                    assert response.status == 200
                    data = response.read()
                    return json.loads(data) if path.startswith('/api/') else data
            try:
                for attempt in range(100):
                    if proc.poll() is not None:
                        raise AssertionError('Demo exited: ' + logpath.read_text(encoding='utf-8'))
                    try:
                        health = get('/api/health')
                        break
                    except (OSError, ValueError):
                        time.sleep(0.2)
                else:
                    raise AssertionError('Demo HTTP startup timed out')
                html = get('/').decode('utf-8')
                for view in ('overview', 'inbound', 'shipment', 'inventory', 'targets'):
                    assert f'id="{view}View"' in html, view
                for metric in ('EA', 'BOX', 'USD', 'EQ_DRAM', 'EQ_FLASH'):
                    kpi = get('/api/kpi?metric=' + metric)
                    hourly = get('/api/hourly?metric=' + metric)
                    assert kpi['metric'] == metric
                    assert len(hourly['hours']) == 24
                    assert math.isclose(kpi['shipment']['actual_today'], sum(hourly['shipment']), rel_tol=1e-9, abs_tol=0.1), metric
                for route in ('filters', 'items', 'customers', 'events', 'targets', 'focus?action=kpi'):
                    assert isinstance(get('/api/' + route), dict), route
                assert (Path(directory) / 'scm_live.sqlite').is_file()
                print('LAUNCHER SMOKE PASS: isolated demo DB, five HTML views, five metric reconciliations and six API routes')
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=5)

if __name__ == '__main__':
    main()
