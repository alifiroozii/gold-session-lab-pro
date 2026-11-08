// Gold Session Lab Pro — Interactive Frontend Controller

let chart = null;
let candleSeries = null;
let currentDirection = "BUY";
let currentTimeframe = "5m";
let currentCandles = [];
let replayIndex = 0;
let isReplaying = false;
let replayTimer = null;
let currentMarketData = null;
let activePriceLines = [];
let sessionRectangles = [];
let liveQuoteLine = null;
let chartHasFittedOnce = false;
let chartRenderedTimeframe = null;
// --- چارت واحد تحلیلی سشن‌ها و سطوح معاملاتی طلا ---
window.switchChartMode = function(mode) {
    const reference = mode !== "local";
    document.getElementById("referenceChartPanel").hidden = !reference;
    document.getElementById("localChartPanel").hidden = reference;
    document.getElementById("btnReferenceChart").setAttribute("aria-pressed", String(reference));
    document.getElementById("btnLocalChart").setAttribute("aria-pressed", String(!reference));
    if (!reference) window.dispatchEvent(new Event("resize"));
};

// --- دریافت و اعمال قیمت زنده تریدینگ‌ویو برای اعداد داشبورد و چارت ---
async function fetchTradingViewQuote() {
    try {
        const res = await fetch("/api/tradingview/quote");
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === "REFERENCE_ONLY" && data.quote) {
            handleTradingViewQuote(data.quote);
        } else {
            const indicator = document.getElementById("tvLivePrice");
            if (indicator) {
                indicator.textContent = "—";
                indicator.title = "منبع مقایسه TradingView در دسترس یا تازه نیست؛ این وضعیت مجوز معامله نیست.";
            }
        }
    } catch (_err) {
        const indicator = document.getElementById("tvLivePrice");
        if (indicator) indicator.textContent = "—";
    }
}

// Scanner quotes are unverified, display-only reference observations.
// Never invent Bid/Ask or spread and NEVER pass scanner values into the paper broker.
function handleTradingViewQuote(quote) {
    const price = Number(quote?.price);
    const reference = document.getElementById("tvLivePrice");
    if (!reference || !Number.isFinite(price) || price <= 0) {
        if (reference) reference.textContent = "نامعتبر / در دسترس نیست";
        return;
    }
    const age = quote.quote_age_seconds;
    if (!Number.isFinite(Number(age)) || Number(age) > 30 || Number(age) < -5) {
        reference.textContent = "قدیمی / غیرقابل اتکا";
        reference.title = "TradingView scanner quote has no verified fresh provider timestamp";
        return;
    }
    reference.textContent = price.toFixed(2) + " · مرجع غیررسمی";
    reference.title = "منبع: " + (quote.source || "SCANNER_UNVERIFIED") +
        " | نماد: " + (quote.ticker || "نامشخص") +
        " | قابل استفاده برای معامله: خیر";
}

// --- تابع جامع تبدیل تاریخ میلادی به تاریخ خورشیدی شمسی (Jalali / Solar Hijri) ---
function toShamsiDateTime(dateInput, includeTime = true) {
    if (!dateInput) return "-";
    try {
        const d = new Date(dateInput);
        if (isNaN(d.getTime())) return String(dateInput);

        const options = {
            calendar: 'persian',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
        };
        if (includeTime) {
            options.hour = '2-digit';
            options.minute = '2-digit';
            options.second = '2-digit';
            options.hour12 = false;
        }
        return new Intl.DateTimeFormat('fa-IR-u-ca-persian', options).format(d);
    } catch (e) {
        return String(dateInput);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initClock();
    initTabs();
    document.getElementById("btnReferenceChart")?.addEventListener("click", () => switchChartMode("reference"));
    document.getElementById("btnLocalChart")?.addEventListener("click", () => switchChartMode("local"));
    initChart();
    initForms();
    fetchMarketData();
    fetchBrokerData();
    fetchCalendarData();
    fetchBotData();
    fetchTradingViewQuote();
    fetchMarketComparison();
    fetchStrategyState();
    fetchSupervisorReport();
    initWebSocket();
    setInterval(fetchBrokerData, 3000);
    setInterval(fetchBotData, 4000);
    setInterval(fetchTradingViewQuote, 3000);
    setInterval(fetchMarketStatus, 5000);
    setInterval(fetchMarketComparison, 5000);
    setInterval(fetchStrategyState, 4000);
    setInterval(fetchSupervisorReport, 8000);
    fetchMarketStatus();
});

// 1. Clock با نمایش تقویم شمسی و ساعت تهران
function initClock() {
    const clockEl = document.getElementById("systemClock");
    if (!clockEl) return;
    setInterval(() => {
        const now = new Date();
        const shamsiStr = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            weekday: 'long',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        }).format(now);
        const utcStr = now.toUTCString().slice(17, 25);
        clockEl.innerText = `تقویم شمسی: ${shamsiStr} (UTC ${utcStr})`;
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
            document.querySelector(".nav-more")?.removeAttribute("open");
            if (targetId === "tab-chart" && chart) {
                window.dispatchEvent(new Event("resize"));
            }
        });
    });
}

// 3. Lightweight Charts Initializer
function initChart() {
    const container = document.getElementById("chartContainer");
    if (!container || typeof LightweightCharts === "undefined") return;

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth || 800,
        height: 560,
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

    chart.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(drawSessionBoxes));
    candleSeries = chart.addCandlestickSeries({
        upColor: "#16A34A",
        downColor: "#DC2626",
        borderVisible: false,
        wickUpColor: "#16A34A",
        wickDownColor: "#DC2626"
    });

    window.addEventListener("resize", () => {
        requestAnimationFrame(drawSessionBoxes);
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
        const res = await fetch(`/api/market?timeframe=${encodeURIComponent(currentTimeframe)}`, {
            cache: "no-store"
        });
        if (!res.ok) throw new Error("Market API HTTP " + res.status);
        const data = await res.json();
        // NEVER silently load the synthetic demo CSV when verified data
        // is missing. An empty, honestly labeled chart is safer.
        renderMarketData(data);
    } catch (err) {
        console.error("Market feed unavailable:", err);
        const empty = document.getElementById("chartEmptyState");
        if (empty) {
            empty.hidden = false;
            const status = empty.querySelector(".chart-empty-message");
            if (status) status.textContent =
                "داده واقعی قابل دریافت نیست. اتصال فید را بررسی کنید؛ هیچ کندل ساختگی جایگزین نخواهد شد.";
        }
    }
}


function renderMarketData(data) {
    if (!data) return;
    const label = document.getElementById("dataSourceLabel");
    const sourceText = data.data_source === "OANDA_HISTORICAL_MID"
        ? "کندل‌های واقعی OANDA (Mid، بسته‌شده) + قیمت لحظه‌ای Bid/Ask"
        : (data.data_source === "DEMO_CSV"
            ? "حالت بازپخش آموزشی — داده ساختگی، غیرقابل معامله"
            : "بدون داده معتبر؛ برای نمایش چارت واقعی فید OANDA را متصل کنید");
    if (label) label.textContent = "چارت: " + sourceText;
    if (data.execution) updateExecutionBadge(data.execution);
    if (!data.candles || data.candles.length === 0) {
        currentMarketData = data;
        currentCandles = [];
        sessionRectangles = [];
        if (candleSeries) candleSeries.setData([]);
        const empty = document.getElementById("chartEmptyState");
        if (empty) empty.hidden = false;
        removeLiveQuoteLine();
        requestAnimationFrame(drawSessionBoxes);
        return;
    }
    const empty = document.getElementById("chartEmptyState");
    if (empty) empty.hidden = true;
    currentMarketData = data;
    sessionRectangles = data.session_boxes || [];
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
    if (!candleSeries) return;
    candleSeries.setData(chartBars);
    // Do not reset the user's zoom/pan every time a polling request arrives.
    if (!chartHasFittedOnce || chartRenderedTimeframe !== currentTimeframe) {
        try {
            const windowBars = {"1m": 450, "5m": 420, "15m": 240, "1h": 130};
            const visibleCount = windowBars[currentTimeframe] || 420;
            if (chartBars.length > visibleCount) {
                chart.timeScale().setVisibleLogicalRange({
                    from: chartBars.length - visibleCount,
                    to: chartBars.length + 8
                });
            } else chart.timeScale().fitContent();
        } catch (_e) { chart.timeScale().fitContent(); }
        chartHasFittedOnce = true;
        chartRenderedTimeframe = currentTimeframe;
    }

    // Update Quote Box
    const lastBar = currentCandles[currentCandles.length - 1];
    const sessionBadge = document.getElementById("currentSessionText");
    if (sessionBadge) {
        const names = {
            "Asia_Reference":"محدوده آسیا", "Tokyo":"توکیو",
            "London":"لندن", "New_York":"نیویورک",
            "London_NY_Overlap":"هم‌پوشانی لندن/نیویورک"
        };
        const sessions = (lastBar.sessions || []).map(x => names[x] || x);
        sessionBadge.textContent = "آخرین کندل: " +
            (sessions.length ? sessions.join(" / ") : "خارج از سشن‌های تعریف‌شده");
    }
    // The provider label and execution status are updated before chart rendering.

    // Update Levels labels
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

    // Render Clean Layers (Levels, Trades, Signals on Demand)
    updateChartLayers();
    requestAnimationFrame(drawSessionBoxes);

    // Update Signals Table
    renderSignalsTable(data.signals || []);

    // Update Metrics
    if (data.metrics) {
        if (document.getElementById("stratWinRate")) document.getElementById("stratWinRate").innerText = data.metrics.win_rate_pct ? `${data.metrics.win_rate_pct}%` : "-";
        if (document.getElementById("stratPF")) document.getElementById("stratPF").innerText = `فاکتور سود: ${data.metrics.profit_factor ?? "-"}`;
        if (document.getElementById("stratExpectancy")) document.getElementById("stratExpectancy").innerText = `${data.metrics.expectancy_r ?? 0.0} R`;
        if (document.getElementById("stratMaxDD")) document.getElementById("stratMaxDD").innerText = `حداکثر افت: ${data.metrics.max_drawdown_r ?? 0.0} R`;
        document.getElementById("totalTradesCount").innerText = `تعداد معاملات: ${data.metrics.total_trades ?? 0}`;
    }
}

function updateChartLayers() {
    if (!currentMarketData || !candleSeries) return;

    const showSignals = document.getElementById("toggleSignals")?.checked || false;
    const showTrades = document.getElementById("toggleTrades")?.checked || false;
    const showLevels = document.getElementById("toggleLevels")?.checked || false;
    requestAnimationFrame(drawSessionBoxes);

    // 1. Manage Horizontal Price Lines (Levels)
    activePriceLines.forEach(line => {
        try { candleSeries.removePriceLine(line); } catch (e) {}
    });
    activePriceLines = [];

    const stats = currentMarketData.session_stats || {};
    if (showLevels) {
        if (stats.asia && stats.asia.high) {
            activePriceLines.push(candleSeries.createPriceLine({
                price: stats.asia.high,
                color: "#F59E0B",
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: "سقف آسیا (Asia High)",
            }));
        }
        if (stats.asia && stats.asia.low) {
            activePriceLines.push(candleSeries.createPriceLine({
                price: stats.asia.low,
                color: "#F59E0B",
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: "کف آسیا (Asia Low)",
            }));
        }
        if (stats.pd && stats.pd.high) {
            activePriceLines.push(candleSeries.createPriceLine({
                price: stats.pd.high,
                color: "#2563EB",
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: "PDH",
            }));
        }
        if (stats.pd && stats.pd.low) {
            activePriceLines.push(candleSeries.createPriceLine({
                price: stats.pd.low,
                color: "#2563EB",
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: "PDL",
            }));
        }
    }

    // 2. Manage Markers
    const markers = [];

    // Executed Paper Trades (High priority, clean and minimal)
    if (showTrades && currentMarketData.trades) {
        currentMarketData.trades.forEach(t => {
            const isWin = t.outcome === "WIN";
            markers.push({
                time: Math.floor(new Date(t.entry_time).getTime() / 1000),
                position: isWin ? "aboveBar" : "belowBar",
                color: isWin ? "#16A34A" : "#DC2626",
                shape: isWin ? "arrowDown" : "arrowUp",
                text: isWin ? `برد +${t.realized_r}R` : "ضرر -1R"
            });
        });
    }

    // Setup Signals (Only enabled when toggle is explicitly checked; max 20 recent signals with sleek short code)
    if (showSignals && currentMarketData.signals) {
        const recentSignals = currentMarketData.signals.slice(-20);
        recentSignals.forEach(s => {
            const shortCode = s.setup_id.split('_')[0] || "SIG";
            const isBuy = s.direction === "BUY";
            markers.push({
                time: s.time,
                position: isBuy ? "belowBar" : "aboveBar",
                color: isBuy ? "#3B82F6" : "#EAB308",
                shape: isBuy ? "arrowUp" : "arrowDown",
                text: `${shortCode} ${isBuy ? 'خرید' : 'فروش'}`
            });
        });
    }

    markers.sort((a, b) => a.time - b.time);
    candleSeries.setMarkers(markers);
}

// Draw exact price/time-bounded session boxes on the *real* candlestick chart.
// Uses chart coordinates: not arbitrary HTML positioning.
function drawSessionBoxes() {
    const overlay = document.getElementById("sessionOverlay");
    if (!overlay || !chart || !candleSeries) return;
    overlay.replaceChildren();
    if (!document.getElementById("toggleSessions")?.checked) return;
    const bars = currentCandles || [];
    if (!bars.length) return;
    const palette = {
        asia: ["#2c7be5", "rgba(44,123,229,.075)", "آسیا"],
        london: ["#18a076", "rgba(24,160,118,.075)", "لندن"],
        new_york: ["#db8b27", "rgba(219,139,39,.075)", "نیویورک"],
        overlap: ["#a06ad4", "rgba(160,106,212,.075)", "همپوشانی"],
    };
    for (const box of sessionRectangles) {
        const first = bars.find(c => c.time >= box.start && c.time <= box.end);
        const last = bars.findLast ? bars.findLast(c => c.time >= box.start && c.time <= box.end)
            : [...bars].reverse().find(c => c.time >= box.start && c.time <= box.end);
        if (!first || !last) continue;
        const a = chart.timeScale().timeToCoordinate(first.time);
        const b = chart.timeScale().timeToCoordinate(last.time);
        const hi = candleSeries.priceToCoordinate(box.high);
        const lo = candleSeries.priceToCoordinate(box.low);
        if ([a,b,hi,lo].some(v => v === null || !Number.isFinite(v))) continue;
        const left = Math.min(a,b) - 3;
        const top = Math.min(hi,lo);
        const width = Math.abs(b-a) + 6;
        const height = Math.abs(lo-hi);
        if (width < 5 || height < 3) continue;
        const [color,background,name] = palette[box.session] || palette.asia;
        const rect = document.createElement("div");
        rect.className = "session-box session-box-" + box.session;
        rect.style.left = left + "px";
        rect.style.top = top + "px";
        rect.style.width = width + "px";
        rect.style.height = height + "px";
        rect.style.borderColor = color;
        rect.style.background = background;
        rect.style.opacity = box.completed ? "1" : ".65";
        const label = document.createElement("span");
        label.className = "session-box-label";
        label.style.color = color;
        label.textContent = name + " · " + box.date +
            (box.completed ? "" : " · در حال شکل‌گیری");
        rect.title = name + " " + box.date +
            " | High: " + Number(box.high).toFixed(2) +
            " | Low: " + Number(box.low).toFixed(2) +
            (box.completed ? " | کامل" : " | ناقص");
        if (width > 66) rect.appendChild(label);
        overlay.appendChild(rect);
    }
}

function removeLiveQuoteLine() {
    if (liveQuoteLine && candleSeries) {
        try { candleSeries.removePriceLine(liveQuoteLine); } catch (_err) {}
    }
    liveQuoteLine = null;
}

function updateLiveQuoteLine(bid, ask, title = "قیمت لحظه‌ای (نقل‌قول)") {
    if (!candleSeries) return;
    // A real broker quote line must not be superimposed on DEMO candles.
    if (currentMarketData?.data_source !== "OANDA_HISTORICAL_MID") {
        removeLiveQuoteLine();
        return;
    }
    if (!Number.isFinite(bid) || !Number.isFinite(ask) || ask <= bid) return;
    const mid = (bid + ask) / 2;
    if (!liveQuoteLine) {
        liveQuoteLine = candleSeries.createPriceLine({
            price: mid, color: "#16A34A", lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dotted,
            axisLabelVisible: true, title: title,
        });
    } else {
        liveQuoteLine.applyOptions({price: mid, title: title});
    }
}

function updateExecutionBadge(execution) {
    const gate = document.getElementById("marketGateText");
    if (gate) gate.textContent = execution.paper_orders_allowed
        ? "قیمت زنده تأیید شده · سفارش دستی مجازی مجاز"
        : "معامله جدید مسدود · " + (execution.reason || "بدون فید معتبر");
    const when = document.getElementById("lastQuoteTime");
    if (when) when.textContent = execution.quote_time
        ? "آخرین قیمت معتبر: " + toShamsiDateTime(execution.quote_time)
        : "آخرین قیمت معتبر: —";
    const bid = document.getElementById("quoteBid");
    const ask = document.getElementById("quoteAsk");
    const spread = document.getElementById("quoteSpread");
    if (bid) bid.textContent = execution.bid_display || (execution.bid == null ? "—" : String(execution.bid));
    if (ask) ask.textContent = execution.ask_display || (execution.ask == null ? "—" : String(execution.ask));
    if (spread) spread.textContent = execution.bid == null || execution.ask == null
        ? "—" : "$" + (execution.spread_display || String(execution.ask - execution.bid));
    const feed = document.getElementById("feedStatusText");
    if (feed) feed.textContent = execution.paper_orders_allowed ? "قیمت تأیید شده" : "فید زنده نامعتبر / بسته";
    const manual = document.getElementById("btnSubmitOrder");
    if (manual) manual.disabled = !execution.paper_orders_allowed;
    const auto = document.getElementById("btnBotAuto");
    // Auto trading is blocked until the next-bar causal bot logic is verified.
    if (auto) auto.disabled = true;
    if (!execution.paper_orders_allowed) removeLiveQuoteLine();
}
async function fetchMarketStatus() {
    try {
        const res = await fetch("/api/market/status", {cache:"no-store"});
        if (res.ok) updateExecutionBadge(await res.json());
    } catch (_err) {
        updateExecutionBadge({paper_orders_allowed:false,reason:"دسترسی به سرور قطع است"});
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
            <td>${toShamsiDateTime(new Date(s.time * 1000))}</td>
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
        if (document.getElementById("sideAccBalance")) {
            document.getElementById("sideAccBalance").innerText = `$${acc.balance.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
        }
        if (document.getElementById("sideAccEquity")) {
            document.getElementById("sideAccEquity").innerText = `$${acc.equity.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
        }
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
            <td>${toShamsiDateTime(o.created_time)}</td>
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
            <td>${toShamsiDateTime(l.timestamp)}</td>
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
        if (!confirm("آیا از ریست کامل حساب مجازی و تنظیم موجودی روی $۱,۰۰۰ اطمینان دارید؟")) return;
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

    // Risk settings: submit actual API request rather than leaving a dead UI button.
    document.getElementById("btnSaveRisk")?.addEventListener("click", async () => {
        const values = {
            risk_per_trade_pct: Number(document.getElementById("riskPerTrade")?.value),
            max_daily_loss_pct: Number(document.getElementById("maxDailyLoss")?.value),
            max_open_positions: Number(document.getElementById("maxPositions")?.value),
            max_daily_trades: Number(document.getElementById("maxDailyTrades")?.value),
            max_spread_pips: Number(document.getElementById("maxSpread")?.value)
        };
        const button = document.getElementById("btnSaveRisk");
        button.disabled = true;
        try {
            const response = await fetch("/api/bot/risk", {
                method:"POST", headers:{"Content-Type":"application/json"},
                body:JSON.stringify(values)
            });
            if (!response.ok) {
                const failure = await response.json();
                throw new Error(typeof failure.detail === "string"
                    ? failure.detail : "مقادیر ریسک نامعتبر یا خارج از سقف ایمنی‌اند.");
            }
            alert("تنظیمات مدیریت ریسک مجازی ذخیره شد.");
            await fetchBotData();
        } catch(error) {
            alert("ذخیره ناموفق: " + error.message);
        } finally { button.disabled = false; }
    });

    // Chart Layer Toggles (Declutter)
    document.getElementById("toggleSessions")?.addEventListener("change", updateChartLayers);
    document.getElementById("toggleSignals")?.addEventListener("change", updateChartLayers);
    document.getElementById("toggleTrades")?.addEventListener("change", updateChartLayers);
    document.getElementById("toggleLevels")?.addEventListener("change", updateChartLayers);
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
                    <span class="log-time">[${toShamsiDateTime(e.timestamp)}]</span>
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
                    <td>${toShamsiDateTime(ev.release_time)}</td>
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
        requestAnimationFrame(drawSessionBoxes);
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
        requestAnimationFrame(drawSessionBoxes);
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
            if (msg.type === "TICK" && msg.verified === true) {
                // A stream tick provides quote information, not authorization
                // to trade. /api/market/status remains the sole execution gate.
                const bid = Number(msg.bid);
                const ask = Number(msg.ask);
                if (Number.isFinite(bid) && Number.isFinite(ask) && ask > bid) {
                    const bidEl = document.getElementById("quoteBid");
                    const askEl = document.getElementById("quoteAsk");
                    const spreadEl = document.getElementById("quoteSpread");
                    const when = document.getElementById("lastQuoteTime");
                    if (bidEl) bidEl.textContent = msg.bid_display || String(msg.bid);
                    if (askEl) askEl.textContent = msg.ask_display || String(msg.ask);
                    if (spreadEl) spreadEl.textContent = "$" + (ask - bid).toFixed(3);
                    if (when) when.textContent = "زمان مظنه: " + toShamsiDateTime(msg.timestamp);
                    updateLiveQuoteLine(bid, ask);
                }
            } else if (msg.type === "TRADINGVIEW_TICK" && msg.quote) {
                handleTradingViewQuote(msg.quote);
            } else if (msg.type === "MARKET_STATUS") {
                updateExecutionBadge({
                    paper_orders_allowed: false,
                    reason: msg.status || "LIVE_STREAM_DISCONNECTED",
                });
            } else if (msg.type === "CANDLES_UPDATED") {
                if (!isReplaying) fetchMarketData();
            } else if (msg.type === "AGENT_OBSERVATIONS") {
                fetchAntigravityActivity();
                fetchAgentAdvice();
            } else if (msg.type === "FILL") {
                fetchBrokerData();
            }
        };
        ws.onclose = () => {
            updateExecutionBadge({
                paper_orders_allowed: false, reason: "ارتباط لحظه‌ای با سرور قطع شد"
            });
            setTimeout(initWebSocket, 3000);
        };
    } catch (e) {
        console.warn("WebSocket fallback to polling mode:", e);
    }
}

// 15. AI Research Center Controller (V3.0)
document.addEventListener("DOMContentLoaded", () => {
    fetchResearchData();
    fetchAntigravityActivity();
    fetchAgentAdvice();
    setInterval(fetchResearchData, 6000);
    setInterval(fetchAntigravityActivity, 10000);
    setInterval(fetchAgentAdvice, 15000);

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
                if (statsEl) statsEl.innerText = data.champion.trades > 0 ? `آمار ثبت‌شده (تأییدنشده): R=${data.champion.expectancy_r.toFixed(2)}` : "بدون بک‌تست معتبر";
            }
            const tbodyJobs = document.querySelector("#supervisorJobsTable tbody");
            if (tbodyJobs && data.recent_jobs) {
                tbodyJobs.innerHTML = data.recent_jobs.map(j => `
                    <tr>
                        <td><strong>${j.job_id}</strong></td>
                        <td>${j.job_type}</td>
                        <td><span class="badge ${j.status === 'COMPLETED' ? 'badge-pd' : 'badge-asia'}">${j.status}</span></td>
                        <td>${toShamsiDateTime(j.created_at)}</td>
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

    // 8. Shadow Mode Proposals
    try {
        const resShadow = await fetch("/api/strategy/shadow-proposals");
        if (resShadow.ok) {
            const proposals = await resShadow.json();
            const tbody = document.querySelector("#shadowProposalsTable tbody");
            if (tbody && proposals.length > 0) {
                tbody.innerHTML = proposals.map(p => {
                    const isEligible = p.status.includes("ELIGIBLE");
                    const statusClass = isEligible ? "badge-pd" : "badge-risk-medium";
                    const statusText = isEligible ? "واجد شرایط (سایه)" : (
                        p.status === "REJECTED_SPREAD" ? "رد اسپرد" :
                        p.status === "REJECTED_NEWS" ? "رد رویداد کلان" :
                        p.status === "REJECTED_RISK" ? "رد ریسک / نسبت R" : p.status
                    );
                    const dirText = p.direction === "BUY" ? "خرید" : "فروش";
                    const dirClass = p.direction === "BUY" ? "text-green" : "text-red";
                    const spreadText = p.spread != null ? `$${p.spread.toFixed(2)}` : "—";
                    return `
                        <tr>
                            <td><code>${safeText(p.proposal_id)}</code></td>
                            <td>${toShamsiDateTime(p.timestamp)}</td>
                            <td><strong>${safeText(p.setup_name)}</strong></td>
                            <td class="${dirClass}"><strong>${dirText}</strong></td>
                            <td>${safeText(p.target_level)} (${formatGoldPrice(p.target_price)})</td>
                            <td><strong>${formatGoldPrice(p.entry_price)}</strong></td>
                            <td>${formatGoldPrice(p.sl_price)} / ${formatGoldPrice(p.tp_price)}</td>
                            <td>${spreadText}</td>
                            <td><span class="badge ${statusClass}">${statusText}</span></td>
                            <td>${safeText(p.rejection_reason)}</td>
                        </tr>
                    `;
                }).join("");
            } else if (tbody) {
                tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">هنوز پیشنهادی در حالت سایه ارزیابی نشده است. با بارگذاری کندل‌ها ارزیابی برخط آغاز می‌شود.</td></tr>';
            }
        }
    } catch (_e) {}

    // 9. Strategy Validation Report (OOS Walk-Forward)
    try {
        const resVal = await fetch("/api/strategy/validation-report");
        if (resVal.ok) {
            const rep = await resVal.json();
            const verdictEl = document.getElementById("valVerdict");
            const provEl = document.getElementById("valProvenance");
            const wrEl = document.getElementById("valWinRate");
            const pfEl = document.getElementById("valProfitFactor");
            const expEl = document.getElementById("valExpectancy");
            const paEl = document.getElementById("valPaperAuto");
            const sumEl = document.getElementById("valSummaryDesc");

            if (verdictEl) {
                verdictEl.textContent = rep.statistical_verdict || rep.outcome || "در انتظار ارزیابی";
                verdictEl.className = rep.statistical_verdict === "FAIL" ? "text-red" : "text-blue";
            }
            if (provEl) {
                provEl.textContent = rep.data_provenance_verified ? "تأییدشده (لایسنس OANDA)" : "تأییدنشده (فیکسچر دمو)";
                provEl.className = rep.data_provenance_verified ? "text-green" : "text-red";
            }
            const oos = rep.out_of_sample_metrics || {};
            if (wrEl) wrEl.textContent = oos.win_rate_pct != null ? `${oos.win_rate_pct}%` : "—";
            if (pfEl) pfEl.textContent = oos.profit_factor != null ? `${oos.profit_factor}` : "—";
            if (expEl) expEl.textContent = oos.expectancy_r != null ? `${oos.expectancy_r} R` : "—";
            if (paEl) {
                paEl.textContent = rep.authorizes_paper_auto ? "مجاز" : "غیرمجاز ❌";
                paEl.className = rep.authorizes_paper_auto ? "badge-pd" : "badge-risk-high";
            }
            if (sumEl) {
                sumEl.textContent = rep.persian_summary || rep.limitations || "گزارش اعتبارسنجی بارگذاری شد.";
            }
        }
    } catch (_e) {}
}

// Verified Antigravity activity. No fabricated success messages.
function safeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    }[ch]));
}
async function fetchAntigravityActivity() {
    try {
        const res = await fetch("/api/agent/status", {cache:"no-store"});
        if (!res.ok) return;
        const data = await res.json();
        const connected = data.agent_status === "RECENT_ACTIVITY";
        const badge = document.getElementById("agentConnectionStatus");
        if (badge) badge.textContent = connected
            ? "فعالیت اخیر ثبت شد · " + toShamsiDateTime(data.agent_last_activity)
            : "Antigravity متصل نیست / فعالیت تازه‌ای ثبت نشده";
        const pairs = [
            ["agentOpenIncidents", data.open_incidents],
            ["agentHypotheses", data.hypotheses_under_review],
            ["agentProposals", data.pending_patch_proposals],
            ["agentVerifiedFixes", data.verified_fixes],
        ];
        for (const [id,val] of pairs) {
            const element = document.getElementById(id);
            if (element) element.textContent = String(val ?? "—");
        }
        const log = document.getElementById("agentActivityTimeline");
        if (!log) return;
        const events = data.events || [];
        log.innerHTML = events.length ? events.slice(0, 20).map(e => `
            <div class="agent-event">
                <span class="agent-event-time">${safeText(toShamsiDateTime(e.timestamp))}</span>
                <strong>${safeText(e.phase)}</strong>
                <span>${safeText(e.subject)}</span>
                <small>${safeText(e.actor)} · ${safeText(e.details)}</small>
                ${e.evidence ? `<code>${safeText(e.evidence)}</code>` : ""}
                ${e.verified ? "<em>مدرک ثبت‌شده ✓</em>" : "<em>هنوز تأیید نشده</em>"}
            </div>`).join("")
            : "هیچ فعالیت واقعی Antigravity ثبت نشده است؛ فقط پس از اجرای چرخه و ثبت شواهد نمایش داده می‌شود.";
    } catch(_err) {
        const badge = document.getElementById("agentConnectionStatus");
        if (badge) badge.textContent = "خطا در خواندن وضعیت Agent";
    }
}

async function fetchAgentAdvice() {
    const el = document.getElementById("agentNextTimeAdvice");
    if (!el) return;
    try {
        const resp = await fetch("/api/agent/advice?limit=8", {cache:"no-store"});
        if (!resp.ok) return;
        const data = await resp.json();
        const safetyItems = data.safety_lessons || data.items || [];
        const tradeItems = data.trade_guidance || [];
        let html = "";
        if (safetyItems.length > 0) {
            html += `<h5 style="margin: 8px 0 4px; color: var(--gold-primary);">قوانین بازدارنده و سدهای ایمنی:</h5>` + safetyItems.map(item => `
                <div class="agent-event">
                    <span class="agent-event-time">${safeText(toShamsiDateTime(item.timestamp))}</span>
                    <strong>${safeText(item.reason)}</strong>
                    <span>${safeText(item.guidance)}</span>
                    <small>سد ایمنی قطعی؛ جلوگیری از معامله نامعتبر</small>
                </div>`).join("");
        }
        if (tradeItems.length > 0) {
            html += `<h5 style="margin: 12px 0 4px; color: var(--blue-accent);">درس‌های استخراج‌شده از کالبدشکافی معاملات:</h5>` + tradeItems.map(item => `
                <div class="agent-event">
                    <span class="agent-event-time">${safeText(toShamsiDateTime(item.created_at))}</span>
                    <strong>${safeText(item.setup_id)} (${safeText(item.side)}) — ${item.pnl >= 0 ? '<span class="text-green">سود +' + item.pnl + '$</span>' : '<span class="text-red">زیان ' + item.pnl + '$</span>'} [${safeText(item.failure_category)}]</strong>
                    <div style="font-size: 12px; margin-top: 3px;"><strong>علت ریشه‌ای:</strong> ${safeText(item.what_went_wrong)}</div>
                    <div style="font-size: 12px; color: #ffb74d;"><strong>چه کاری تکرار نشود:</strong> ${safeText(item.what_not_to_repeat)}</div>
                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">چک‌لیست: ${safeText(item.pre_trade_checklist)} | قانون: ${safeText(item.gating_rule)} (${safeText(item.confidence)})</div>
                </div>`).join("");
        }
        el.innerHTML = html || "هنوز هشدار ایمنی یا کالبدشکافی معامله‌ای ثبت نشده است.";
    } catch (_err) {
        el.textContent = "دریافت دفترچهٔ ایمنی ناموفق بود.";
    }
}

window.emergencyStop = async function() {
    if (!confirm("آیا از فعال‌سازی توقف اضطراری (Emergency Stop) اطمینان دارید؟ کلیه معاملات خودکار مسدود خواهند شد.")) return;
    try {
        const resp = await fetch("/api/bot/emergency-stop", { method: "POST" });
        const res = await resp.json();
        alert(res.message);
        fetchBotData();
    } catch (e) {
        console.error(e);
    }
};

window.resumeBot = async function() {
    if (!confirm("آیا مایلید ربات را از حالت توقف خارج و آماده‌باش قرار دهید؟")) return;
    try {
        const resp = await fetch("/api/bot/resume", { method: "POST" });
        const res = await resp.json();
        alert(res.message);
        fetchBotData();
    } catch (e) {
        console.error(e);
    }
};

// 16. Institutional Grids & Health Monitors Initializer
document.addEventListener("DOMContentLoaded", () => {
    renderStrategiesGrid();
    renderHealthGrid();
    renderSensitivityMatrix();
});

function renderStrategiesGrid() {
    const grid = document.getElementById("strategiesGrid");
    if (!grid) return;
    const strategies = [
        { id: "S1", name: "S1 — Asia Range Breakout", desc: "شناسایی شکست بازه آسیا و ورود با حد ضرر لبه مقابل", tf: "5m", r: "2.0R", active: true },
        { id: "S2", name: "S2 — Sweep + Reclaim + BOS + Retest", desc: "جاروب نقدینگی، بازیابی ساختار، شکست روند و پولبک تاییدیه", tf: "5m", r: "2.5R", active: true },
        { id: "S3", name: "S3 — Liquidity Sweep + CHoCH", desc: "شکار نقدینگی سطوح کلیدی همراه با تغییر ماهیت بازار (CHoCH)", tf: "5m", r: "2.0R", active: true },
        { id: "S4", name: "S4 — Fair Value Gap Mitigation", desc: "پر کردن عدم تعادل قیمت (FVG سه کندلی) و بازگشت مومنتوم", tf: "5m", r: "1.8R", active: true },
        { id: "S5", name: "S5 — Order Block Proxy Retest", desc: "تست مجدد آخرین کندل خلاف روند قبل از شکست پرشتاب ساختار", tf: "5m", r: "2.2R", active: true },
        { id: "S6", name: "S6 — Candlestick Wick Rejection", desc: "تله سایه‌های بلند قیمت (Wick Ratio > 40%) و پس‌زدگی سریع", tf: "5m", r: "1.5R", active: true },
        { id: "S7", name: "S7 — Trend Continuation Pullback", desc: "ورود در راستای روند سشن جاری با پولبک به میانگین متحرک و FVG", tf: "5m", r: "2.0R", active: true },
        { id: "S8", name: "S8 — Combined Structural Model", desc: "ترکیب چندگانه هم‌پوشانی FVG، بلاک سفارش و شکار نقدینگی سشن", tf: "5m", r: "3.0R", active: true }
    ];

    grid.innerHTML = strategies.map(s => `
        <div class="strategy-card">
            <div class="strat-header">
                <span class="strat-title">${s.name}</span>
                <span class="badge ${s.active ? 'badge-pd' : 'badge-asia'}">${s.active ? 'فعال در پایپلاین' : 'غیرفعال'}</span>
            </div>
            <p class="text-muted" style="font-size: 12px; margin-bottom: 8px;">${s.desc}</p>
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary);">
                <span>تایم‌فریم: <strong>${s.tf}</strong></span>
                <span>تارگت هدف: <strong class="text-gold">${s.r}</strong></span>
            </div>
        </div>
    `).join("");
}

function renderHealthGrid() {
    const grid = document.getElementById("healthGrid");
    if (!grid) return;
    const cards = [
        { title: "ترازنامه دفتر کل", val: "نیازمند ممیزی فعال", sub: "نتیجه از حساب و پایگاه داده باید بررسی شود؛ تأیید نمایشی ممنوع.", ok: false },
        { title: "فید زنده قیمت طلا", val: "در انتظار تأیید فید واقعی", sub: "دمو و کندل تاریخی، قیمت اجرایی نیستند.", ok: false },
        { title: "ناظر مستقل ریسک (Risk Guardian)", val: "محافظت سخت‌گیرانه (Active)", sub: "سقف افت روزانه ۲٪ | سقف ریسک هر معامله ۰.۵٪", ok: true },
        { title: "سرپرست پژوهش چندروزه", val: "زمان‌بندی فعال تأیید نشده", sub: "صف محلی وجود دارد؛ اتصال عامل جداگانه باید فعال شود.", ok: false },
        { title: "پایپلاین اصلاح کد", val: "پیشنهاد و بازبینی؛ بدون اعمال خودکار", sub: "بدون Git diff و نتیجه آزمون معتبر، کد اصلی تغییر نمی‌کند.", ok: false },
        { title: "مدل یادگیری ماشین", val: "حالت پژوهشی، اثبات‌نشده", sub: "نمره تا زمان آزمون کالیبراسیون احتمال برد نیست.", ok: false }
    ];

    grid.innerHTML = cards.map(c => `
        <div class="stat-card">
            <div class="stat-title">${c.title}</div>
            <div class="stat-value ${c.ok ? 'text-green' : 'text-red'}" style="font-size: 16px;">${c.val}</div>
            <div class="stat-sub">${c.sub}</div>
        </div>
    `).join("");
}

function renderSensitivityMatrix() {
    const container = document.getElementById("sensitivityContainer");
    if (!container) return;
    container.innerHTML = `
        <div class="text-muted" style="padding: 20px; text-align:center;">
            هیچ آزمون حساسیت پارامترها با داده واقعی و نتایج خارج از نمونه تأیید نشده است.
            اعداد قبلی صرفاً نمایشی بودند و حذف شدند.
        </div>`;
}


// ========================================================
// 16. Layer C Market Comparison & Causal State Machine API
// ========================================================

async function fetchMarketComparison() {
    const tableBody = document.querySelector("#marketComparisonTable tbody");
    if (!tableBody) return;
    try {
        const res = await fetch("/api/market/comparison", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        if (data && data.layers && data.layers.length > 0) {
            tableBody.innerHTML = data.layers.map(l => `
                <tr>
                    <td><strong>${safeText(l.source_layer)}</strong></td>
                    <td><code>${safeText(l.symbol)}</code></td>
                    <td>${safeText(l.provider_name)}</td>
                    <td>${safeText(l.data_type)}</td>
                    <td>${l.last_quote_time ? safeText(toShamsiDateTime(l.last_quote_time)) : "—"}</td>
                    <td class="text-green">${l.bid !== null ? formatGoldPrice(l.bid) : "—"}</td>
                    <td class="text-red">${l.ask !== null ? formatGoldPrice(l.ask) : "—"}</td>
                    <td>${l.mid !== null ? formatGoldPrice(l.mid) : "—"}</td>
                    <td>${l.spread !== null ? `$${l.spread.toFixed(2)}` : "—"}</td>
                    <td><small>${safeText(l.latency_estimate)}</small></td>
                    <td><span class="badge ${l.is_executable ? 'badge-pd' : 'badge-asia'}">${safeText(l.quote_validity)}</span></td>
                    <td>${l.is_executable ? '<span class="text-green">✓ مجاز</span>' : '<span class="text-red">✗ غیرمجاز</span>'}</td>
                    <td><small class="text-muted">${safeText(l.notes)}</small></td>
                </tr>
            `).join("");
        }

        const deltaAmountEl = document.getElementById("priceDeltaAmount");
        const deltaNoteEl = document.getElementById("priceDeltaExplanation");
        if (deltaAmountEl && data.price_delta) {
            if (data.price_delta.difference_usd !== null && data.price_delta.difference_usd !== undefined) {
                const diff = data.price_delta.difference_usd;
                deltaAmountEl.textContent = `اختلاف قیمت: ${diff > 0 ? '+' : ''}${diff.toFixed(2)} دلار`;
                deltaAmountEl.className = `badge ${Math.abs(diff) > 1.0 ? 'badge-london' : 'badge-info'}`;
            } else {
                deltaAmountEl.textContent = "اختلاف: در انتظار داده همزمان";
            }
        }
        if (deltaNoteEl && data.price_delta && data.price_delta.note) {
            deltaNoteEl.textContent = data.price_delta.note;
        }
    } catch (_err) {
        console.warn("Comparison fetch failed:", _err);
    }
}

async function fetchStrategyState() {
    const badgeEl = document.getElementById("stateMachineBadge");
    const lastSigEl = document.getElementById("sideLastSignal");
    if (!badgeEl && !lastSigEl) return;
    try {
        const res = await fetch("/api/strategy/state", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        const stateNames = {
            "WAITING_FOR_SESSION": "در انتظار سشن",
            "BUILDING_RANGE": "تشکیل محدوده آسیا",
            "RANGE_FINALIZED": "سطوح آسیا تثبیت شد",
            "SWEEP_DETECTED": "نفوذ نقدینگی (Sweep)",
            "RECLAIM_CONFIRMED": "تأیید بازپس‌گیری (Reclaim)",
            "STRUCTURE_CONFIRMED": "شکست ساختار (BOS)",
            "RETEST_CONFIRMED": "تأیید پولبک (Retest)",
            "ENTRY_ELIGIBLE": "واجد شرایط ورود (سایه)",
            "PAPER_ORDER": "سفارش ارسال شد",
            "POSITION_MANAGEMENT": "مدیریت موقعیت باز",
            "CLOSED": "پایان چرخه ستاپ"
        };
        const stateText = stateNames[data.current_state] || data.current_state || "در انتظار سشن";
        if (badgeEl) {
            badgeEl.textContent = `[سایه] ${stateText}`;
            badgeEl.title = `حالت سایه فعال (کندل‌های پردازش شده: ${data.processed_candles_count || 0}). اجرای زنده غیرفعال است.`;
        }
        if (lastSigEl) {
            if (data.active_setup) {
                const s = data.active_setup;
                const dir = s.direction === "BUY" ? "خرید" : "فروش";
                lastSigEl.innerHTML = `<strong>${dir}</strong> روی ${safeText(s.target_level_name || '')} (${formatGoldPrice(s.target_level_val || 0)})`;
                lastSigEl.className = s.direction === "BUY" ? "text-green" : "text-red";
            } else if (data.recent_proposals && data.recent_proposals.length > 0) {
                const p = data.recent_proposals[0];
                const dir = p.direction === "BUY" ? "خرید" : "فروش";
                lastSigEl.innerHTML = `<span class="badge ${p.status.includes('ELIGIBLE') ? 'badge-pd' : 'badge-asia'}">${dir} ${safeText(p.setup_name)}</span>`;
                lastSigEl.className = p.status.includes('ELIGIBLE') ? 'text-green' : 'text-muted';
            } else {
                lastSigEl.textContent = "در انتظار ستاپ سشن";
                lastSigEl.className = "text-muted";
            }
        }
    } catch (_err) {
        console.warn("Strategy state fetch failed:", _err);
    }
}

async function fetchSupervisorReport() {
    try {
        const res = await fetch("/api/agent/supervisor-report", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();

        const setTxt = (id, val) => {
            const el = document.getElementById(id);
            if (el && val !== undefined && val !== null) el.textContent = String(val);
        };

        if (data.last_inspection) {
            setTxt("auditLastInspection", toShamsiDateTime(data.last_inspection));
        }
        setTxt("auditDiscoveredIssue", data.discovered_issue);
        setTxt("auditProbableCause", data.probable_cause);
        setTxt("auditReproTest", data.reproduction_test);
        setTxt("auditProposedPatch", data.proposed_patch);
        setTxt("auditTestOutcome", data.test_outcome);
        setTxt("auditVerificationStatus", data.verification_status);
        setTxt("auditGitRef", data.inspected_git_ref);
        setTxt("auditStrategyResult", data.strategy_audit_result);

        if (data.open_incidents_count !== undefined) setTxt("agentOpenIncidents", data.open_incidents_count);
        if (data.hypotheses_count !== undefined) setTxt("agentHypotheses", data.hypotheses_count);
        if (data.pending_proposals_count !== undefined) setTxt("agentProposals", data.pending_proposals_count);
        if (data.verified_fixes_count !== undefined) setTxt("agentVerifiedFixes", data.verified_fixes_count);
    } catch (_err) {
        console.warn("Supervisor report fetch failed:", _err);
    }
}
