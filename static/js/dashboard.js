// Gold Session Lab Pro — Interactive Frontend Controller

let chart = null;
let candleSeries = null;
let currentDirection = "BUY";
let currentTimeframe = "5m";
let currentCandles = [];
let replayIndex = 0;
let isReplaying = false;
let replayTimer = null;

document.addEventListener("DOMContentLoaded", () => {
    initClock();
    initTabs();
    initChart();
    initForms();
    fetchMarketData();
    fetchBrokerData();
    fetchCalendarData();
    fetchBotData();
    initWebSocket();
    setInterval(fetchBrokerData, 3000);
    setInterval(fetchBotData, 4000);
});

// 1. Clock
function initClock() {
    const clockEl = document.getElementById("systemClock");
    setInterval(() => {
        const now = new Date();
        clockEl.innerText = "UTC " + now.toUTCString().slice(17, 25);
    }, 1000);
}

// 2. Tab Navigation
function initTabs() {
    const tabBtns = document.querySelectorAll(".nav-btn");
    const panes = document.querySelectorAll(".tab-pane");

    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            panes.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            const targetId = btn.getAttribute("data-tab");
            const targetPane = document.getElementById(targetId);
            if (targetPane) {
                targetPane.classList.add("active");
            }
            if (targetId === "tab-chart" && chart) {
                window.dispatchEvent(new Event("resize"));
            }
        });
    });
}

// 3. Lightweight Charts Initializer
function initChart() {
    const container = document.getElementById("chartContainer");
    if (!container) return;

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 520,
        layout: {
            background: { color: "#FFFFFF" },
            textColor: "#172033",
            fontFamily: "Vazirmatn, sans-serif"
        },
        grid: {
            vertLines: { color: "#F1F5F9" },
            horzLines: { color: "#F1F5F9" }
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal
        },
        rightPriceScale: {
            borderColor: "#E2E8F0"
        },
        timeScale: {
            borderColor: "#E2E8F0",
            timeVisible: true,
            secondsVisible: false
        }
    });

    candleSeries = chart.addCandlestickSeries({
        upColor: "#16A34A",
        downColor: "#DC2626",
        borderVisible: false,
        wickUpColor: "#16A34A",
        wickDownColor: "#DC2626"
    });

    window.addEventListener("resize", () => {
        if (chart && container) {
            chart.applyOptions({ width: container.clientWidth });
        }
    });

    // Timeframe selector
    document.querySelectorAll(".tf-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentTimeframe = btn.getAttribute("data-tf");
            switchTimeframe(currentTimeframe);
        });
    });

    // Replay controls
    document.getElementById("btnReplayPlay")?.addEventListener("click", toggleReplay);
    document.getElementById("btnReplayNext")?.addEventListener("click", stepReplayNext);
    document.getElementById("btnReplayPrev")?.addEventListener("click", stepReplayPrev);
}

// 4. Market Data Loader
async function fetchMarketData() {
    try {
        const res = await fetch(`/api/market?timeframe=${currentTimeframe}`);
        if (!res.ok) return;
        const data = await res.json();
        renderMarketData(data);
    } catch (err) {
        console.error("Error fetching market data:", err);
    }
}

function renderMarketData(data) {
    if (!data || !data.candles || data.candles.length === 0) return;
    currentCandles = data.candles;
    replayIndex = currentCandles.length;

    // Set series data
    const chartBars = currentCandles.map(c => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close
    }));
    candleSeries.setData(chartBars);

    // Update Quote Box
    const lastBar = currentCandles[currentCandles.length - 1];
    const bid = lastBar.close;
    const ask = +(bid + 0.25).toFixed(2);
    document.getElementById("quoteBid").innerText = bid.toFixed(2);
    document.getElementById("quoteAsk").innerText = ask.toFixed(2);

    // Update Levels
    const stats = data.session_stats || {};
    if (stats.asia) {
        document.getElementById("lblAsiaH").innerText = stats.asia.high ?? "-";
        document.getElementById("lblAsiaL").innerText = stats.asia.low ?? "-";
        document.getElementById("lblAsiaM").innerText = stats.asia.midline ?? "-";
    }
    if (stats.london) {
        document.getElementById("lblLonH").innerText = stats.london.high ?? "-";
        document.getElementById("lblLonL").innerText = stats.london.low ?? "-";
    }
    if (stats.pd) {
        document.getElementById("lblPDH").innerText = stats.pd.high ?? "-";
        document.getElementById("lblPDL").innerText = stats.pd.low ?? "-";
    }

    // Set Markers on Chart
    const markers = [];
    if (data.signals) {
        data.signals.forEach(s => {
            markers.push({
                time: s.time,
                position: s.direction === "BUY" ? "belowBar" : "aboveBar",
                color: s.direction === "BUY" ? "#2563EB" : "#D6A54B",
                shape: s.direction === "BUY" ? "arrowUp" : "arrowDown",
                text: `${s.setup_name} (${s.direction})`
            });
        });
    }

    if (data.trades) {
        data.trades.forEach(t => {
            if (t.outcome === "WIN") {
                markers.push({
                    time: Math.floor(new Date(t.entry_time).getTime() / 1000),
                    position: "inBar",
                    color: "#16A34A",
                    shape: "circle",
                    text: `برد: +${t.realized_r}R`
                });
            } else if (t.outcome === "LOSS") {
                markers.push({
                    time: Math.floor(new Date(t.entry_time).getTime() / 1000),
                    position: "inBar",
                    color: "#DC2626",
                    shape: "circle",
                    text: `ضرر: -1R`
                });
            }
        });
    }

    markers.sort((a, b) => a.time - b.time);
    candleSeries.setMarkers(markers);

    // Update Signals Table
    renderSignalsTable(data.signals || []);

    // Update Metrics
    if (data.metrics) {
        document.getElementById("stratWinRate").innerText = data.metrics.win_rate_pct ? `${data.metrics.win_rate_pct}%` : "-";
        document.getElementById("stratPF").innerText = `فاکتور سود: ${data.metrics.profit_factor ?? "-"}`;
        document.getElementById("stratExpectancy").innerText = `${data.metrics.expectancy_r ?? 0.0} R`;
        document.getElementById("stratMaxDD").innerText = `حداکثر افت: ${data.metrics.max_drawdown_r ?? 0.0} R`;
        document.getElementById("totalTradesCount").innerText = `تعداد معاملات: ${data.metrics.total_trades ?? 0}`;
    }
}

// 5. Switch Timeframe
async function switchTimeframe(tf) {
    try {
        await fetch("/api/market/timeframe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ timeframe: tf })
        });
        fetchMarketData();
    } catch (e) {
        console.error(e);
    }
}

// 6. Signals Table
function renderSignalsTable(signals) {
    const tbody = document.querySelector("#signalsTable tbody");
    if (!tbody) return;
    if (signals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">سیگنالی در این بازه ثبت نشده است.</td></tr>';
        return;
    }
    tbody.innerHTML = signals.map(s => `
        <tr>
            <td>${new Date(s.time * 1000).toLocaleTimeString("fa-IR")}</td>
            <td><strong>${s.setup_name}</strong></td>
            <td><span class="badge ${s.direction === 'BUY' ? 'badge-pd' : 'badge-london'}">${s.direction}</span></td>
            <td>${s.entry_price.toFixed(2)}</td>
            <td>${s.sl ? s.sl.toFixed(2) : '-'}</td>
            <td>${s.tp ? s.tp.toFixed(2) : '-'}</td>
            <td>${s.risk_r.toFixed(2)}</td>
            <td>${s.reason}</td>
        </tr>
    `).join("");
}

// 7. Broker Data
async function fetchBrokerData() {
    try {
        const res = await fetch("/api/broker/account");
        if (!res.ok) return;
        const acc = await res.json();

        document.getElementById("accBalance").innerText = `$${acc.balance.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
        document.getElementById("accEquity").innerText = `$${acc.equity.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
        document.getElementById("accFloatingSub").innerText = `سود/زیان شناور: $${acc.unrealized_pnl.toFixed(2)}`;
        document.getElementById("accFreeMargin").innerText = `$${acc.margin_free.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
        document.getElementById("accMarginLevel").innerText = `سطح مارجین: ${acc.margin_level_pct}%`;
        document.getElementById("accRealized").innerText = `$${acc.realized_pnl.toFixed(2)}`;

        // Fetch Positions
        const pRes = await fetch("/api/broker/positions");
        if (pRes.ok) {
            const positions = await pRes.json();
            renderPositions(positions);
        }

        // Fetch Pending Orders
        const oRes = await fetch("/api/broker/orders");
        if (oRes.ok) {
            const orders = await oRes.json();
            renderPendingOrders(orders);
        }

        // Fetch Ledger
        const lRes = await fetch("/api/broker/ledger");
        if (lRes.ok) {
            const ledger = await lRes.json();
            renderLedger(ledger);
        }
    } catch (err) {
        console.error(err);
    }
}

function renderPositions(positions) {
    const tbody = document.querySelector("#positionsTable tbody");
    if (!tbody) return;
    if (!positions || positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">هیچ موقعیت بازی وجود ندارد.</td></tr>';
        return;
    }

    tbody.innerHTML = positions.map(p => `
        <tr>
            <td>${p.position_id}</td>
            <td>${p.symbol}</td>
            <td><span class="badge ${p.direction === 'BUY' ? 'badge-pd' : 'badge-london'}">${p.direction}</span></td>
            <td>${p.quantity_lots}</td>
            <td>${p.entry_price.toFixed(2)}</td>
            <td>${p.current_price ? p.current_price.toFixed(2) : '-'}</td>
            <td>${p.sl_price ? p.sl_price.toFixed(2) : '-'}</td>
            <td>${p.tp_price ? p.tp_price.toFixed(2) : '-'}</td>
            <td class="${p.unrealized_pnl >= 0 ? 'text-green' : 'text-red'} font-weight-bold">$${p.unrealized_pnl.toFixed(2)}</td>
            <td><button class="btn btn-danger btn-sm" onclick="closePosition('${p.position_id}')">بستن معامله</button></td>
        </tr>
    `).join("");
}

function renderPendingOrders(orders) {
    const tbody = document.querySelector("#pendingOrdersTable tbody");
    if (!tbody) return;
    const pending = orders.filter(o => o.status === "PENDING");
    if (pending.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">سفارش معلقی موجود نیست.</td></tr>';
        return;
    }
    tbody.innerHTML = pending.map(o => `
        <tr>
            <td>${o.order_id}</td>
            <td><span class="badge ${o.direction === 'BUY' ? 'badge-pd' : 'badge-london'}">${o.direction}</span></td>
            <td>${o.order_type}</td>
            <td>${o.quantity_lots}</td>
            <td>${o.target_price ? o.target_price.toFixed(2) : '-'}</td>
            <td>${o.sl_price ? o.sl_price.toFixed(2) : '-'}</td>
            <td>${o.tp_price ? o.tp_price.toFixed(2) : '-'}</td>
            <td>${new Date(o.created_time).toLocaleTimeString("fa-IR")}</td>
            <td><span class="badge badge-asia">${o.status}</span></td>
            <td><button class="btn btn-secondary btn-sm" onclick="cancelOrder('${o.order_id}')">لغو</button></td>
        </tr>
    `).join("");
}

function renderLedger(ledger) {
    const tbody = document.querySelector("#ledgerTable tbody");
    if (!tbody) return;
    if (!ledger || ledger.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">تراکنشی ثبت نشده است.</td></tr>';
        return;
    }
    tbody.innerHTML = ledger.slice(0, 30).map(l => `
        <tr>
            <td>${l.ledger_id}</td>
            <td>${new Date(l.timestamp).toLocaleString("fa-IR")}</td>
            <td><span class="badge ${l.amount >= 0 ? 'badge-pd' : 'badge-london'}">${l.entry_type}</span></td>
            <td class="${l.amount >= 0 ? 'text-green' : 'text-red'}">${l.amount >= 0 ? '+' : ''}$${l.amount.toFixed(2)}</td>
            <td>$${l.balance_after.toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
            <td>${l.notes || '-'}</td>
        </tr>
    `).join("");
}

// 8. Order & Position Actions
window.closePosition = async function(posId) {
    if (!confirm("آیا از بستن این موقعیت مطمئن هستید؟")) return;
    try {
        await fetch(`/api/broker/positions/${posId}/close`, { method: "POST" });
        fetchBrokerData();
    } catch (e) {
        console.error(e);
    }
};

window.cancelOrder = async function(orderId) {
    try {
        await fetch(`/api/broker/orders/${orderId}/cancel`, { method: "POST" });
        fetchBrokerData();
    } catch (e) {
        console.error(e);
    }
};

// 9. Forms & Modals
function initForms() {
    const btnBuy = document.getElementById("btnDirBuy");
    const btnSell = document.getElementById("btnDirSell");
    btnBuy?.addEventListener("click", () => {
        currentDirection = "BUY";
        btnBuy.classList.add("active");
        btnSell.classList.remove("active");
    });
    btnSell?.addEventListener("click", () => {
        currentDirection = "SELL";
        btnSell.classList.add("active");
        btnBuy.classList.remove("active");
    });

    const orderTypeSelect = document.getElementById("orderTypeSelect");
    orderTypeSelect?.addEventListener("change", () => {
        const val = orderTypeSelect.value;
        const targetRow = document.getElementById("targetPriceRow");
        if (targetRow) {
            targetRow.style.display = (val === "LIMIT" || val === "STOP") ? "block" : "none";
        }
    });

    // Submit Order
    document.getElementById("orderForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const lots = parseFloat(document.getElementById("orderLots").value);
        const orderType = document.getElementById("orderTypeSelect").value;
        const targetPrice = parseFloat(document.getElementById("orderTargetPrice")?.value) || null;
        const sl = parseFloat(document.getElementById("orderSL")?.value) || null;
        const tp = parseFloat(document.getElementById("orderTP")?.value) || null;

        try {
            const res = await fetch("/api/broker/order", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    direction: currentDirection,
                    order_type: orderType,
                    quantity_lots: lots,
                    target_price: targetPrice,
                    sl_price: sl,
                    tp_price: tp
                })
            });
            if (res.ok) {
                alert("سفارش آزمایشی با موفقیت در بروکر مجازی ثبت شد.");
                fetchBrokerData();
            } else {
                const err = await res.json();
                alert(`خطا در ثبت سفارش: ${err.detail || "نامشخص"}`);
            }
        } catch (err) {
            console.error(err);
        }
    });

    // Fund Modal
    const fundModal = document.getElementById("fundModal");
    let modalAction = "DEPOSIT";

    document.getElementById("btnModalDeposit")?.addEventListener("click", () => {
        modalAction = "DEPOSIT";
        document.getElementById("modalTitle").innerText = "واریز وجه مجازی به کیف پول";
        fundModal.classList.add("show");
    });

    document.getElementById("btnModalWithdraw")?.addEventListener("click", () => {
        modalAction = "WITHDRAW";
        document.getElementById("modalTitle").innerText = "برداشت وجه مجازی از کیف پول";
        fundModal.classList.add("show");
    });

    document.getElementById("btnModalReset")?.addEventListener("click", async () => {
        if (!confirm("آیا از ریست کامل حساب مجازی و تنظیم موجودی روی $۱۰,۰۰۰ اطمینان دارید؟")) return;
        await fetch("/api/broker/reset", { method: "POST" });
        fetchBrokerData();
    });

    document.getElementById("btnModalCancel")?.addEventListener("click", () => {
        fundModal.classList.remove("show");
    });

    document.getElementById("btnModalConfirm")?.addEventListener("click", async () => {
        const amount = parseFloat(document.getElementById("modalAmount").value);
        if (amount <= 0) return;
        const endpoint = modalAction === "DEPOSIT" ? "/api/broker/deposit" : "/api/broker/withdraw";
        await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ amount: amount })
        });
        fundModal.classList.remove("show");
        fetchBrokerData();
    });

    // Bot Control Buttons
    document.getElementById("btnBotAnalysis")?.addEventListener("click", () => setBotState("ANALYSIS_ONLY"));
    document.getElementById("btnBotAuto")?.addEventListener("click", () => {
        if (confirm("تایید فعال‌سازی ترید خودکار آزمایشی (Paper Auto)؟ در این حالت سفارش‌های آزمایشی بر مبنای سیگنال‌ها در بروکر مجازی ثبت خواهند شد.")) {
            setBotState("PAPER_AUTO");
        }
    });
    document.getElementById("btnBotPause")?.addEventListener("click", () => setBotState("PAUSED"));

    // Backtest Comparison Button
    document.getElementById("btnRunComparison")?.addEventListener("click", runStrategyComparison);
}

// 10. Bot Management
async function setBotState(state) {
    try {
        await fetch("/api/bot/state", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ state: state })
        });
        fetchBotData();
    } catch (e) {
        console.error(e);
    }
}

async function fetchBotData() {
    try {
        const res = await fetch("/api/bot/status");
        if (!res.ok) return;
        const bot = await res.json();

        const badge = document.getElementById("botBadge");
        const statusText = document.getElementById("botStatusText");
        const display = document.getElementById("botStateDisplay");

        statusText.innerText = `ربات: ${bot.state}`;
        display.innerText = `حالت فعلی: ${bot.state}`;

        // Event logs
        const logBox = document.getElementById("botEventLog");
        if (logBox && bot.events) {
            logBox.innerHTML = bot.events.slice(-20).map(e => `
                <div class="log-line">
                    <span class="log-time">[${new Date(e.timestamp).toLocaleTimeString("fa-IR")}]</span>
                    <span class="log-tag">[${e.event_type}]</span>
                    <span>${e.message}</span>
                </div>
            `).join("");
        }
    } catch (e) {
        console.error(e);
    }
}

// 11. Strategy Comparison Backtest
async function runStrategyComparison() {
    const btn = document.getElementById("btnRunComparison");
    btn.disabled = true;
    btn.innerText = "در حال شبیه‌سازی و ارزیابی...";

    try {
        const res = await fetch("/api/backtest/compare");
        if (!res.ok) return;
        const data = await res.json();

        const tbody = document.querySelector("#comparisonTable tbody");
        if (tbody && data.results) {
            tbody.innerHTML = data.results.map(r => `
                <tr>
                    <td><strong>${r.strategy_id}</strong></td>
                    <td>${r.strategy_name}</td>
                    <td>${r.total_trades}</td>
                    <td><span class="badge ${r.win_rate_pct >= 50 ? 'badge-pd' : 'badge-london'}">${r.win_rate_pct}%</span></td>
                    <td>${r.profit_factor}</td>
                    <td class="${r.expectancy_r >= 0 ? 'text-green' : 'text-red'} font-weight-bold">${r.expectancy_r} R</td>
                    <td>${r.max_drawdown_r} R</td>
                    <td><span class="badge ${r.evidence_status.startsWith('SUFFICIENT') ? 'badge-pd' : 'badge-asia'}">${r.evidence_status}</span></td>
                </tr>
            `).join("");
        }
    } catch (err) {
        console.error(err);
    } finally {
        btn.disabled = false;
        btn.innerText = "اجرای مجدد بکتست و مقایسه جامع 🚀";
    }
}

// 12. Calendar Data
async function fetchCalendarData() {
    try {
        const res = await fetch("/api/calendar");
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.querySelector("#calendarTable tbody");
        if (tbody && data.events) {
            tbody.innerHTML = data.events.map(ev => `
                <tr>
                    <td><strong>${ev.name}</strong></td>
                    <td>${new Date(ev.release_time).toUTCString().slice(17, 22)} UTC</td>
                    <td><span class="badge badge-london">${ev.impact}</span></td>
                    <td><span class="badge ${ev.is_blackout ? 'badge-asia' : 'badge-pd'}">${ev.status}</span></td>
                </tr>
            `).join("");
        }
    } catch (e) {
        console.error(e);
    }
}

// 13. Replay Engine
function toggleReplay() {
    const btn = document.getElementById("btnReplayPlay");
    if (!isReplaying) {
        isReplaying = true;
        btn.innerText = "⏸ توقف (Pause)";
        replayTimer = setInterval(stepReplayNext, 1200);
    } else {
        isReplaying = false;
        btn.innerText = "▶ بازپخش (Replay)";
        clearInterval(replayTimer);
    }
}

function stepReplayNext() {
    if (replayIndex < currentCandles.length) {
        replayIndex++;
        const subset = currentCandles.slice(0, replayIndex);
        candleSeries.setData(subset.map(c => ({
            time: c.time, open: c.open, high: c.high, low: c.low, close: c.close
        })));
    } else {
        toggleReplay();
    }
}

function stepReplayPrev() {
    if (replayIndex > 10) {
        replayIndex--;
        const subset = currentCandles.slice(0, replayIndex);
        candleSeries.setData(subset.map(c => ({
            time: c.time, open: c.open, high: c.high, low: c.low, close: c.close
        })));
    }
}

// 14. WebSocket Live Stream
function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    let ws = null;

    try {
        ws = new WebSocket(wsUrl);
        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === "TICK") {
                document.getElementById("quoteBid").innerText = msg.bid.toFixed(2);
                document.getElementById("quoteAsk").innerText = msg.ask.toFixed(2);
                document.getElementById("quoteSpread").innerText = `$${(msg.ask - msg.bid).toFixed(2)}`;
            } else if (msg.type === "FILL") {
                fetchBrokerData();
            }
        };
        ws.onclose = () => {
            setTimeout(initWebSocket, 3000);
        };
    } catch (e) {
        console.warn("WebSocket fallback to polling mode:", e);
    }
}

// 15. AI Research Center Controller (V3.0)
document.addEventListener("DOMContentLoaded", () => {
    fetchResearchData();
    setInterval(fetchResearchData, 6000);

    const btnHypo = document.getElementById("btnNewHypothesis");
    if (btnHypo) {
        btnHypo.addEventListener("click", () => {
            const modal = document.getElementById("hypothesisModal");
            if (modal) modal.classList.add("show");
        });
    }
});

function closeHypothesisModal() {
    const modal = document.getElementById("hypothesisModal");
    if (modal) modal.classList.remove("show");
}

async function submitNewHypothesis() {
    const title = document.getElementById("hypTitle").value;
    const rationale = document.getElementById("hypRationale").value;
    const target = document.getElementById("hypTarget").value;
    if (!title) {
        alert("لطفاً عنوان فرضیه را وارد کنید.");
        return;
    }
    try {
        const res = await fetch("/api/learning/hypotheses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, rationale, target_metric: target })
        });
        if (res.ok) {
            closeHypothesisModal();
            fetchResearchData();
        }
    } catch (e) {
        console.error("Error creating hypothesis:", e);
    }
}

async function triggerCycle(cycleType) {
    try {
        const res = await fetch(`/api/supervisor/trigger?cycle_type=${cycleType}`, { method: "POST" });
        if (res.ok) {
            fetchResearchData();
            if (cycleType === "NIGHTLY_EVALUATION") {
                loadLatestReport();
            }
        }
    } catch (e) {
        console.error("Error triggering cycle:", e);
    }
}

async function loadLatestReport() {
    try {
        const res = await fetch("/api/reports/latest");
        if (!res.ok) return;
        const data = await res.json();
        const el = document.getElementById("latestReportContent");
        if (el) {
            el.innerText = data.content;
        }
    } catch (e) {
        console.error("Error loading report:", e);
    }
}

async function approveProposal(proposalId) {
    if (!confirm(`آیا اصلاحیه ${proposalId} را به صورت رسمی تایید و اعمال می‌کنید؟`)) return;
    try {
        const res = await fetch(`/api/autofix/proposals/${proposalId}/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_confirmed: true })
        });
        const data = await res.json();
        alert(data.message || "نتیجه ثبت شد.");
        fetchResearchData();
    } catch (e) {
        console.error(e);
    }
}

async function rejectProposal(proposalId) {
    const reason = prompt("دلیل رد اصلاحیه را وارد کنید:") || "رد شده توسط کاربر";
    try {
        await fetch(`/api/autofix/proposals/${proposalId}/reject`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_confirmed: true, reason })
        });
        fetchResearchData();
    } catch (e) {
        console.error(e);
    }
}

async function promoteChallenger(challengerId) {
    if (!confirm(`آیا استراتژی ${challengerId} به عنوان قهرمان (Champion) جدید تایید و جایگزین شود؟`)) return;
    try {
        const res = await fetch("/api/promotion/promote", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ challenger_id: challengerId, user_confirmed: true })
        });
        const data = await res.json();
        alert(data.message || "نتیجه ثبت شد.");
        fetchResearchData();
    } catch (e) {
        console.error(e);
    }
}

async function fetchResearchData() {
    // 1. Supervisor Status & Jobs
    try {
        const resSup = await fetch("/api/supervisor/status");
        if (resSup.ok) {
            const data = await resSup.json();
            if (data.champion) {
                const champEl = document.getElementById("championName");
                if (champEl) champEl.innerText = data.champion.name;
                const statsEl = document.getElementById("championStats");
                if (statsEl) statsEl.innerText = `امید ریاضی: R=${data.champion.expectancy_r.toFixed(2)}`;
            }
            const tbodyJobs = document.querySelector("#supervisorJobsTable tbody");
            if (tbodyJobs && data.recent_jobs) {
                tbodyJobs.innerHTML = data.recent_jobs.map(j => `
                    <tr>
                        <td><strong>${j.job_id}</strong></td>
                        <td>${j.job_type}</td>
                        <td><span class="badge ${j.status === 'COMPLETED' ? 'badge-pd' : 'badge-asia'}">${j.status}</span></td>
                        <td>${j.created_at ? j.created_at.slice(11, 19) : '-'}</td>
                        <td class="text-muted">${j.error_message ? j.error_message : (j.result ? JSON.stringify(j.result).slice(0, 50) : 'موفق')}</td>
                    </tr>
                `).join("");
            }
        }
    } catch (e) {}

    // 2. Regime Monitor
    try {
        const resReg = await fetch("/api/regime/current");
        if (resReg.ok) {
            const reg = await resReg.json();
            const badge = document.getElementById("regimeStatusText");
            if (badge) badge.innerText = `رژیم: ${reg.primary_regime}`;
            const primaryEl = document.getElementById("regimePrimary");
            if (primaryEl) primaryEl.innerText = reg.primary_regime;
            const volEl = document.getElementById("regimeVolRatio");
            if (volEl) volEl.innerText = `${reg.volatility_ratio}x`;
            const slopeEl = document.getElementById("regimeTrendSlope");
            if (slopeEl) slopeEl.innerText = reg.adx_trend_slope;
            const falseEl = document.getElementById("regimeFalseBreak");
            if (falseEl) falseEl.innerText = `${(reg.false_breakout_rate * 100).toFixed(0)}%`;
            const descEl = document.getElementById("regimeDesc");
            if (descEl) descEl.innerText = reg.description;
        }
    } catch (e) {}

    // 3. Strategy Versions (Champion vs Challenger)
    try {
        const resVers = await fetch("/api/promotion/versions");
        if (resVers.ok) {
            const versions = await resVers.json();
            const tbody = document.querySelector("#strategyVersionsTable tbody");
            if (tbody) {
                tbody.innerHTML = versions.map(v => `
                    <tr>
                        <td><strong>${v.version_id}</strong></td>
                        <td>${v.name}</td>
                        <td><span class="${v.is_champion ? 'badge-champion' : 'badge-challenger'}">${v.is_champion ? '👑 CHAMPION' : 'CHALLENGER'}</span></td>
                        <td>${v.total_trades}</td>
                        <td>${v.win_rate.toFixed(1)}%</td>
                        <td class="font-weight-bold ${v.expectancy_r >= 0 ? 'text-green' : 'text-red'}">${v.expectancy_r.toFixed(2)} R</td>
                        <td>${v.max_drawdown_pct.toFixed(1)}%</td>
                        <td>${v.sharpe_ratio.toFixed(2)}</td>
                        <td><span class="badge ${v.p_value_vs_champion <= 0.05 ? 'badge-pd' : 'badge-london'}">p=${v.p_value_vs_champion.toFixed(3)}</span></td>
                        <td>
                            ${v.is_champion ? '<span class="text-muted">نسخه فعال</span>' : `<button class="btn btn-primary btn-sm" onclick="promoteChallenger('${v.version_id}')">ترفیع به قهرمان 👑</button>`}
                        </td>
                    </tr>
                `).join("");
            }
        }
    } catch (e) {}

    // 4. Hypotheses Registry
    try {
        const resHyp = await fetch("/api/learning/hypotheses");
        if (resHyp.ok) {
            const hypotheses = await resHyp.json();
            const tbody = document.querySelector("#hypothesesTable tbody");
            if (tbody) {
                tbody.innerHTML = hypotheses.map(h => `
                    <tr>
                        <td><strong>${h.hypothesis_id}</strong></td>
                        <td>${h.title}</td>
                        <td><span class="badge badge-asia">${h.status}</span></td>
                        <td>${h.target_metric}</td>
                        <td>${h.sample_size}</td>
                    </tr>
                `).join("");
            }
        }
    } catch (e) {}

    // 5. Autopsies
    try {
        const resAut = await fetch("/api/learning/autopsies");
        if (resAut.ok) {
            const autopsies = await resAut.json();
            const tbody = document.querySelector("#autopsiesTable tbody");
            if (tbody && autopsies.length > 0) {
                tbody.innerHTML = autopsies.map(a => `
                    <tr>
                        <td><strong>${a.trade_id}</strong></td>
                        <td>${a.setup_id}</td>
                        <td class="${a.pnl >= 0 ? 'text-green' : 'text-red'} font-weight-bold">${a.pnl >= 0 ? '+' : ''}$${a.pnl.toFixed(2)} (${a.r_multiple}R)</td>
                        <td><span class="badge ${a.verdict.includes('WIN') ? 'badge-pd' : 'badge-london'}">${a.verdict}</span></td>
                        <td>${a.takeaway_persian}</td>
                    </tr>
                `).join("");
            }
        }
    } catch (e) {}

    // 6. Auto-Fix Proposals
    try {
        const resFix = await fetch("/api/autofix/proposals");
        if (resFix.ok) {
            const proposals = await resFix.json();
            const tbody = document.querySelector("#proposalsTable tbody");
            if (tbody && proposals.length > 0) {
                tbody.innerHTML = proposals.map(p => `
                    <tr>
                        <td><strong>${p.proposal_id}</strong></td>
                        <td>${p.title}</td>
                        <td><code>${p.target_file}</code></td>
                        <td><span class="badge-risk-${p.risk_level.toLowerCase()}">${p.risk_level}</span></td>
                        <td><span class="badge ${p.status === 'APPLIED' ? 'badge-pd' : 'badge-asia'}">${p.status}</span></td>
                        <td>${p.requires_human_approval ? 'الزامی ⚠️' : 'خودکار'}</td>
                        <td>
                            ${p.status === 'PROPOSED' ? `
                                <button class="btn btn-success btn-sm" onclick="approveProposal('${p.proposal_id}')">تایید ✅</button>
                                <button class="btn btn-danger btn-sm" onclick="rejectProposal('${p.proposal_id}')">رد ❌</button>
                            ` : `<span class="text-muted">${p.status}</span>`}
                        </td>
                    </tr>
                `).join("");
            } else if (tbody) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">هیچ اصلاحیه بازی در صف انتظار نیست (سیستم سالم است).</td></tr>';
            }
        }
    } catch (e) {}

    // 7. ML Scores
    try {
        const resML = await fetch("/api/ml/scores");
        if (resML.ok) {
            const scores = await resML.json();
            const tbody = document.querySelector("#mlScoresTable tbody");
            if (tbody && scores.length > 0) {
                tbody.innerHTML = scores.map(s => `
                    <tr>
                        <td><strong>${s.score_id}</strong></td>
                        <td>${s.setup_id}</td>
                        <td class="font-weight-bold text-blue">${(s.predicted_win_prob * 100).toFixed(1)}%</td>
                        <td><span class="badge badge-pd">${s.quality_grade}</span></td>
                        <td><span class="badge badge-london">${s.shadow_mode ? 'حالت سایه (Shadow)' : 'فعال'}</span></td>
                    </tr>
                `).join("");
            } else if (tbody) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">امتیازدهی یادگیری ماشین به محض دریافت اولین سیگنال ثبت می‌شود.</td></tr>';
            }
        }
    } catch (e) {}
}
