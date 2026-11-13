"""Independent review regressions, synthetic and no-network."""
import json, tempfile, threading, unittest
from pathlib import Path
from labs_meet.store import Store
from labs_meet.service import Companion

class ReviewGuards(unittest.TestCase):
    def setup_store(self, directory):
        s=Store(Path(directory)/'state.db')
        mids=[s.create('Synthetic',code,'Synthetic consent') for code in ['abc-defg-hij','aaa-bbbb-ccc']]
        ids=[s.stage(m,'join',{'code':s.meeting(m)['code']}) for m in mids]
        for oid in ids:s.approve(oid,s.out(oid)['digest'])
        return s,mids,ids

    def test_unknown_join_holds_quota(self):
        with tempfile.TemporaryDirectory() as d:
            s,m,ids=self.setup_store(d);s.claim(ids[0]);s.settle(ids[0],'unknown',{})
            with self.assertRaises(ValueError):s.claim(ids[1])
            self.assertEqual(s.out(ids[1])['status'],'approved');s.db.close()

    def test_sending_leave_does_not_release_quota(self):
        with tempfile.TemporaryDirectory() as d:
            s,m,ids=self.setup_store(d);s.claim(ids[0]);s.settle(ids[0],'submitted',{})
            leave=s.stage(m[0],'leave',{'code':'abc-defg-hij'});s.approve(leave,s.out(leave)['digest']);s.claim(leave)
            with self.assertRaises(ValueError):s.claim(ids[1])
            s.db.close()

    def test_concurrent_distinct_joins_only_one_claims(self):
        with tempfile.TemporaryDirectory() as d:
            s,m,ids=self.setup_store(d);s.db.close();barrier=threading.Barrier(2);results=[]
            def worker(oid):
                st=Store(Path(d)/'state.db');barrier.wait()
                try:st.claim(oid);results.append('claimed')
                except ValueError:results.append('blocked')
                finally:st.db.close()
            threads=[threading.Thread(target=worker,args=(oid,)) for oid in ids]
            for t in threads:t.start()
            for t in threads:t.join(10)
            self.assertEqual(sorted(results),['blocked','claimed'])

    def test_terminal_result_cannot_be_overwritten_by_same_status(self):
        with tempfile.TemporaryDirectory() as d:
            s,m,ids=self.setup_store(d);s.settle(ids[0],'failed',{'reason':'original'})
            s.settle(ids[0],'failed',{'reason':'late'})
            self.assertEqual(json.loads(s.out(ids[0])['result']),{'reason':'original'});s.db.close()

    def test_unknown_join_requires_manual_failure_reason(self):
        with tempfile.TemporaryDirectory() as d:
            s,m,ids=self.setup_store(d);s.claim(ids[0]);s.settle(ids[0],'unknown',{})
            app=Companion(s)
            with self.assertRaises(ValueError):app.resolve_unknown(ids[0],'sent',provider_id='fake')
            app.resolve_unknown(ids[0],'failed',reason='Provider checked: no bot present')
            s.claim(ids[1]);s.db.close()

    def test_email_cannot_be_manually_marked_chat_posted(self):
        with tempfile.TemporaryDirectory() as d:
            s,m,ids=self.setup_store(d);oid=s.stage(m[0],'email',{'text':'Synthetic'})
            s.settle(oid,'unknown',{})
            with self.assertRaises(ValueError):Companion(s).resolve_unknown(oid,'posted',provider_id='email-id')
            self.assertEqual(s.out(oid)['status'],'unknown');s.db.close()

    def test_cli_empty_initial_sync_still_establishes_baseline(self):
        import io, os
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from labs_meet import cli
        with tempfile.TemporaryDirectory() as d:
            s,m,ids=self.setup_store(d);s.db.close()
            calls=[]
            class FakeApp:
                def __init__(self,*a,**kw):pass
                def sync(self,mid,baseline=False):calls.append(baseline);return []
            with patch.dict(os.environ,{},clear=True),patch.object(cli,'Companion',FakeApp),redirect_stdout(io.StringIO()):
                for _ in range(2):cli.main(['--db',str(Path(d)/'state.db'),'sync',m[0]])
            self.assertEqual(calls,[True,False])
