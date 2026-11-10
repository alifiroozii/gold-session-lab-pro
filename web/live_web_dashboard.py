#!/usr/bin/env python3
"""
Gold Session Lab Pro v3.6 - Ultra-Clean Light-Theme Live Dashboard Server
Connects MT5 live telemetry and decision journals directly to a modern, user-friendly light UI.
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
SCREENSHOT_PATH = "/Users/alifiroozi/.gemini/antigravity/brain/fc7d5427-edd2-485c-b4db-cf3528c4d919/mt5_chart_both_preview.jpg"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>داشبورد زنده و هوشمند معاملات طلا | Gold Session Lab Pro v3.6</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-body: #f8fafc;
            --bg-card: #ffffff;
            --border-card: #e2e8f0;
            --border-focus: #3b82f6;
            --text-heading: #0f172a;
            --text-body: #334155;
            --text-muted: #64748b;
            --text-light: #94a3b8;
            
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

            --primary-blue: #2563eb;
            --primary-bg: #eff6ff;
            --primary-border: #bfdbfe;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-body);
            background-image: 
                radial-gradient(at 0% 0%, rgba(219, 234, 254, 0.45) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(254, 243, 199, 0.4) 0px, transparent 50%),
                radial-gradient(at 50% 100%, rgba(241, 245, 249, 0.5) 0px, transparent 50%);
            color: var(--text-body);
            font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            min-height: 100vh;
            padding: 24px 20px;
            line-height: 1.6;
        }

        .mono {
            font-family: 'JetBrains Mono', monospace;
            direction: ltr;
            display: inline-block;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        /* Top Navbar */
        nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            padding: 18px 24px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 20px;
            box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.04), 0 2px 6px -1px rgba(0, 0, 0, 0.02);
            margin-bottom: 24px;
        }

        .nav-brand {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-icon {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #f59e0b, #d97706);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 22px;
            box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
        }

        .brand-text h1 {
            font-size: 19px;
            font-weight: 800;
            color: var(--text-heading);
            letter-spacing: -0.3px;
        }

        .brand-text p {
            font-size: 13px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .nav-metrics {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .pill {
            background: #f8fafc;
            border: 1px solid var(--border-card);
            padding: 8px 16px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .pill-status {
            display: flex;
            align-items: center;
            gap: 8px;
            background: var(--success-bg);
            border: 1px solid var(--success-border);
            color: var(--success-text);
        }

        .pulse-dot {
            width: 10px;
            height: 10px;
            background-color: var(--success-accent);
            border-radius: 50%;
            box-shadow: 0 0 0 rgba(16, 185, 129, 0.4);
            animation: pulse-ring 1.8s infinite;
        }

        @keyframes pulse-ring {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        /* Hero Decision & Reasoning Center */
        .reasoning-hero {
            background: #ffffff;
            border-radius: 20px;
            border: 2px solid #e2e8f0;
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
            position: relative;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .reasoning-hero.filtered {
            border-color: #fca5a5;
            background: linear-gradient(180deg, #ffffff 0%, #fef2f2 100%);
        }

        .reasoning-hero.hunting {
            border-color: #fde68a;
            background: linear-gradient(180deg, #ffffff 0%, #fffbeb 100%);
        }

        .reasoning-hero.executed {
            border-color: #86efac;
            background: linear-gradient(180deg, #ffffff 0%, #f0fdf4 100%);
        }

        .hero-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
            border-bottom: 1px solid rgba(0,0,0,0.06);
            padding-bottom: 16px;
        }

        .hero-badge {
            font-size: 14px;
            font-weight: 700;
            padding: 8px 20px;
            border-radius: 30px;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .hero-badge.red {
            background: var(--danger-bg);
            color: var(--danger-text);
            border: 1px solid var(--danger-border);
        }

        .hero-badge.amber {
            background: var(--warning-bg);
            color: var(--warning-text);
            border: 1px solid var(--warning-border);
        }

        .hero-badge.green {
            background: var(--success-bg);
            color: var(--success-text);
            border: 1px solid var(--success-border);
        }

        .hero-main-reason {
            font-size: 21px;
            font-weight: 800;
            color: var(--text-heading);
            margin-bottom: 10px;
            line-height: 1.5;
        }

        .hero-sub-reason {
            font-size: 15px;
            color: var(--text-body);
            line-height: 1.8;
            margin-bottom: 22px;
        }

        /* 3-Part Status Breakdown */
        .reason-breakdown {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin-top: 20px;
        }

        @media (max-width: 900px) {
            .reason-breakdown { grid-template-columns: 1fr; }
        }

        .breakdown-item {
            background: rgba(255, 255, 255, 0.85);
            border: 1px solid rgba(0, 0, 0, 0.07);
            border-radius: 14px;
            padding: 16px 20px;
            display: flex;
            align-items: flex-start;
            gap: 12px;
        }

        .breakdown-icon {
            font-size: 22px;
            line-height: 1;
            margin-top: 2px;
        }

        .breakdown-title {
            font-size: 13px;
            font-weight: 700;
            color: var(--text-muted);
            margin-bottom: 4px;
        }

        .breakdown-text {
            font-size: 14px;
            font-weight: 700;
            color: var(--text-heading);
        }

        /* Grid Section */
        .grid-2 {
            display: grid;
            grid-template-columns: 4fr 8fr;
            gap: 20px;
            margin-bottom: 24px;
        }

        @media (max-width: 1024px) {
            .grid-2 { grid-template-columns: 1fr; }
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.03);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            border-bottom: 1px solid #f1f5f9;
            padding-bottom: 12px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 800;
            color: var(--text-heading);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Live Price Card */
        .big-price {
            font-size: 44px;
            font-weight: 900;
            color: #0f172a;
            margin: 6px 0 12px 0;
            letter-spacing: -0.5px;
        }

        .price-details {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-top: 1px solid #f1f5f9;
            border-bottom: 1px solid #f1f5f9;
            margin-bottom: 14px;
            font-size: 14px;
        }

        /* Range Visualizer */
        .range-track-container {
            margin: 24px 0 12px 0;
        }

        .range-extremes {
            display: flex;
            justify-content: space-between;
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 10px;
        }

        .range-bar {
            height: 24px;
            background: #e2e8f0;
            border-radius: 12px;
            position: relative;
            overflow: visible;
        }

        .range-inner-fill {
            position: absolute;
            height: 100%;
            background: linear-gradient(90deg, #60a5fa, #3b82f6);
            border-radius: 12px;
            width: 100%;
            opacity: 0.35;
        }

        .range-needle {
            position: absolute;
            top: -6px;
            width: 14px;
            height: 36px;
            background: #1e293b;
            border: 3px solid #ffffff;
            border-radius: 7px;
            transform: translateX(-50%);
            box-shadow: 0 4px 10px rgba(0,0,0,0.25);
            transition: left 0.4s ease;
        }

        /* 6 Filters Checklist Grid */
        .filters-grid {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 14px;
            margin-bottom: 24px;
        }

        @media (max-width: 1100px) {
            .filters-grid { grid-template-columns: repeat(3, 1fr); }
        }
        @media (max-width: 640px) {
            .filters-grid { grid-template-columns: repeat(2, 1fr); }
        }

        .filter-box {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 16px;
            padding: 16px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.02);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .filter-box:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(0,0,0,0.05);
        }

        .filter-status-tag {
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 12px;
            display: inline-block;
            margin-top: 8px;
        }

        .tag-pass { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); }
        .tag-block { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); }
        .tag-wait { background: var(--warning-bg); color: var(--warning-text); border: 1px solid var(--warning-border); }

        /* Journal Table */
        .journal-box {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.03);
            margin-bottom: 24px;
        }

        .table-wrap {
            overflow-x: auto;
            margin-top: 16px;
        }

        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 13px;
            text-align: right;
        }

        th {
            background: #f8fafc;
            color: #475569;
            padding: 14px 16px;
            font-weight: 700;
            border-top: 1px solid #e2e8f0;
            border-bottom: 2px solid #e2e8f0;
            white-space: nowrap;
        }

        td {
            padding: 14px 16px;
            border-bottom: 1px solid #f1f5f9;
            color: #334155;
            white-space: nowrap;
        }

        tr:nth-child(even) td {
            background: #fafafa;
        }

        tr:hover td {
            background: #f0fdf4 !important;
        }

        .badge-pill {
            font-size: 11px;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 12px;
            display: inline-block;
        }

        .badge-pill.danger { background: #fee2e2; color: #991b1b; }
        .badge-pill.warning { background: #fef3c7; color: #92400e; }
        .badge-pill.success { background: #dcfce7; color: #166534; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Navigation Header -->
        <nav>
            <div class="nav-brand">
                <div class="brand-icon">🏆</div>
                <div class="brand-text">
                    <h1>داشبورد زنده تله‌متری معاملات طلا (Gold Session Lab Pro v3.6)</h1>
                    <p>مدل قهرمان شکست سشن لندن | حساب دمو متاتریدر ۵</p>
                </div>
            </div>
            <div class="nav-metrics">
                <div class="pill pill-status">
                    <div class="pulse-dot"></div>
                    <span>متصل به MT5 (زنده)</span>
                </div>
                <div class="pill">
                    <span>شماره حساب:</span>
                    <strong class="mono" id="nav-login">91551123</strong>
                </div>
                <div class="pill">
                    <span>موجودی:</span>
                    <strong class="mono" id="nav-balance" style="color: #059669;">$1,000.00</strong>
                </div>
                <div class="pill">
                    <span>زمان هماهنگ UTC:</span>
                    <strong class="mono" id="nav-utc">--:--:--</strong>
                </div>
            </div>
        </nav>

        <!-- Prominent AI Reasoning & Trade Decision Center -->
        <div class="reasoning-hero filtered" id="reasoning-hero">
            <div class="hero-top">
                <div class="hero-badge red" id="hero-badge">
                    <span>⛔</span>
                    <span id="hero-badge-text">عدم ورود به معامله (معامله مسدود شده است)</span>
                </div>
                <div style="font-size: 13px; color: var(--text-muted);">
                    تایمر اسکن بازار: <strong style="color: #0f172a;" id="scan-countdown">فعال - به‌روزرسانی لحظه‌ای</strong>
                </div>
            </div>

            <div class="hero-main-reason" id="hero-main-reason">
                چرا الان ربات ترید نمی‌کند؟ عرض رنج سشن آسیا امروز ۳۶.۳۹ دلار بوده که از سقف مجاز ۳۰.۰۰ دلار بیشتر است.
            </div>

            <div class="hero-sub-reason" id="hero-sub-reason">
                استراتژی شکست سشن Heavy طلا، روزهایی که بازار در سشن آسیا حرکت بیش از حد (Overextension) انجام می‌دهد را به عنوان روزهای پرریسک دسته‌بندی می‌کند؛ زیرا انرژی اولیه بازار تخلیه شده و نوسانات لندن معمولاً به تله‌های نقدینگی و فیک‌بریک تبدیل می‌شوند.
            </div>

            <div class="reason-breakdown">
                <div class="breakdown-item">
                    <div class="breakdown-icon">🎯</div>
                    <div>
                        <div class="breakdown-title">موقعیت فعلی قیمت نسبت به رنج</div>
                        <div class="breakdown-text" id="reason-pos-text">قیمت در میانه رنج آسیاست (بدون شکست)</div>
                    </div>
                </div>

                <div class="breakdown-item">
                    <div class="breakdown-icon">🛡️</div>
                    <div>
                        <div class="breakdown-title">فیلتر محافظتی فعال</div>
                        <div class="breakdown-text" id="reason-filter-text">فیلتر پهنای رنج آسیا (Max $30) مانع ورود است</div>
                    </div>
                </div>

                <div class="breakdown-item">
                    <div class="breakdown-icon">🌊</div>
                    <div>
                        <div class="breakdown-title">وضعیت نقدینگی نهادی</div>
                        <div class="breakdown-text" id="reason-vol-text">حجم تیک ضعیف است (0.71x < 1.10x)</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 2 Column Market Overview -->
        <div class="grid-2">
            <!-- Price Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>💰</span>
                        <span>مظنه لحظه‌ای انس طلا (XAUUSD_o)</span>
                    </div>
                    <span class="pill mono" id="live-spread">اسپرد: ۲۲ pts</span>
                </div>
                <div class="big-price mono" id="hero-price">4118.50</div>
                <div class="price-details">
                    <span>نرخ خرید (Ask): <strong class="mono" id="hero-ask">--</strong></span>
                    <span>نرخ فروش (Bid): <strong class="mono" id="hero-bid">--</strong></span>
                </div>
                <div style="font-size: 13px; color: var(--text-muted); display: flex; justify-content: space-between;">
                    <span>تایم‌فریم اجرایی: <strong style="color: #0f172a;">M5</strong></span>
                    <span>استراتژی: <strong style="color: #0f172a;">Heavy Optimized</strong></span>
                    <span>حجم‌گذاری: <strong style="color: #059669;">ریسک ۱٪ پویا</strong></span>
                </div>
            </div>

            <!-- Asian Range Visualizer -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>📊</span>
                        <span>رنج سشن آسیا و موقعیت لحظه‌ای قیمت</span>
                    </div>
                    <span class="pill mono" id="hero-range-width" style="color: #b91c1c; background: #fef2f2;">عرض رنج: ۳۶.۳۹$</span>
                </div>
                
                <div class="range-extremes">
                    <span style="color: #dc2626;">کف سشن آسیا (Low): <strong class="mono" id="hero-low">4110.09</strong></span>
                    <span style="color: #2563eb;">سقف سشن آسیا (High): <strong class="mono" id="hero-high">4146.48</strong></span>
                </div>

                <div class="range-track-container">
                    <div class="range-bar">
                        <div class="range-inner-fill"></div>
                        <div class="range-needle" id="hero-needle" style="left: 23%;"></div>
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; font-size: 13px; color: var(--text-muted); margin-top: 14px;">
                    <span>فاصله تا سقف آسیا: <strong class="mono" id="dist-high" style="color: #2563eb;">--</strong></span>
                    <span>فاصله تا کف آسیا: <strong class="mono" id="dist-low" style="color: #dc2626;">--</strong></span>
                    <span>پنجره لندن: <strong id="hero-window-state" style="color: #d97706;">فعال</strong></span>
                </div>
            </div>
        </div>

        <!-- 6 Institutional Strategy Filters -->
        <div class="filters-grid">
            <div class="filter-box">
                <div style="font-size: 24px;">📅</div>
                <div style="font-size: 13px; font-weight: 700; color: #64748b; margin: 4px 0;">فیلتر روز هفته</div>
                <div style="font-size: 16px; font-weight: 800; color: #0f172a;" id="box-day">سه‌شنبه</div>
                <div class="filter-status-tag tag-pass" id="tag-day">تأیید شد (مجاز)</div>
            </div>

            <div class="filter-box">
                <div style="font-size: 24px;">📏</div>
                <div style="font-size: 13px; font-weight: 700; color: #64748b; margin: 4px 0;">عرض رنج آسیا</div>
                <div class="mono" style="font-size: 16px; font-weight: 800; color: #dc2626;" id="box-width">$36.39</div>
                <div class="filter-status-tag tag-block" id="tag-width">بیش از حد مجاز (>30$)</div>
            </div>

            <div class="filter-box">
                <div style="font-size: 24px;">⚡</div>
                <div style="font-size: 13px; font-weight: 700; color: #64748b; margin: 4px 0;">شکست کندل M5</div>
                <div style="font-size: 16px; font-weight: 800; color: #0f172a;" id="box-breakout">درون رنج</div>
                <div class="filter-status-tag tag-wait" id="tag-breakout">بدون شکست</div>
            </div>

            <div class="filter-box">
                <div style="font-size: 24px;">🕯️</div>
                <div style="font-size: 13px; font-weight: 700; color: #64748b; margin: 4px 0;">قدرت بدنه کندل</div>
                <div class="mono" style="font-size: 16px; font-weight: 800; color: #059669;" id="box-body">68.4%</div>
                <div class="filter-status-tag tag-pass" id="tag-body">قدرتمند (>=45%)</div>
            </div>

            <div class="filter-box">
                <div style="font-size: 24px;">🏛️</div>
                <div style="font-size: 13px; font-weight: 700; color: #64748b; margin: 4px 0;">ساختار M15 BOS</div>
                <div style="font-size: 16px; font-weight: 800; color: #0f172a;" id="box-bos">خنثی (0)</div>
                <div class="filter-status-tag tag-wait" id="tag-bos">در انتظار تأیید</div>
            </div>

            <div class="filter-box">
                <div style="font-size: 24px;">📊</div>
                <div style="font-size: 13px; font-weight: 700; color: #64748b; margin: 4px 0;">حجم تیک و FVG</div>
                <div class="mono" style="font-size: 16px; font-weight: 800; color: #dc2626;" id="box-vol">0.71x</div>
                <div class="filter-status-tag tag-block" id="tag-vol">ضعیف (<1.10x)</div>
            </div>
        </div>

        <!-- Live Journal Table Section -->
        <div class="journal-box">
            <div class="card-header">
                <div class="card-title">
                    <span>📋</span>
                    <span>جدول لاگ چرخه‌های ارزیابی زنده ربات (ثبت هر ۱۰ ثانیه)</span>
                </div>
                <span class="pill mono" style="font-size: 12px;">مستقیماً از متاتریدر ۵</span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>زمان (UTC)</th>
                            <th>قیمت (Bid)</th>
                            <th>رنج آسیا</th>
                            <th>پنجره زمانی</th>
                            <th>وضعیت شکست</th>
                            <th>بدنه M5</th>
                            <th>حجم تیک</th>
                            <th>تصمیم نهایی ربات</th>
                            <th>دلیل عدم ورود یا ورود</th>
                        </tr>
                    </thead>
                    <tbody id="journal-tbody">
                        <tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 24px;">در حال بارگذاری اطلاعات زنده...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        async function fetchTelemetry() {
            try {
                const res = await fetch('/api/telemetry?t=' + Date.now());
                if(!res.ok) return;
                const d = await res.json();

                // Top Nav
                if(d.utc_time) document.getElementById('nav-utc').innerText = d.utc_time.split(' ')[1];
                if(d.account_balance) document.getElementById('nav-balance').innerText = '$' + Number(d.account_balance).toLocaleString('en-US', {minimumFractionDigits: 2});

                // Price
                const bid = Number(d.current_bid || 0);
                const ask = Number(d.current_ask || 0);
                document.getElementById('hero-price').innerText = bid.toFixed(2);
                document.getElementById('hero-bid').innerText = bid.toFixed(2);
                document.getElementById('hero-ask').innerText = ask.toFixed(2);

                const spreadPts = Math.round((ask - bid) * 100);
                document.getElementById('live-spread').innerText = 'اسپرد: ' + spreadPts + ' pts';

                // Range
                const aHigh = Number(d.asian_high || 0);
                const aLow = Number(d.asian_low || 0);
                const aWidth = Number(d.asian_width || 0);

                document.getElementById('hero-high').innerText = '$' + aHigh.toFixed(2);
                document.getElementById('hero-low').innerText = '$' + aLow.toFixed(2);
                document.getElementById('hero-range-width').innerText = 'عرض رنج: $' + aWidth.toFixed(2);

                // Distances
                if(aHigh > 0 && aLow > 0 && bid > 0) {
                    const toHigh = (aHigh - bid).toFixed(2);
                    const toLow = (bid - aLow).toFixed(2);
                    document.getElementById('dist-high').innerText = '$' + toHigh;
                    document.getElementById('dist-low').innerText = '$' + toLow;

                    // Needle position
                    const pct = ((bid - aLow) / (aHigh - aLow)) * 100;
                    const clamped = Math.max(0, Math.min(100, pct));
                    document.getElementById('hero-needle').style.left = clamped + '%';
                }

                document.getElementById('hero-window-state').innerText = d.window_status || 'پنجره لندن فعال';

                // 6 Boxes
                document.getElementById('box-width').innerText = '$' + aWidth.toFixed(2);
                if(aWidth > 30.0) {
                    document.getElementById('tag-width').className = 'filter-status-tag tag-block';
                    document.getElementById('tag-width').innerText = 'بیش از حد مجاز (>30$)';
                } else {
                    document.getElementById('tag-width').className = 'filter-status-tag tag-pass';
                    document.getElementById('tag-width').innerText = 'مجاز (<=30$)';
                }

                document.getElementById('box-body').innerText = (Number(d.candle_strength || 0) * 100).toFixed(1) + '%';
                document.getElementById('box-vol').innerText = Number(d.volume_ratio || 0).toFixed(2) + 'x';
                if(Number(d.volume_ratio || 0) >= 1.10) {
                    document.getElementById('tag-vol').className = 'filter-status-tag tag-pass';
                    document.getElementById('tag-vol').innerText = 'کافی (>=1.10x)';
                } else {
                    document.getElementById('tag-vol').className = 'filter-status-tag tag-block';
                    document.getElementById('tag-vol').innerText = 'ضعیف (<1.10x)';
                }

                // AI Hero Decision Box
                const hero = document.getElementById('reasoning-hero');
                const badge = document.getElementById('hero-badge');
                const badgeText = document.getElementById('hero-badge-text');
                const mainReason = document.getElementById('hero-main-reason');
                const subReason = document.getElementById('hero-sub-reason');

                if(d.decision && d.decision.includes('FILTERED')) {
                    hero.className = 'reasoning-hero filtered';
                    badge.className = 'hero-badge red';
                    badgeText.innerText = '⛔ عدم ورود به معامله (معامله مسدود است)';
                    
                    if(aWidth > 30.0) {
                        mainReason.innerText = `چرا الان ربات ترید نمی‌کند؟ عرض رنج آسیا امروز $${aWidth.toFixed(2)} بوده که از سقف مجاز $30.00 بیشتر است.`;
                        subReason.innerText = 'طبق بک‌تست‌های آماری مدل Heavy، روزهایی که رنج آسیا بیش از حد کشیده می‌شود، بازار در لندن فاقد نیروی محرکه لازم برای ادامه روند است و وارد رفتارهای رنج و تله‌های معاملاتی می‌شود.';
                        document.getElementById('reason-filter-text').innerText = 'فیلتر عرض رنج آسیا (>30$) ورود را مسدود کرده است';
                    } else {
                        mainReason.innerText = 'چرا الان ربات ترید نمی‌کند؟ قیمت هنوز در میانه رنج آسیا نوسان می‌کند و شکستی رخ نداده است.';
                        subReason.innerText = 'ورود فقط زمانی مجاز است که یک کندل کامل ۵ دقیقه‌ای بالای سقف یا زیر کف آسیا بسته شود.';
                    }

                    document.getElementById('reason-pos-text').innerText = `قیمت در $${bid.toFixed(2)} و درون رنج سقف و کف محبوس است`;
                    document.getElementById('reason-vol-text').innerText = `حجم تیک جاری (${Number(d.volume_ratio||0).toFixed(2)}x) ضعیف است`;

                } else if(d.decision && d.decision.includes('SIGNAL')) {
                    hero.className = 'reasoning-hero executed';
                    badge.className = 'hero-badge green';
                    badgeText.innerText = '⚡ سیگنال ورود با موفقیت صادر شد!';
                    mainReason.innerText = 'تمامی شروط نهادی تأیید شد؛ ورود به پوزیشن انجام گرفت.';
                    subReason.innerText = 'شکست سشن با بدنه قدرتمند، تاییدیه حجم، FVG معتبر و مدیریت سرمایه ۱٪ اجرا شد.';
                } else {
                    hero.className = 'reasoning-hero hunting';
                    badge.className = 'hero-badge amber';
                    badgeText.innerText = '🔍 در حال اسکن بازار (در انتظار شکست معتبر)';
                    mainReason.innerText = 'پنجره بریک‌اوت لندن فعال است؛ ربات در حال پایش لحظه‌ای کندل‌هاست.';
                    subReason.innerText = 'به محض خروج کندل M5 از رنج آسیا همراه با حجم تیک و FVG، سفارش ورود صادر خواهد شد.';
                }

            } catch(e) {
                console.error("Telemetry error", e);
            }
        }

        async function fetchJournal() {
            try {
                const res = await fetch('/api/journal?t=' + Date.now());
                if(!res.ok) return;
                const list = await res.json();
                if(!Array.isArray(list) || list.length === 0) return;

                const tbody = document.getElementById('journal-tbody');
                tbody.innerHTML = '';

                list.slice(-18).reverse().forEach((r, idx) => {
                    const tr = document.createElement('tr');
                    const num = list.length - idx;
                    
                    let brkPill = '<span class="badge-pill warning">درون رنج</span>';
                    if(r.Breakout === 'BULLISH') brkPill = '<span class="badge-pill success">شکست صعودی ▲</span>';
                    if(r.Breakout === 'BEARISH') brkPill = '<span class="badge-pill danger">شکست نزولی ▼</span>';

                    let decPill = '<span class="badge-pill warning">' + (r.Decision || 'اسکن') + '</span>';
                    if(r.Decision.includes('FILTERED')) decPill = '<span class="badge-pill danger">رد معامله (فیلتر)</span>';
                    if(r.Decision.includes('SIGNAL')) decPill = '<span class="badge-pill success">اجرای سفارش</span>';

                    let faReason = r.Reason || '';
                    if(faReason.includes('exceeds')) {
                        faReason = 'عرض رنج آسیا از ۳۰$ فراتر رفته و قیمت درون رنج است.';
                    } else if(faReason.includes('Outside London')) {
                        faReason = 'خارج از پنجره بریک‌اوت لندن (08:00 تا 10:00 UTC).';
                    }

                    tr.innerHTML = `
                        <td class="mono"><strong>#${num}</strong></td>
                        <td class="mono">${r.UTC_Time || '--'}</td>
                        <td class="mono"><strong>$${r.Bid || '--'}</strong></td>
                        <td class="mono">${r.Asian_Range || '--'}</td>
                        <td>${r.Window || '--'}</td>
                        <td>${brkPill}</td>
                        <td class="mono">${r.Candle_Body || '--'}</td>
                        <td class="mono">${r.Vol_Ratio ? r.Vol_Ratio + 'x' : '--'}</td>
                        <td>${decPill}</td>
                        <td style="color: #475569; max-width: 340px; white-space: normal;">${faReason}</td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch(e) {
                console.error("Journal error", e);
            }
        }

        fetchTelemetry();
        fetchJournal();
        setInterval(fetchTelemetry, 1500);
        setInterval(fetchJournal, 2500);
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
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        if parsed.path == "/api/telemetry":
            telemetry_file = os.path.join(MT5_FILES_DIR, "live_telemetry.json")
            data = {}
            if os.path.exists(telemetry_file):
                try:
                    with open(telemetry_file, "r", encoding="latin1") as f:
                        data = json.load(f)
                except Exception as e:
                    data = {"error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if parsed.path == "/api/journal":
            journal_file = os.path.join(MT5_FILES_DIR, "live_decisions_journal.csv")
            records = []
            if os.path.exists(journal_file):
                try:
                    with open(journal_file, "r", encoding="latin1") as f:
                        records = list(csv.DictReader(f))
                except Exception as e:
                    records = [{"error": str(e)}]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(records).encode("utf-8"))
            return

        if parsed.path == "/api/screenshot":
            if os.path.exists(SCREENSHOT_PATH):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                with open(SCREENSHOT_PATH, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        self.send_response(404)
        self.end_headers()

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), LiveDashboardHandler)
    print(f"[*] Gold Session Lab Pro Clean Light Dashboard running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    run_server()
