#!/usr/bin/env python3
"""
Gold Session Lab Pro v3.6 - Pro Split-Screen Light Dashboard
Side-by-Side Cockpit & Dedicated Live Log Stream.
100% Real-Time Synchronized with MT5 Demo Engine (XAUUSD_o, M5).
"""

import os
import sys
import json
import csv
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = 8089
MT5_FILES_DIR = "/Users/alifiroozi/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>میز کار هوشمند معاملات طلا | Gold Session Lab Pro v3.6</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-body: #f8fafc;
            --bg-card: #ffffff;
            --border-card: #e2e8f0;
            --border-subtle: #edf2f7;
            --text-heading: #0f172a;
            --text-body: #334155;
            --text-muted: #64748b;
            
            --success-bg: #ecfdf5;
            --success-border: #a7f3d0;
            --success-text: #065f46;
            --success-accent: #10b981;

            --warning-bg: #fffbeb;
            --warning-border: #fde68a;
            --warning-text: #92400e;
            --warning-accent: #f59e0b;

            --danger-bg: #fef2f2;
            --danger-border: #fecaca;
            --danger-text: #991b1b;
            --danger-accent: #ef4444;

            --blue-bg: #eff6ff;
            --blue-border: #bfdbfe;
            --blue-text: #1e40af;
            --blue-accent: #3b82f6;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-body);
            color: var(--text-body);
            font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            height: 100vh;
            max-height: 100vh;
            padding: 10px 14px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .mono {
            font-family: 'JetBrains Mono', monospace;
            direction: ltr;
            display: inline-block;
        }

        /* 1. TOP NAV - Ultra Slim & Sleek */
        nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 7px 14px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 10px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
            flex-shrink: 0;
            height: 44px;
        }

        .nav-brand {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .brand-icon {
            width: 28px;
            height: 28px;
            background: linear-gradient(135deg, #f59e0b, #d97706);
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 15px;
        }

        .brand-text h1 {
            font-size: 13.5px;
            font-weight: 800;
            color: var(--text-heading);
            line-height: 1.1;
        }

        .brand-text p {
            font-size: 10px;
            color: var(--text-muted);
        }

        .nav-pills {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .pill {
            background: #f8fafc;
            border: 1px solid var(--border-card);
            padding: 4px 10px;
            border-radius: 7px;
            font-size: 11px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 5px;
            height: 28px;
        }

        .pill-live {
            background: var(--success-bg);
            border-color: var(--success-border);
            color: var(--success-text);
        }

        .pulse-dot {
            width: 7px;
            height: 7px;
            background-color: var(--success-accent);
            border-radius: 50%;
            animation: pulse-ring 1.8s infinite;
        }

        @keyframes pulse-ring {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        /* 2. MAIN WORKSPACE (Split Side-by-Side: Left Cockpit 60% / Right Log 40%) */
        .workspace {
            display: grid;
            grid-template-columns: 58fr 42fr;
            gap: 10px;
            flex: 1;
            min-height: 0;
        }

        @media (max-width: 1050px) {
            body { height: auto; max-height: none; overflow: auto; }
            .workspace { grid-template-columns: 1fr; }
        }

        /* LEFT SIDE: Cockpit, AI Reasoning & Filters */
        .left-cockpit {
            display: flex;
            flex-direction: column;
            gap: 8px;
            overflow-y: auto;
            min-height: 0;
            padding-left: 2px;
        }

        /* AI Reasoning Banner - High Priority Focal Area */
        .reasoning-box {
            background: #ffffff;
            border-radius: 11px;
            border: 1.5px solid #e2e8f0;
            padding: 10px 14px;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
            transition: all 0.25s ease;
            flex-shrink: 0;
        }

        .reasoning-box.filtered {
            border-color: #fca5a5;
            background: linear-gradient(180deg, #ffffff 0%, #fff5f5 100%);
        }

        .reasoning-box.hunting {
            border-color: #fde68a;
            background: linear-gradient(180deg, #ffffff 0%, #fffbeb 100%);
        }

        .reasoning-box.executed {
            border-color: #86efac;
            background: linear-gradient(180deg, #ffffff 0%, #f0fdf4 100%);
        }

        .reason-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }

        .status-badge {
            font-size: 11px;
            font-weight: 800;
            padding: 3px 10px;
            border-radius: 16px;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        .status-badge.red { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); }
        .status-badge.amber { background: var(--warning-bg); color: var(--warning-text); border: 1px solid var(--warning-border); }
        .status-badge.green { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); }

        .reason-title {
            font-size: 13.5px;
            font-weight: 800;
            color: var(--text-heading);
            margin-bottom: 4px;
            line-height: 1.35;
        }

        .reason-desc {
            font-size: 11.5px;
            color: #475569;
            line-height: 1.45;
        }

        .reason-chips {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
            margin-top: 8px;
        }

        .chip {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 7px;
            padding: 5px 8px;
            font-size: 10.5px;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .chip-label { color: var(--text-muted); font-weight: 600; }
        .chip-val { color: var(--text-heading); font-weight: 800; }

        /* Price & Range Compact Dual Box */
        .price-range-grid {
            display: grid;
            grid-template-columns: 1fr 1.6fr;
            gap: 8px;
            flex-shrink: 0;
        }

        .price-panel {
            background: #ffffff;
            border: 1px solid var(--border-card);
            border-radius: 11px;
            padding: 10px 12px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 11px;
            font-weight: 700;
            color: var(--text-muted);
        }

        .big-price {
            font-size: 27px;
            font-weight: 900;
            color: #0f172a;
            line-height: 1.1;
            margin: 4px 0;
            letter-spacing: -0.5px;
        }

        .price-sub {
            display: flex;
            justify-content: space-between;
            font-size: 10px;
            color: var(--text-muted);
        }

        .range-panel {
            background: #ffffff;
            border: 1px solid var(--border-card);
            border-radius: 11px;
            padding: 10px 12px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
        }

        .range-extremes {
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            font-weight: 700;
        }

        .range-bar {
            height: 11px;
            background: #e2e8f0;
            border-radius: 6px;
            position: relative;
            margin: 7px 0 5px 0;
        }

        .range-fill {
            position: absolute;
            height: 100%;
            background: linear-gradient(90deg, #60a5fa, #3b82f6);
            border-radius: 6px;
            width: 100%;
            opacity: 0.35;
        }

        .range-pin {
            position: absolute;
            top: -4px;
            width: 8px;
            height: 19px;
            background: #0f172a;
            border: 1.5px solid #ffffff;
            border-radius: 3px;
            transform: translateX(-50%);
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            transition: left 0.3s ease;
        }

        .range-sub {
            display: flex;
            justify-content: space-between;
            font-size: 10px;
            color: var(--text-muted);
        }

        /* 6 Filters Matrix - 3x2 Compact Grid */
        .filters-matrix {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
            flex-shrink: 0;
        }

        .filter-cell {
            background: #ffffff;
            border: 1px solid var(--border-card);
            border-radius: 9px;
            padding: 6px 9px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
        }

        .filter-info {
            display: flex;
            flex-direction: column;
            gap: 1px;
        }

        .f-title { font-size: 10px; color: var(--text-muted); font-weight: 600; }
        .f-val { font-size: 11.5px; font-weight: 800; color: var(--text-heading); }

        .f-tag {
            font-size: 9.5px;
            font-weight: 800;
            padding: 2px 7px;
            border-radius: 5px;
        }

        .tag-pass { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); }
        .tag-block { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); }
        .tag-wait { background: var(--warning-bg); color: var(--warning-text); border: 1px solid var(--warning-border); }

        /* Strategy Parameter Mini Card */
        .strat-card {
            background: #ffffff;
            border: 1px solid var(--border-card);
            border-radius: 9px;
            padding: 6px 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 10.5px;
            color: var(--text-muted);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
            flex-shrink: 0;
        }

        .strat-card strong {
            color: var(--text-heading);
            font-weight: 700;
        }

        /* RIGHT SIDE: Dedicated Live Journal & Log Stream Column */
        .right-journal {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 11px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
            min-height: 0;
        }

        .journal-header {
            padding: 9px 12px;
            background: #f8fafc;
            border-bottom: 1px solid var(--border-card);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
        }

        .journal-title {
            font-size: 12.5px;
            font-weight: 800;
            color: var(--text-heading);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .log-count-badge {
            background: #e2e8f0;
            color: #475569;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 10px;
        }

        .journal-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 6px 8px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        /* Log Entry Card in Sidebar */
        .log-item {
            background: #ffffff;
            border: 1px solid var(--border-card);
            border-radius: 8px;
            padding: 7px 10px;
            transition: all 0.2s ease;
            position: relative;
            flex-shrink: 0;
        }

        .log-item:hover {
            border-color: #cbd5e1;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.03);
        }

        .log-item.latest {
            border-right: 3.5px solid var(--warning-accent);
            background: #fffdf5;
        }

        .log-item.filtered {
            border-right: 3.5px solid var(--danger-accent);
            background: #fffafa;
        }

        .log-item.executed {
            border-right: 3.5px solid var(--success-accent);
            background: #f0fdf4;
        }

        .log-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 3px;
        }

        .log-time {
            font-size: 10px;
            color: var(--text-muted);
            font-weight: 600;
        }

        .log-price {
            font-size: 11.5px;
            font-weight: 800;
            color: #0f172a;
        }

        .log-decision-pill {
            font-size: 9.5px;
            font-weight: 800;
            padding: 1.5px 6px;
            border-radius: 5px;
        }

        .log-decision-pill.red { background: #fee2e2; color: #991b1b; }
        .log-decision-pill.amber { background: #fef3c7; color: #92400e; }
        .log-decision-pill.green { background: #dcfce7; color: #166534; }

        .log-reason {
            font-size: 11px;
            color: #334155;
            line-height: 1.4;
            font-weight: 500;
        }

        .log-metrics-row {
            display: flex;
            gap: 8px;
            font-size: 9.5px;
            color: #64748b;
            margin-top: 3px;
            padding-top: 3px;
            border-top: 1px dashed #f1f5f9;
        }
    </style>
</head>
<body>
    <!-- Top Compact Navigation -->
    <nav>
        <div class="nav-brand">
            <div class="brand-icon">🏆</div>
            <div class="brand-text">
                <h1>Gold Session Lab Pro v3.6 — میز کار هوشمند طلا</h1>
                <p>مدل استراتژی شکست سشن Heavy طلا | حساب دمو متاتریدر ۵</p>
            </div>
        </div>
        <div class="nav-pills">
            <div class="pill pill-live">
                <div class="pulse-dot"></div>
                <span>اتصال زنده به متاتریدر ۵</span>
            </div>
            <div class="pill">
                <span>حساب:</span>
                <strong class="mono" id="nav-login">91551123</strong>
            </div>
            <div class="pill">
                <span>موجودی:</span>
                <strong class="mono" id="nav-balance" style="color:#059669;">$1,000.00</strong>
            </div>
            <div class="pill">
                <span>ساعت UTC:</span>
                <strong class="mono" id="nav-utc">--:--:--</strong>
            </div>
            <div class="pill">
                <span>ساعت بروکر:</span>
                <strong class="mono" id="nav-srv">--:--:--</strong>
            </div>
        </div>
    </nav>

    <!-- Main Workspace (Split View) -->
    <div class="workspace">
        <!-- LEFT: Cockpit, AI Decision & Institutional Filters -->
        <div class="left-cockpit">
            <!-- AI Reasoning Hero -->
            <div class="reasoning-box hunting" id="reason-hero">
                <div class="reason-header">
                    <div class="status-badge amber" id="hero-badge">
                        <span>🔍</span>
                        <span id="hero-badge-text">در کمین شکست لندن (Active Hunting)</span>
                    </div>
                    <span style="font-size: 10.5px; color: var(--text-muted);" id="scan-timer">پنجره لندن: در حال پایش</span>
                </div>

                <div class="reason-title" id="hero-main-title">
                    چرا الان ربات ترید نمی‌کند؟ شکست زیر کف آسیا رخ داده، اما تاییدیه ساختار تایم‌فریم M15 (BOS) هنوز تکمیل نشده است.
                </div>

                <div class="reason-desc" id="hero-sub-desc">
                    قیمت زیر کف رنج آسیا نفوذ کرده و کندل ۵ دقیقه‌ای با بدنه قوی بسته شده است؛ طبق استراتژی هوشمند Heavy، ورود تا زمان تایید شکست ساختار تایم‌فریم بالاتر (M15 BOS) و حجم بالای 1.10x مسدود می‌ماند تا از افتادن در تله شکست جعلی جلوگیری شود.
                </div>

                <div class="reason-chips">
                    <div class="chip">
                        <span class="chip-label">موقعیت قیمت طلا</span>
                        <span class="chip-val" id="chip-pos">شکست نزولی (زیر کف آسیا)</span>
                    </div>
                    <div class="chip">
                        <span class="chip-label">فیلتر فعال محافظتی</span>
                        <span class="chip-val" id="chip-filter" style="color: #d97706;">ساختار M15 BOS</span>
                    </div>
                    <div class="chip">
                        <span class="chip-label">حجم معاملات نهادی</span>
                        <span class="chip-val" id="chip-vol" style="color: #dc2626;">1.02x (نیاز به 1.10x)</span>
                    </div>
                </div>
            </div>

            <!-- Price & Range Dual Panel -->
            <div class="price-range-grid">
                <!-- Price Box -->
                <div class="price-panel">
                    <div class="panel-header">
                        <span>مظنه زنده XAUUSD_o</span>
                        <span class="mono" id="live-spread">اسپرد: ۲۲ pts</span>
                    </div>
                    <div class="big-price mono" id="hero-bid">4084.41</div>
                    <div class="price-sub">
                        <span>خرید (Ask): <strong class="mono" id="hero-ask">4084.63</strong></span>
                        <span>فروش (Bid): <strong class="mono" id="hero-bid-sub">4084.41</strong></span>
                    </div>
                </div>

                <!-- Range Box -->
                <div class="range-panel">
                    <div class="panel-header">
                        <span>رنج سشن آسیا (سقف / کف واقعی)</span>
                        <span class="mono" id="hero-width" style="color: #059669; font-weight:800;">عرض: ۳۳.۳۰$</span>
                    </div>
                    <div class="range-extremes">
                        <span style="color: #dc2626;">کف: <strong class="mono" id="hero-low">4108.10</strong></span>
                        <span style="color: #2563eb;">سقف: <strong class="mono" id="hero-high">4141.40</strong></span>
                    </div>
                    <div class="range-bar">
                        <div class="range-fill"></div>
                        <div class="range-pin" id="hero-needle" style="left: 0%;"></div>
                    </div>
                    <div class="range-sub">
                        <span>فاصله تا سقف: <strong class="mono" id="dist-high" style="color: #2563eb;">$56.99</strong></span>
                        <span>فاصله تا کف: <strong class="mono" id="dist-low" style="color: #dc2626;">-$23.69</strong></span>
                    </div>
                </div>
            </div>

            <!-- 6 Institutional Filters Matrix -->
            <div class="filters-matrix">
                <div class="filter-cell">
                    <div class="filter-info">
                        <span class="f-title">فیلتر روز هفته</span>
                        <span class="f-val" id="m-day">سه‌شنبه</span>
                    </div>
                    <span class="f-tag tag-pass" id="m-day-tag">مجاز</span>
                </div>

                <div class="filter-cell">
                    <div class="filter-info">
                        <span class="f-title">عرض رنج آسیا</span>
                        <span class="f-val mono" id="m-width">$33.30</span>
                    </div>
                    <span class="f-tag tag-pass" id="m-width-tag">مجاز (Heavy)</span>
                </div>

                <div class="filter-cell">
                    <div class="filter-info">
                        <span class="f-title">شکست کندل M5</span>
                        <span class="f-val" id="m-break" style="color:#dc2626;">شکست نزولی ▼</span>
                    </div>
                    <span class="f-tag tag-pass" id="m-break-tag">تأیید شکست</span>
                </div>

                <div class="filter-cell">
                    <div class="filter-info">
                        <span class="f-title">قدرت بدنه کندل</span>
                        <span class="f-val mono" id="m-body">60.0%</span>
                    </div>
                    <span class="f-tag tag-pass" id="m-body-tag">قوی (>=45%)</span>
                </div>

                <div class="filter-cell">
                    <div class="filter-info">
                        <span class="f-title">ساختار M15 BOS</span>
                        <span class="f-val" id="m-bos">خنثی (0)</span>
                    </div>
                    <span class="f-tag tag-wait" id="m-bos-tag">در انتظار</span>
                </div>

                <div class="filter-cell">
                    <div class="filter-info">
                        <span class="f-title">حجم تیک و FVG</span>
                        <span class="f-val mono" id="m-vol">1.02x</span>
                    </div>
                    <span class="f-tag tag-block" id="m-vol-tag">ضعیف (<1.10x)</span>
                </div>
            </div>

            <!-- Strategy Config Strip -->
            <div class="strat-card">
                <span>استراتژی: <strong>London Breakout Heavy Optimized</strong></span>
                <span>تایم فریم: <strong>M5</strong></span>
                <span>ریسک مجاز: <strong>۱.۰٪ پویا</strong></span>
                <span>حد ضرر: <strong>کف/سقف رنج آسیا</strong></span>
                <span>سود شناور: <strong class="mono" style="color:#059669;">$0.00</strong></span>
            </div>
        </div>

        <!-- RIGHT: Dedicated Live Journal & Log Stream Column -->
        <div class="right-journal">
            <div class="journal-header">
                <div class="journal-title">
                    <span>📋</span>
                    <span>دفترچه وقایع و لاگ تصمیمات زنده (Live Journal)</span>
                </div>
                <div class="log-count-badge" id="journal-count">۰ رکورد</div>
            </div>

            <div class="journal-scroll" id="journal-stream">
                <div style="text-align:center; padding: 25px; color: #94a3b8; font-size: 12px;">
                    در حال اتصال به لاگ‌های زنده متاتریدر ۵...
                </div>
            </div>
        </div>
    </div>

    <script>
        async function updateTelemetry() {
            try {
                const res = await fetch('/api/telemetry?t=' + Date.now());
                if(!res.ok) return;
                const d = await res.json();

                // Nav Time
                if(d.utc_time) {
                    const p = d.utc_time.split(' ');
                    document.getElementById('nav-utc').innerText = p.length > 1 ? p[1] : d.utc_time;
                }
                if(d.server_time) {
                    const p = d.server_time.split(' ');
                    document.getElementById('nav-srv').innerText = p.length > 1 ? p[1] : d.server_time;
                }
                if(d.account_balance) {
                    document.getElementById('nav-balance').innerText = '$' + Number(d.account_balance).toLocaleString('en-US', {minimumFractionDigits: 2});
                }

                // Price Quote
                const bid = Number(d.current_bid || 0);
                const ask = Number(d.current_ask || 0);
                if(bid > 0) {
                    document.getElementById('hero-bid').innerText = bid.toFixed(2);
                    document.getElementById('hero-bid-sub').innerText = bid.toFixed(2);
                }
                if(ask > 0) {
                    document.getElementById('hero-ask').innerText = ask.toFixed(2);
                }

                if(bid > 0 && ask > 0) {
                    const spreadPts = Math.round((ask - bid) * 100);
                    document.getElementById('live-spread').innerText = 'اسپرد: ' + spreadPts + ' pts';
                }

                // Range
                const aHigh = Number(d.asian_high || 0);
                const aLow = Number(d.asian_low || 0);
                const aWidth = Number(d.asian_width || 0);

                if(aHigh > 0 && aLow > 0) {
                    document.getElementById('hero-high').innerText = aHigh.toFixed(2);
                    document.getElementById('hero-low').innerText = aLow.toFixed(2);
                    document.getElementById('hero-width').innerText = 'عرض: $' + aWidth.toFixed(2);

                    const toHigh = (aHigh - bid).toFixed(2);
                    const toLow = (bid - aLow).toFixed(2);
                    document.getElementById('dist-high').innerText = (toHigh >= 0 ? '$' : '-$') + Math.abs(toHigh);
                    document.getElementById('dist-low').innerText = (toLow >= 0 ? '$' : '-$') + Math.abs(toLow);

                    const pct = ((bid - aLow) / (aHigh - aLow)) * 100;
                    const clamped = Math.max(0, Math.min(100, pct));
                    document.getElementById('hero-needle').style.left = clamped + '%';
                }

                // Window Countdown
                if(d.window_status) {
                    document.getElementById('scan-timer').innerText = 'پنجره لندن: ' + d.window_status;
                }

                // Matrix Cells
                document.getElementById('m-width').innerText = '$' + aWidth.toFixed(2);
                document.getElementById('m-width-tag').className = 'f-tag tag-pass';
                document.getElementById('m-width-tag').innerText = 'مجاز (Heavy)';

                // Breakout
                const brkSide = Number(d.breakout_side || 0);
                if(brkSide === 1) {
                    document.getElementById('m-break').innerText = 'شکست صعودی ▲';
                    document.getElementById('m-break').style.color = '#16a34a';
                    document.getElementById('m-break-tag').className = 'f-tag tag-pass';
                    document.getElementById('m-break-tag').innerText = 'تأیید شکست';
                } else if(brkSide === -1) {
                    document.getElementById('m-break').innerText = 'شکست نزولی ▼';
                    document.getElementById('m-break').style.color = '#dc2626';
                    document.getElementById('m-break-tag').className = 'f-tag tag-pass';
                    document.getElementById('m-break-tag').innerText = 'تأیید شکست';
                } else {
                    document.getElementById('m-break').innerText = 'درون رنج';
                    document.getElementById('m-break').style.color = '#0f172a';
                    document.getElementById('m-break-tag').className = 'f-tag tag-wait';
                    document.getElementById('m-break-tag').innerText = 'بدون شکست';
                }

                // Candle Body
                document.getElementById('m-body').innerText = (Number(d.candle_strength || 0) * 100).toFixed(1) + '%';
                if(Number(d.candle_strength || 0) >= 0.45) {
                    document.getElementById('m-body-tag').className = 'f-tag tag-pass';
                    document.getElementById('m-body-tag').innerText = 'قوی (>=45%)';
                } else {
                    document.getElementById('m-body-tag').className = 'f-tag tag-block';
                    document.getElementById('m-body-tag').innerText = 'ضعیف (<45%)';
                }

                // BOS M15
                const bos = Number(d.bos_m15 || 0);
                if(bos === 1) {
                    document.getElementById('m-bos').innerText = 'صعودی (+1)';
                    document.getElementById('m-bos-tag').className = 'f-tag tag-pass';
                    document.getElementById('m-bos-tag').innerText = 'تأیید ساختار';
                } else if(bos === -1) {
                    document.getElementById('m-bos').innerText = 'نزولی (-1)';
                    document.getElementById('m-bos-tag').className = 'f-tag tag-pass';
                    document.getElementById('m-bos-tag').innerText = 'تأیید ساختار';
                } else {
                    document.getElementById('m-bos').innerText = 'خنثی (0)';
                    document.getElementById('m-bos-tag').className = 'f-tag tag-wait';
                    document.getElementById('m-bos-tag').innerText = 'در انتظار';
                }

                // Volume
                const vol = Number(d.volume_ratio || 0);
                document.getElementById('m-vol').innerText = vol.toFixed(2) + 'x';
                if(vol >= 1.10) {
                    document.getElementById('m-vol-tag').className = 'f-tag tag-pass';
                    document.getElementById('m-vol-tag').innerText = 'کافی (>=1.10x)';
                } else {
                    document.getElementById('m-vol-tag').className = 'f-tag tag-block';
                    document.getElementById('m-vol-tag').innerText = 'ضعیف (<1.10x)';
                }

                // AI Hero Reasoning Box
                const heroBox = document.getElementById('reason-hero');
                const badge = document.getElementById('hero-badge');
                const badgeText = document.getElementById('hero-badge-text');
                const mainTitle = document.getElementById('hero-main-title');
                const subDesc = document.getElementById('hero-sub-desc');

                const dec = d.decision || '';
                const reasonEn = d.reason_en || '';

                if(dec.includes('SIGNAL')) {
                    heroBox.className = 'reasoning-box executed';
                    badge.className = 'status-badge green';
                    badgeText.innerText = '⚡ سیگنال ورود با موفقیت صادر شد!';
                    mainTitle.innerText = 'تمامی شروط نهادی تأیید شد؛ ورود به پوزیشن انجام گرفت.';
                    subDesc.innerText = 'شکست سشن با بدنه قدرتمند، تاییدیه ساختار M15، حجم بالای 1.10x و مدیریت سرمایه ۱٪ پویا اجرا شد.';
                } else if(dec.includes('BOS') || dec.includes('Structure')) {
                    heroBox.className = 'reasoning-box hunting';
                    badge.className = 'status-badge amber';
                    badgeText.innerText = '🔍 در کمین شکست لندن (Active Hunting)';
                    mainTitle.innerText = 'چرا الان ربات ترید نمی‌کند؟ شکست زیر کف آسیا رخ داده، اما تاییدیه ساختار تایم‌فریم M15 (BOS) هنوز تکمیل نشده است.';
                    subDesc.innerText = `قیمت در $${bid.toFixed(2)} و زیر کف رنج آسیا ($${aLow.toFixed(2)}) نفوذ کرده است؛ طبق الگوریتم Heavy، ورود تا زمان بسته شدن کندل ساختاری M15 و حجم بالای 1.10x مسدود می‌ماند تا از تله شکست جعلی جلوگیری شود.`;
                    document.getElementById('chip-pos').innerText = `شکست نزولی (زیر $${aLow.toFixed(2)})`;
                    document.getElementById('chip-filter').innerText = 'ساختار M15 BOS';
                    document.getElementById('chip-vol').innerText = `${vol.toFixed(2)}x (نیاز به 1.10x)`;
                } else if(dec.includes('Volume')) {
                    heroBox.className = 'reasoning-box hunting';
                    badge.className = 'status-badge amber';
                    badgeText.innerText = '🔍 در کمین شکار (حجم ناکافی)';
                    mainTitle.innerText = 'چرا الان ربات ترید نمی‌کند؟ شکست رخ داده اما حجم معاملات نهادی هنوز به ۱.۱۰ برابر میانگین نرسیده است.';
                    subDesc.innerText = 'برای ورود مطمئن سازمانی، حضور نقدینگی قدرتمند الزامی است؛ ربات منتظر تزریق نقدینگی در کندل‌های آتی است.';
                } else if(dec.includes('Outside London')) {
                    heroBox.className = 'reasoning-box filtered';
                    badge.className = 'status-badge red';
                    badgeText.innerText = '⛔ خارج از پنجره معاملاتی لندن';
                    mainTitle.innerText = 'پنجره بریک‌اوت لندن بسته شده است؛ ربات در حالت آماده‌باش برای سشن فردا قرار دارد.';
                    subDesc.innerText = 'معاملات شکست سشن تنها بین ساعات ۰۸:۰۰ تا ۱۰:۰۰ UTC (۱۱:۳۰ تا ۱۳:۳۰ به وقت تهران) مجاز است.';
                } else if(dec.includes('Inside Asian Range') || brkSide === 0) {
                    heroBox.className = 'reasoning-box hunting';
                    badge.className = 'status-badge amber';
                    badgeText.innerText = '🔍 در حال اسکن بازار (درون رنج آسیا)';
                    mainTitle.innerText = 'چرا الان ربات ترید نمی‌کند؟ قیمت هنوز در میانه رنج آسیا در نوسان است و خروجی رخ نداده است.';
                    subDesc.innerText = `قیمت در $${bid.toFixed(2)} و بین کف ($${aLow.toFixed(2)}) و سقف ($${aHigh.toFixed(2)}) محبوس است؛ به محض شکست معتبر، بررسی شروط نهادی آغاز خواهد شد.`;
                    document.getElementById('chip-pos').innerText = `درون رنج ($${bid.toFixed(2)})`;
                    document.getElementById('chip-filter').innerText = 'عدم شکست رنج';
                    document.getElementById('chip-vol').innerText = `${vol.toFixed(2)}x`;
                } else {
                    heroBox.className = 'reasoning-box filtered';
                    badge.className = 'status-badge red';
                    badgeText.innerText = '⛔ عدم ورود به معامله (فیلتر محافظتی)';
                    mainTitle.innerText = 'عدم تطابق شروط ورود در استراتژی Heavy.';
                    subDesc.innerText = reasonEn;
                }

            } catch(e) {
                console.error("Telemetry error", e);
            }
        }

        async function updateJournal() {
            try {
                const res = await fetch('/api/journal?t=' + Date.now());
                if(!res.ok) return;
                const list = await res.json();
                if(!Array.isArray(list) || list.length === 0) return;

                document.getElementById('journal-count').innerText = list.length + ' رکورد ثبت‌شده';

                const container = document.getElementById('journal-stream');
                container.innerHTML = '';

                list.slice(-30).reverse().forEach((r, idx) => {
                    const item = document.createElement('div');

                    let pillClass = 'amber';
                    let pillText = 'اسکن / کمین';
                    let itemClass = 'latest';

                    if(r.Decision && r.Decision.includes('BOS')) {
                        pillClass = 'amber';
                        pillText = 'در انتظار BOS';
                        itemClass = 'latest';
                    } else if(r.Decision && r.Decision.includes('FILTERED')) {
                        pillClass = 'red';
                        pillText = 'رد معامله (فیلتر)';
                        itemClass = 'filtered';
                    } else if(r.Decision && r.Decision.includes('SIGNAL')) {
                        pillClass = 'green';
                        pillText = 'اجرای سفارش';
                        itemClass = 'executed';
                    }

                    item.className = 'log-item ' + itemClass;

                    const num = list.length - idx;
                    let faReason = r.Reason || '';
                    if(faReason.includes('market structure did not confirm')) {
                        faReason = 'شکست زیر کف آسیا رخ داده؛ در انتظار تایید ساختار M15 BOS و حجم 1.10x.';
                    } else if(faReason.includes('exceeds')) {
                        faReason = 'عرض رنج آسیا فراتر از حد مجاز.';
                    } else if(faReason.includes('Outside London')) {
                        faReason = 'خارج از پنجره معاملاتی لندن (08:00 تا 10:00 UTC).';
                    }

                    const brkLabel = r.Breakout === 'NONE' ? 'درون رنج' : (r.Breakout === 'BULLISH' ? 'شکست صعودی ▲' : 'شکست نزولی ▼');

                    item.innerHTML = `
                        <div class="log-top">
                            <span class="log-time mono">#${num} • ${r.UTC_Time || '--'} UTC (بروکر ${r.Server_Time || '--'})</span>
                            <span class="log-price mono">$${r.Bid || '--'}</span>
                            <span class="log-decision-pill ${pillClass}">${pillText}</span>
                        </div>
                        <div class="log-reason">${faReason}</div>
                        <div class="log-metrics-row mono">
                            <span>رنج آسیا: ${r.Asian_Range || '--'}</span>
                            <span>وضعیت: ${brkLabel}</span>
                            <span>بدنه: ${r.Candle_Body || '--'}</span>
                            <span>حجم: ${r.Vol_Ratio ? r.Vol_Ratio + 'x' : '--'}</span>
                        </div>
                    `;
                    container.appendChild(item);
                });
            } catch(e) {
                console.error("Journal error", e);
            }
        }

        updateTelemetry();
        updateJournal();
        setInterval(updateTelemetry, 1000);
        setInterval(updateJournal, 2000);
    </script>
</body>
</html>
"""

class LiveDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        if parsed.path == "/api/telemetry":
            telemetry_file = os.path.join(MT5_FILES_DIR, "live_telemetry.json")
            data = {}
            if os.path.exists(telemetry_file):
                try:
                    with open(telemetry_file, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                except Exception as e:
                    data = {"error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if parsed.path == "/api/journal":
            journal_file = os.path.join(MT5_FILES_DIR, "live_decisions_journal.csv")
            records = []
            if os.path.exists(journal_file):
                try:
                    with open(journal_file, "r", encoding="utf-8", errors="ignore") as f:
                        records = list(csv.DictReader(f))
                except Exception as e:
                    records = [{"error": str(e)}]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(records).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), LiveDashboardHandler)
    print(f"[*] Gold Session Lab Pro Split-Screen Light Dashboard running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    run_server()
