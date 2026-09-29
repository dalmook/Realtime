from __future__ import annotations
import contextlib, json, logging, threading, time, uuid
from datetime import datetime
from .common import *
from .connectors.splunk import SplunkClient
from .connectors.oracle import OracleClient
from .reference import publish
LOG=logging.getLogger('scm_db')

def schedule_due(now,at,already=False):
    hh,mm=map(int,at.split(':'))
    return not already and (now.hour,now.minute)>=(hh,mm)

class Engine:
    def __init__(self,settings,db):
        self.s=settings; self.db=db; self.clients={}; self.stop=threading.Event()
    def collect(self,d,*,from_epoch=None):
        if not d.get('enabled'): raise ConfigError(f"{d['id']}: 비활성/원천 매핑 미확정")
        name=d.get('connection','DEP')
        if name not in self.clients: self.clients[name]=SplunkClient(self.s.profile(name))
        state=self.db.state(d['id'])
        upper=int(time.time())-self.s.number('SPLUNK_SETTLE_SECONDS',10,0,3600)
        if from_epoch is not None:
            lower=from_epoch
        elif state['watermark']:
            lower=max(0,state['watermark']-int(d.get('overlap_seconds',300)))
        else:
            configured=d.get('bootstrap_from','month_start')
            lower=month_start_epoch() if configured=='month_start' else int(datetime.strptime(configured,'%Y-%m-%d').replace(tzinfo=KST).timestamp())
        if upper<=lower: return {'windows':0,'rows':0}
        marker='bootstrap_floor:'+d['id']
        stored=self.db.query('SELECT value FROM meta WHERE key=?',(marker,))
        floor=int(stored[0]['value']) if stored and from_epoch is None else lower
        with self.db.transaction() as con:
            con.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(marker,str(floor)))
        totals={'windows':0,'rows':0}
        for lo,hi,events in self.clients[name].windows(d,lower,upper):
            if self.stop.is_set(): break
            result=self.db.ingest(d,events,hi,None)
            totals['windows']+=1; totals['rows']+=result['read']
            LOG.info('%s · window %s..%s · read=%s written=%s unchanged=%s older=%s',d['id'],lo,hi,result['read'],result['written'],result['unchanged'],result['older'])
        else:
            with self.db.transaction() as con:
                con.execute('''UPDATE source_state SET coverage_from=CASE WHEN coverage_from IS NULL THEN ? ELSE MIN(coverage_from,?) END WHERE source_id=?''',(floor,floor,d['id']))
                con.execute('DELETE FROM meta WHERE key=?',(marker,))
        return totals
    def sync_oracle(self):
        if not self.s.flag('ORACLE_ENABLED',True): raise ConfigError('ORACLE_ENABLED=false')
        run=self.db.start_run('oracle_all','reference_snapshot'); stage=None
        try:
            stage,metadata=OracleClient(self.s).stage()
            result=publish(self.db,self.s,stage,metadata,run)
            out=self.s.data_dir/'exports'
            atomic_text(out/'oracle_schema.json',json.dumps(metadata,ensure_ascii=False,indent=2))
            atomic_text(out/'oracle_mapping_status.json',json.dumps(result,ensure_ascii=False,indent=2))
            LOG.info('Oracle 5-table snapshot published · %s',js(result))
            return result
        except BaseException as exc:
            self.db.fail_run(run,'oracle_all',exc); raise
        finally:
            if stage:
                with contextlib.suppress(OSError): stage.unlink()
    def run_scheduled_oracle(self,now=None):
        now=now or now_kst(); day=now.strftime('%Y-%m-%d')
        at=self.s.config['oracle_schedule'].get('at','09:00')
        if not self.s.flag('ORACLE_ENABLED',True): return False
        with self.db.transaction() as con:
            exists=con.execute("SELECT 1 FROM schedule_run WHERE task='oracle_daily' AND local_day=?",(day,)).fetchone()
            if not schedule_due(now,at,bool(exists)): return False
            con.execute('INSERT INTO schedule_run(task,local_day,started_at,status) VALUES(?,?,?,?)',('oracle_daily',day,stamp(),'RUNNING'))
        status='SUCCESS'; detail=''
        try: self.sync_oracle()
        except Exception as exc:
            status='FAILED'; detail=safe_error(exc); LOG.error('Oracle daily failed · %s',detail)
        with self.db.transaction() as con:
            con.execute('UPDATE schedule_run SET ended_at=?,status=?,detail=? WHERE task=? AND local_day=?',(stamp(),status,detail,'oracle_daily',day))
        # Exactly one scheduled attempt/day. Manual retry is an explicit separate action.
        return True
    def _oracle_loop(self):
        while not self.stop.is_set():
            try: self.run_scheduled_oracle()
            except Exception as exc: LOG.error('Oracle schedule error · %s',safe_error(exc))
            self.stop.wait(20)
    def loop(self):
        # The process lock is taken by the CLI. A second process cannot start a writer.
        with self.db.transaction() as con:
            con.execute("UPDATE etl_run SET status='INTERRUPTED',ended_at=? WHERE status='RUNNING'",(stamp(),))
            con.execute("UPDATE schedule_run SET status='INTERRUPTED',ended_at=?,detail='이전 프로세스 중단. 필요 시 Oracle 수동 재조회' WHERE status='RUNNING'",(stamp(),))
        thread=threading.Thread(target=self._oracle_loop,name='oracle-daily-09',daemon=True); thread.start()
        due={}; backup_day=''
        try:
            while not self.stop.is_set():
                for d in self.s.splunk:
                    if not d.get('enabled') or time.monotonic()<due.get(d['id'],0): continue
                    try: self.collect(d)
                    except Exception as exc:
                        run=self.db.start_run(d['id'],'splunk_poll')
                        self.db.fail_run(run,d['id'],exc)
                        LOG.error('%s · %s',d['id'],safe_error(exc))
                    finally: due[d['id']]=time.monotonic()+int(d.get('poll_seconds',60))
                now=now_kst()
                # Local backup is independent of Oracle reads and runs only once per local date.
                if self.s.flag('AUTO_BACKUP',True) and now.hour>=9 and backup_day!=now.strftime('%Y%m%d'):
                    try:
                        dst=self.db.backup(); self.db.prune(self.s.number('RAW_RETENTION_DAYS',30,7,3650))
                        for p in sorted(dst.parent.glob('scm_*.sqlite'))[:-self.s.number('BACKUP_KEEP',7,1,365)]: p.unlink()
                        backup_day=now.strftime('%Y%m%d')
                    except Exception as exc: LOG.error('Backup/retention · %s',safe_error(exc)); backup_day=now.strftime('%Y%m%d')
                self.stop.wait(1)
        except KeyboardInterrupt: pass
        finally:
            self.stop.set(); thread.join(timeout=2)
