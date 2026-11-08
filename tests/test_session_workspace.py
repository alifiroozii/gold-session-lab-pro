from pathlib import Path

from datetime import datetime, timedelta, timezone

from goldlab.session_workspace import SessionWorkspace
from goldlab.types import Candle

UTC = timezone.utc


def test_reopen_reconstructs_all_sessions_without_browser(tmp_path):
    path = str(tmp_path / 'sessions.sqlite')
    now = datetime(2026, 11, 9, 14, tzinfo=UTC)
    first = SessionWorkspace(path).calendar(now, days=7)
    second = SessionWorkspace(path).calendar(now, days=7)
    assert first == second
    assert {s['key'] for s in first['sessions']} == {'sydney','tokyo','asia','london','new_york','overlap'}
    assert any(s['status'] == 'IN_PROGRESS' for s in first['sessions'])
    assert any(s['status'] == 'FINISHED' for s in first['sessions'])
    assert all(s['high'] is None for s in first['sessions'])


def test_london_new_york_dst_mismatch(tmp_path):
    svc = SessionWorkspace(str(tmp_path / 's.sqlite'))
    def overlap(day):
        return next(s for s in svc.calendar(datetime(2026,10,day,16,tzinfo=UTC),days=1)['sessions']
                    if s['key']=='overlap' and s['date']==f'2026-10-{day:02}')
    assert overlap(23)['end'] - overlap(23)['start'] == 4 * 3600
    assert overlap(26)['end'] - overlap(26)['start'] == 5 * 3600


def test_cache_persists_and_never_uses_future_candle(tmp_path):
    path = str(tmp_path / 's.sqlite')
    now = datetime(2026,11,9,14,tzinfo=UTC)
    bars = [Candle(timestamp=now-timedelta(minutes=1),open=100,high=102,low=99,close=101),
            Candle(timestamp=now+timedelta(minutes=1),open=100,high=999,low=1,close=101)]
    svc = SessionWorkspace(path)
    svc.save_provider_candles(bars)
    svc.save_provider_candles(bars)
    london = next(s for s in SessionWorkspace(path).calendar(now,days=1)['sessions']
                  if s['key']=='london' and s['date']=='2026-11-09')
    assert london['high'] == 102 and london['bars'] == 1
    assert london['coverage'] == 'PARTIAL'


def test_weekend_is_never_displayed_as_active_market(tmp_path):
    result = SessionWorkspace(str(tmp_path / 's.sqlite')).calendar(
        datetime(2026,11,7,14,tzinfo=UTC), days=1)
    assert not any(s['status']=='IN_PROGRESS' for s in result['sessions'])


def test_research_queue_is_persistent_and_deduplicated(tmp_path):
    path = str(tmp_path/'s.sqlite')
    svc = SessionWorkspace(path)
    assert svc.queue_research() == 6
    assert SessionWorkspace(path).queue_research() == 0
    plan = svc.research()
    assert plan['research_balance'] == 1000
    assert len(plan['tasks']) == 6
    assert all(t['status']=='QUEUED' for t in plan['tasks'])
    assert plan['authorizes_paper_auto'] is False


def test_research_tasks_reach_agent_handoff_without_claiming_ai(tmp_path):
    from goldlab.agent_bridge import AgentBridge
    path = str(tmp_path / 'research.sqlite')
    SessionWorkspace(path).queue_research()
    bridge = AgentBridge(path)
    destination = tmp_path / 'REVIEW.md'
    bridge.write_handoff(str(destination))
    content = destination.read_text()
    assert 'S1_BREAKOUT_RETEST' in content
    assert 'docs/SESSION_RESEARCH_PROTOCOL.md' in content
    assert bridge.state()['agent_status'] == 'NOT_CONNECTED'


def test_session_api_queue_is_honest_and_deduplicated(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as runtime
    from goldlab.agent_bridge import AgentBridge
    path = str(tmp_path / 'api.sqlite')
    monkeypatch.setattr(runtime, 'session_workspace', SessionWorkspace(path))
    bridge = AgentBridge(path)
    monkeypatch.setattr(bridge, 'write_handoff', lambda: None)
    monkeypatch.setattr(runtime, 'agent_bridge', bridge)
    client = TestClient(runtime.app)
    assert client.get('/api/sessions/calendar?days=30').status_code == 200
    first = client.post('/api/research/session-plan/queue').json()
    assert first['added'] == 6 and first['ai_executed'] is False
    assert client.post('/api/research/session-plan/queue').json()['added'] == 0
    assert len(client.get('/api/research/session-plan').json()['tasks']) == 6


def test_paper_close_reaches_memory_and_matching_strategy(tmp_path, monkeypatch):
    import app as runtime
    from goldlab.agent_bridge import AgentBridge
    from goldlab.market_safety import MarketQuote
    from goldlab.state_machine import SessionTradingStateMachine, ActiveSetupContext
    from goldlab.types import SignalDirection
    from types import SimpleNamespace
    path = str(tmp_path/'close.sqlite')
    machine = SessionTradingStateMachine(path)
    machine.active_setup = ActiveSetupContext(order_id='MATCH',position_id='POS',direction=SignalDirection.BUY)
    monkeypatch.setattr(runtime,'session_state_machine',machine)
    bridge = AgentBridge(path)
    monkeypatch.setattr(runtime,'agent_bridge',bridge)
    monkeypatch.setattr(runtime,'bot',SimpleNamespace(on_trade_closed=lambda pnl: None))
    position=SimpleNamespace(status=SimpleNamespace(value='CLOSED'),order_id='MATCH',realized_pnl=-5,
        direction=SimpleNamespace(value='BUY'),entry_price=101,close_price=100,current_price=100,close_reason='STOP_LOSS')
    monkeypatch.setattr(runtime,'broker',SimpleNamespace(positions={'POS':position}))
    quote=MarketQuote(100,100.2,datetime(2026,11,9,14,tzinfo=UTC),'OANDA_V20_READ_ONLY',tradeable=True)
    assert runtime.record_paper_position_events({'POS'},quote)==['POS']
    assert machine.active_setup is None
    assert machine.current_state.value=='CLOSED'
    assert runtime.record_paper_position_events({'POS'},quote)==[]
    assert 'POS' in Path(bridge.write_handoff(str(tmp_path/'review.md'))).read_text()


def test_manual_fill_does_not_change_unrelated_strategy(tmp_path, monkeypatch):
    import app as runtime
    from types import SimpleNamespace
    from goldlab.agent_bridge import AgentBridge
    from goldlab.market_safety import MarketQuote
    from goldlab.state_machine import SessionTradingStateMachine, ActiveSetupContext
    path=str(tmp_path/'manual.sqlite')
    machine=SessionTradingStateMachine(path)
    machine.active_setup=ActiveSetupContext(order_id='STRATEGY_ORDER')
    original=machine.current_state
    monkeypatch.setattr(runtime,'session_state_machine',machine)
    monkeypatch.setattr(runtime,'agent_bridge',AgentBridge(path))
    monkeypatch.setattr(runtime,'broker',SimpleNamespace(positions={
        'MANUAL':SimpleNamespace(status=SimpleNamespace(value='OPEN'),order_id='MANUAL_ORDER')}))
    quote=MarketQuote(100,100.2,datetime(2026,11,9,14,tzinfo=UTC),'OANDA_V20_READ_ONLY',tradeable=True)
    assert runtime.record_paper_position_events(set(),quote)==[]
    assert machine.current_state==original and machine.active_setup.position_id is None
    runtime.broker.positions['MANUAL'].order_id='STRATEGY_ORDER'
    runtime.record_paper_position_events(set(),quote)
    assert machine.active_setup.position_id=='MANUAL'
    assert machine.last_candle_id==quote.timestamp.isoformat()
