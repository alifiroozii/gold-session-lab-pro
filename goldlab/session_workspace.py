"""Restart-independent session calendar and explicit research queue; no order path."""
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from goldlab.sessions import SessionManager, SessionConfig

UTC = timezone.utc
TEHRAN = ZoneInfo('Asia/Tehran')
PLAN_VERSION = 'session-research-v1'


class SessionWorkspace:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS session_provider_m1 '
                         '(time INTEGER PRIMARY KEY, high REAL NOT NULL, low REAL NOT NULL, '
                         'source TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS session_research_tasks '
                         '(task_id TEXT PRIMARY KEY, strategy TEXT NOT NULL, timeframe TEXT NOT NULL, '
                         'status TEXT NOT NULL, created_at TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT "")')

    def save_provider_candles(self, bars):
        """Called only from the authenticated historical provider path, never from widgets."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany('INSERT OR REPLACE INTO session_provider_m1 VALUES (?,?,?,?)',
                             [(int(c.timestamp.timestamp()),c.high,c.low,'OANDA_HISTORICAL_MID')
                              for c in bars if c.is_closed])

    def calendar(self, now=None, days=7):
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError('timezone-aware clock required')
        days = max(1,min(int(days),30))
        lower = datetime.combine(now.astimezone(TEHRAN).date()-timedelta(days=days-1),time(),TEHRAN)
        upper = datetime.combine(now.astimezone(TEHRAN).date()+timedelta(days=2),time(),TEHRAN)
        cfg = SessionConfig()
        definitions = [
            ('sydney','سیدنی','Australia/Sydney',time(8),time(17)),
            ('tokyo','توکیو','Asia/Tokyo',cfg.tokyo_start,cfg.tokyo_end),
            ('asia','محدوده مرجع آسیا','America/New_York',cfg.asia_ref_ny_start,cfg.asia_ref_ny_end),
            ('london','لندن','Europe/London',cfg.london_start,cfg.london_end),
            ('new_york','نیویورک','America/New_York',cfg.ny_start,cfg.ny_end),
        ]
        manager = SessionManager()
        windows = []
        for offset in range(-days-1,3):
            date = now.astimezone(TEHRAN).date()+timedelta(days=offset)
            bounds = {}
            for key,label,zone,start,end in definitions:
                tz = ZoneInfo(zone)
                a = datetime.combine(date,start,tz).astimezone(UTC)
                b = datetime.combine(date+timedelta(days=end<=start),end,tz).astimezone(UTC)
                bounds[key] = (a,b)
                windows.append((key,label,a,b))
            a = max(bounds['london'][0],bounds['new_york'][0])
            b = min(bounds['london'][1],bounds['new_york'][1])
            windows.append(('overlap','هم‌پوشانی لندن و نیویورک',a,b))
        with sqlite3.connect(self.db_path) as conn:
            bars = conn.execute('SELECT time,high,low FROM session_provider_m1 '
                                'WHERE time>=? AND time+60<=? ORDER BY time',
                                (int(lower.timestamp()),int(now.timestamp()))).fetchall()
        result = []
        for key,label,a,b in windows:
            if not lower <= a < upper or b <= a:
                continue
            # Calendar windows are conventions, not claims of tradable quotes.
            scheduled_open = any(not manager.is_market_closed(a+timedelta(minutes=i))
                                 for i in range(0,int((b-a).total_seconds()/60),30))
            if not scheduled_open:
                status = 'MARKET_CLOSED'
            elif now<a:
                status = 'UPCOMING'
            elif now>=b:
                status = 'FINISHED'
            else:
                status = 'IN_PROGRESS' if not manager.is_market_closed(now) else 'MARKET_CLOSED'
            start,end = int(a.timestamp()),int(b.timestamp())
            observed = [bar for bar in bars if start<=bar[0] and bar[0]+60<=end]
            expected = max(0,int((min(now,b)-a).total_seconds()//60))
            result.append(dict(id=f'{key}-{start}',key=key,label=label,
                date=a.astimezone(TEHRAN).date().isoformat(),start=start,end=end,status=status,
                high=max((x[1] for x in observed),default=None),
                low=min((x[2] for x in observed),default=None),bars=len(observed),
                coverage='COMPLETE' if expected>0 and len(observed)==expected else
                         ('PARTIAL' if observed else 'UNAVAILABLE')))
        return dict(now=int(now.timestamp()),timezone='Asia/Tehran',days=days,
                    schedule_only=True,sessions=sorted(result,key=lambda s:(s['start'],s['key'])))

    def queue_research(self):
        added = 0
        with sqlite3.connect(self.db_path) as conn:
            for strategy in ('S1_BREAKOUT_RETEST','S2_SWEEP_RECLAIM_BOS_RETEST'):
                for timeframe in ('1m','5m','15m'):
                    added += conn.execute('INSERT OR IGNORE INTO session_research_tasks '
                        '(task_id,strategy,timeframe,status,created_at) VALUES (?,?,?,?,?)',
                        (f'{PLAN_VERSION}:{strategy}:{timeframe}',strategy,timeframe,'QUEUED',
                         datetime.now(UTC).isoformat())).rowcount
        return added

    def research(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            tasks = [dict(x) for x in conn.execute('SELECT * FROM session_research_tasks ORDER BY task_id')]
        return dict(version=PLAN_VERSION,research_balance=1000,authorizes_paper_auto=False,
            execution_timeframe='5m',candidate_timeframes=['1m','5m','15m'],
            verdict='AWAITING_VERIFIED_DATA',tasks=tasks,
            protocol='docs/SESSION_RESEARCH_PROTOCOL.md',
            steps=['تثبیت محدوده سشن با کندل بسته', 'شکست و ریتست یا Sweep و Reclaim',
                   'تأیید BOS / CHoCH و رد سایه', 'ورود فقط پس از تأیید، با مظنه بعدی معتبر',
                   'بررسی حد ضرر، حد سود، اسپرد و ریسک', 'ثبت دلیل، نتیجه و آزمون خارج از نمونه'])
