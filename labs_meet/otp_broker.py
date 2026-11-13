"""Bounded request-driven unofficial OTP allocation, disabled until reviewed.

Existing gateway retains normal outbound content under operator/backup access.
Short code validity limits usefulness, not storage duration. Never ask customers
to reply with their code. This ledger is new-app-only: other senders do not share
its15secondgap/atomicreservation. Aggregate read leaves headroom but can race.
"""
import hashlib,hmac,re,secrets,sqlite3,time,json,datetime,socket,stat,os
from pathlib import Path
from urllib.parse import quote
from .adapters import endpoint,request

class OtpUnavailable(ValueError):pass

class BoundedOtpBroker:
    def __init__(self,path,key,*,base,api_key,session,health,aggregate,enabled=False,allowed_numbers=(),test_id=None,clock=time.time,api=request):
        if not isinstance(allowed_numbers,(tuple,list)) or len(allowed_numbers)>1 or any(not isinstance(n,str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}',n) for n in allowed_numbers):raise OtpUnavailable('One explicit owner-test recipient required')
        if test_id is not None and (not isinstance(test_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,96}',test_id)):raise OtpUnavailable('Explicit test authorization identity required')
        self.test_id=test_id
        self.allowed_numbers=frozenset(allowed_numbers)
        if not isinstance(key,bytes) or len(key)<32:raise OtpUnavailable('Dedicated OTP ledger key required')
        if not all(isinstance(x,str) and x for x in (api_key,session)):raise OtpUnavailable('Operator-bound sender required')
        p=Path(path).absolute();parent=p.parent
        # Existing ancestors must not redirect the private ledger. Shared /tmp
        # is permitted only as a sticky system directory, never as ledger parent.
        for ancestor in (parent,*parent.parents):
            if ancestor.is_symlink():raise OtpUnavailable('OTP ledger directory refused')
            if ancestor.exists():
                info=ancestor.stat()
                if not stat.S_ISDIR(info.st_mode):raise OtpUnavailable('OTP ledger directory refused')
                if info.st_mode&0o022 and not (info.st_uid in (0,os.geteuid()) and info.st_mode&stat.S_ISVTX):raise OtpUnavailable('Untrusted OTP ledger ancestor')
        parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        info=parent.stat()
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:raise OtpUnavailable('Private app-owned OTP ledger directory required')
        for file in (p,Path(str(p)+'-wal'),Path(str(p)+'-shm')):
            if file.is_symlink():raise OtpUnavailable('OTP ledger path refused')
            if file.exists():
                info=file.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600:raise OtpUnavailable('Private OTP ledger file required')
        # Create private inode before SQLite opens it. No chmod of foreign files.
        try:fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        except FileExistsError:pass
        else:os.close(fd)
        self.db=sqlite3.connect(p);self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,phone_key TEXT NOT NULL,created REAL NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS test_attempts(test_id TEXT PRIMARY KEY,attempt TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sender_lock(id INTEGER PRIMARY KEY CHECK(id=1),attempt TEXT NOT NULL);
        ''');self.db.commit()
        self.key,self.base,self.api_key,self.session=key,endpoint(base),api_key,session
        self.health,self.aggregate,self.enabled,self.clock,self.api=health,aggregate,enabled,clock,api
    def seal(self,phone):return hmac.new(self.key,('otp-phone:'+phone).encode(),hashlib.sha256).hexdigest()
    def observe(self):
        # Callbacks must read current source each time, no stale caching. They
        # return explicit readiness and all-status outbound count for UTC day.
        health=self.health();count=self.aggregate()
        now=self.clock();day=int(now//86400)*86400
        if not isinstance(health,dict) or health.get('ready') is not True or health.get('session')!=self.session or type(health.get('as_of')) not in (int,float) or not 0<=now-health['as_of']<=5:raise OtpUnavailable('Sender health not verified')
        if not isinstance(count,dict) or type(count.get('count')) is not int or count['count']<0 or count.get('utc_day')!=day or type(count.get('as_of')) not in (int,float) or not 0<=now-count['as_of']<=5:raise OtpUnavailable('Aggregate sender budget not verified')
        if count['count']>=150:raise OtpUnavailable('Sender budget held for existing work')
    def reserve(self,phone):
        if phone not in self.allowed_numbers:raise OtpUnavailable('Recipient outside owner-test scope')
        now=self.clock();day=int(now//86400)*86400;pk=self.seal(phone);attempt=secrets.token_hex(16)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.test_id is not None and self.db.execute('SELECT 1 FROM test_attempts WHERE test_id=?',(self.test_id,)).fetchone():raise OtpUnavailable('Single test attempt already reserved')
            if self.db.execute('SELECT 1 FROM sender_lock').fetchone():raise OtpUnavailable('Sender busy or previous send uncertain')
            if self.db.execute('SELECT count(*) FROM attempts WHERE created>=?',(day,)).fetchone()[0]>=10:raise OtpUnavailable('OTP daily allocation reached')
            if self.db.execute('SELECT count(*) FROM attempts WHERE created>=? AND phone_key=?',(day,pk)).fetchone()[0]>=3:raise OtpUnavailable('Number allocation reached')
            own=self.db.execute('SELECT max(created) FROM attempts WHERE phone_key=?',(pk,)).fetchone()[0]
            last=self.db.execute('SELECT max(created) FROM attempts').fetchone()[0]
            if own is not None and now-own<60:raise OtpUnavailable('Wait before requesting another code')
            if last is not None and now-last<15:raise OtpUnavailable('Sender pacing wait')
            if self.test_id is not None:self.db.execute('INSERT INTO test_attempts VALUES(?,?)',(self.test_id,attempt))
            self.db.execute('INSERT INTO attempts VALUES(?,?,?,?)',(attempt,pk,now,'reserved'))
            self.db.execute('INSERT INTO sender_lock VALUES(1,?)',(attempt,))
        return attempt
    def settle(self,attempt,status,release):
        with self.db:
            self.db.execute('UPDATE attempts SET status=? WHERE id=?',(status,attempt))
            if release:self.db.execute('DELETE FROM sender_lock WHERE attempt=?',(attempt,))
    def __call__(self,phone,code,ttl):
        if self.enabled is not True:raise OtpUnavailable('OTP sender disabled pending acceptance')
        if not isinstance(phone,str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}',phone) or not isinstance(code,str) or not re.fullmatch(r'[0-9]{4}',code) or ttl!=180:raise OtpUnavailable('OTP request policy refused')
        if phone not in self.allowed_numbers:raise OtpUnavailable('Recipient outside owner-test scope')
        # No recipient lookup happens before local abuse/allocation reservation.
        self.observe();attempt=self.reserve(phone);send_started=False
        try:
            self.observe()
            sid=quote(self.session,safe='')
            resolved=self.api(self.base,f'/api/sessions/{sid}/contacts/check/{phone[1:]}',self.api_key)
            if not isinstance(resolved,dict) or str(resolved.get('number','')).lstrip('+')!=phone[1:] or resolved.get('exists') is not True or not isinstance(resolved.get('whatsappId'),str) or not re.fullmatch(r'[0-9]+@(?:c\.us|s\.whatsapp\.net|lid)',resolved['whatsappId']):raise OtpUnavailable('Recipient resolution not confirmed')
            self.observe()
            text=code+' is your Lathar Labs sign-in code. Expires in 3 minutes. Enter it only on bot.143.lat. Do not reply with or share this code. If you did not request it, ignore this message.'
            send_started=True
            result=self.api(self.base,f'/api/sessions/{sid}/messages/send-text',self.api_key,'POST',{'chatId':resolved['whatsappId'],'text':text})
            if not isinstance(result,dict) or not isinstance(result.get('messageId'),str) or not result['messageId'].strip():raise OtpUnavailable('Send outcome unknown')
            self.settle(attempt,'engine-accepted',True)
            return True
        except Exception:
            # Unknown send keeps persistent single-inflight lock, even after
            # process restart. Operator reconciles externally before clearing.
            self.settle(attempt,'unknown' if send_started else 'not-sent',not send_started)
            raise OtpUnavailable('OTP request not confirmed. No automatic retry.') from None
    def close_checked(self,attempt):
        raise OtpUnavailable('Reconcile provider evidence and ledger offline; no customer unlock endpoint')


class GatewayHealth:
    """Actual gateway GET session contract; no guessed status endpoint."""
    def __init__(self,base,key,session,phone,*,api=request,clock=time.time):
        self.base,self.key,self.session,self.phone,self.api,self.clock=endpoint(base),key,session,phone.lstrip('+'),api,clock
    def __call__(self):
        result=self.api(self.base,'/api/sessions/'+quote(self.session,safe=''),self.key)
        ready=isinstance(result,dict) and {'id','phone','status','engineLoaded','restriction','lastError'}<=set(result) and result.get('id')==self.session and str(result.get('phone',''))==self.phone and result.get('status')=='ready' and result.get('engineLoaded') is True and result.get('restriction') is None and result.get('lastError') is None
        return {'session':self.session,'ready':ready,'as_of':self.clock()}

def validate_aggregate(result,session,now):
    try:
        if not isinstance(result,dict) or set(result)!={'session_id','utc_day','outgoing_count','observed_at_utc'} or result['session_id']!=session:raise ValueError()
        day=datetime.datetime.fromtimestamp(now,datetime.timezone.utc).strftime('%Y-%m-%d')
        if result['utc_day']!=day or type(result['outgoing_count']) is not int or result['outgoing_count']<0:raise ValueError()
        observed=datetime.datetime.fromisoformat(result['observed_at_utc'].replace('Z','+00:00'))
        if observed.utcoffset()!=datetime.timedelta(0):raise ValueError()
        stamp=observed.timestamp()
        if not 0<=now-stamp<=5:raise ValueError()
        return {'count':result['outgoing_count'],'utc_day':int(now//86400)*86400,'as_of':stamp}
    except (ValueError,TypeError,KeyError,OSError,AttributeError):raise OtpUnavailable('Aggregate sender budget unavailable or stale') from None

class AggregateSocket:
    """Read fixed content-free COUNT protocol from private host-owned collector.

    A separately reviewed runtime UID/access design is required. This consumer
    never opens or mounts the gateway database. No customer-selectable path.
    """
    def __init__(self,path,session,*,collector_uid,ipc_gid,clock=time.time):
        if type(collector_uid) is not int or collector_uid<0 or type(ipc_gid) is not int or ipc_gid<0 or collector_uid==os.geteuid():raise OtpUnavailable('Separate collector UID and IPC group required')
        self.path,self.session,self.clock,self.collector_uid,self.ipc_gid=Path(path),session,clock,collector_uid,ipc_gid
    def __call__(self):
        try:
            p=self.path;parent=p.parent
            if p.is_symlink() or parent.is_symlink():raise ValueError()
            info=p.stat();directory=parent.stat()
            if not stat.S_ISSOCK(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o660 or stat.S_IMODE(directory.st_mode)!=0o750 or info.st_uid!=self.collector_uid or directory.st_uid!=self.collector_uid or info.st_gid!=self.ipc_gid or directory.st_gid!=self.ipc_gid:raise ValueError()
            deadline=time.monotonic()+2
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.settimeout(2);client.connect(str(p));client.settimeout(max(.001,deadline-time.monotonic()));client.sendall(b'COUNT\n');payload=b''
                while b'\n' not in payload:
                    left=deadline-time.monotonic()
                    if left<=0:raise ValueError()
                    client.settimeout(left);block=client.recv(513-len(payload))
                    if not block:raise ValueError()
                    payload+=block
                    if len(payload)>512:raise ValueError()
            if not payload.endswith(b'\n') or payload.count(b'\n')!=1:raise ValueError()
            return validate_aggregate(json.loads(payload),self.session,self.clock())
        except (ValueError,TypeError,OSError,AttributeError):raise OtpUnavailable('Aggregate sender budget unavailable or stale') from None
