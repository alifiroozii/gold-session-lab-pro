/* Session schedule uses server time and survives browser/project downtime. */
(() => {
    const stateNames = {IN_PROGRESS:'در جریان',FINISHED:'پایان‌یافته',UPCOMING:'پیش رو',MARKET_CLOSED:'بازار تعطیل'};
    const colors = {sydney:'#a78bfa',tokyo:'#06b6d4',asia:'#3b82f6',london:'#10b981',new_york:'#f59e0b',overlap:'#8b5cf6'};
    let snapshot = null, fetching = false;
    const formatTime = value => new Intl.DateTimeFormat('fa-IR', {timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value * 1000));
    const dayKey = value => new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value*1000));
    const formatEnd = session => formatTime(session.end) + (dayKey(session.end)!==dayKey(session.start) ? ' (روز بعد)' : '');
    const formatDay = value => new Intl.DateTimeFormat('fa-IR', {timeZone:'Asia/Tehran',weekday:'short',month:'short',day:'numeric'}).format(new Date(value + 'T12:00:00+03:30'));
    const node = (tag, text, className) => {const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(className) el.className=className; return el;};
    function renderHistory() {
        if(!snapshot) return;
        const selected = document.getElementById('sessionHistoryDate').value;
        const rows = document.getElementById('sessionHistoryRows'); rows.replaceChildren();
        snapshot.sessions.filter(s=>s.date===selected).forEach(s=>{
            const row=node('tr');
            const price=s.high===null ? '—' : `${s.high.toFixed(2)} / ${s.low.toFixed(2)}`;
            const coverage=s.coverage==='COMPLETE' ? 'کامل' : (s.coverage==='PARTIAL' ? `ناقص · ${s.bars} کندل` : 'دادهٔ قیمت موجود نیست');
            [s.label,formatTime(s.start),formatEnd(s),stateNames[s.status],price,coverage].forEach(v=>row.append(node('td',v)));
            rows.append(row);
        });
    }
    function renderCalendar(data) {
        snapshot=data;
        const cards=document.getElementById('sessionNowCards'); cards.replaceChildren();
        const currentDay=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(data.now*1000));
        Object.keys(colors).forEach(key=>{
            const windows=data.sessions.filter(s=>s.key===key);
            const chosen=windows.find(s=>s.status==='IN_PROGRESS') || windows.find(s=>s.start>data.now && s.status==='UPCOMING') || windows[windows.length-1];
            if(!chosen) return;
            const card=node('article',undefined,'session-now-card'+(chosen.status==='IN_PROGRESS'?' is-active':''));
            card.style.setProperty('--session-color',colors[key]);
            card.append(node('h3',chosen.label),node('span',stateNames[chosen.status],'session-state'),node('p',formatDay(chosen.date)),node('p',`${formatTime(chosen.start)} — ${formatEnd(chosen)}`));
            if(chosen.status==='IN_PROGRESS') card.append(node('p',`${Math.max(0,Math.ceil((chosen.end-data.now)/60))} دقیقه تا پایان`));
            cards.append(card);
        });
        const selector=document.getElementById('sessionHistoryDate');
        const previous=selector.value;
        const dates=[...new Set(data.sessions.map(s=>s.date))].sort().reverse();
        selector.replaceChildren(...dates.map(date=>{const option=node('option',formatDay(date)); option.value=date; return option;}));
        selector.value=dates.includes(previous)?previous:(dates.includes(currentDay)?currentDay:dates[0]);
        renderHistory();
        document.getElementById('sessionSyncStatus').textContent=`به‌روز شد · ${formatTime(data.now)} تهران`;
    }
    async function refreshCalendar() {
        if(fetching) return; fetching=true;
        try {
            const days=document.getElementById('sessionHistoryDays').value;
            const response=await fetch(`/api/sessions/calendar?days=${encodeURIComponent(days)}`,{cache:'no-store'});
            if(!response.ok) throw new Error('calendar');
            renderCalendar(await response.json());
        } catch(_) {document.getElementById('sessionSyncStatus').textContent='به‌روزرسانی قطع است؛ زمان‌های نمایش‌داده‌شده ممکن است قدیمی باشند';}
        finally {fetching=false;}
    }
    async function refreshResearch() {
        const el=document.getElementById('sessionResearchStatus');
        try {
            const response=await fetch('/api/research/session-plan',{cache:'no-store'});
            if(!response.ok) throw new Error('research');
            const plan=await response.json();
            el.textContent=plan.tasks.length ? `${plan.tasks.length} آزمایش در صف بررسی · نتیجهٔ عملکرد هنوز ثبت نشده` : 'هنوز طرحی ثبت نشده؛ منتظر دادهٔ تاریخی تأییدشده';
        } catch(_) {el.textContent='صف پژوهش در دسترس نیست';}
    }
    document.addEventListener('DOMContentLoaded',()=>{
        document.getElementById('sessionHistoryDays').addEventListener('change',refreshCalendar);
        document.getElementById('sessionHistoryDate').addEventListener('change',renderHistory);
        document.getElementById('btnQueueSessionResearch').addEventListener('click',async event=>{
            const button=event.currentTarget; button.disabled=true;
            try {
                const response=await fetch('/api/research/session-plan/queue',{method:'POST'});
                if(!response.ok) throw new Error('queue');
                await refreshResearch();
            } catch(_) {document.getElementById('sessionResearchStatus').textContent='ثبت درخواست ناموفق بود؛ دوباره تلاش کنید';}
            finally {button.disabled=false;}
        });
        refreshCalendar(); refreshResearch();
        setInterval(()=>{if(!document.hidden) refreshCalendar();},15000);
        document.addEventListener('visibilitychange',()=>{if(!document.hidden) {refreshCalendar();refreshResearch();}});
        window.addEventListener('pageshow',refreshCalendar);
    });
})();
