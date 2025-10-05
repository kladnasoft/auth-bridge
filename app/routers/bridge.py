# app/routers/bridge.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.core.logging import get_logger
from app.core.redis import caches
from app.models import ServiceLink
from app.routers.service import reload_services
from app.routers.workspace import reload_workspaces
from app.core.types_loader import load_service_types

log = get_logger("auth-bridge.bridge-ui")

router = APIRouter(tags=["service-bridge-ui"])


async def validate_service_api_key(x_api_key: str = Header(..., alias="x-api-key")) -> str:
    """
    Validate a *service* API key (not an admin key).
    Returns the matching service_id to the caller for convenience.
    """
    await reload_services()
    for svc in caches.services.values():
        if getattr(svc, "api_key", None) == x_api_key:
            return svc.id
    raise HTTPException(
        status_code=401,
        detail={"error_code": "INVALID_SERVICE_KEY", "message": "Invalid service x-api-key"},
    )


SERVICE_CONSOLE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>AuthBridge • Service Console</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            primary: {
              50: '#f0f9ff',
              100: '#e0f2fe',
              200: '#bae6fd',
              300: '#7dd3fc',
              400: '#38bdf8',
              500: '#0ea5e9',
              600: '#0284c7',
              700: '#0369a1',
              800: '#075985',
              900: '#0c4a6e',
            },
            gradient: {
              start: '#667eea',
              end: '#764ba2'
            }
          },
          animation: {
            'fade-in': 'fadeIn 0.5s ease-in-out',
            'slide-up': 'slideUp 0.3s ease-out',
            'pulse-soft': 'pulseSoft 2s infinite',
          },
          keyframes: {
            fadeIn: {
              '0%': { opacity: '0' },
              '100%': { opacity: '1' }
            },
            slideUp: {
              '0%': { transform: 'translateY(10px)', opacity: '0' },
              '100%': { transform: 'translateY(0)', opacity: '1' }
            },
            pulseSoft: {
              '0%, 100%': { opacity: '1' },
              '50%': { opacity: '0.8' }
            }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    * {
      font-family: 'Inter', sans-serif;
    }

    :root {
      --glass-bg: rgba(255, 255, 255, 0.7);
      --glass-border: rgba(255, 255, 255, 0.2);
      --shadow-soft: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
      --shadow-card: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
    }

    body {
      background: linear-gradient(135deg, #f5f7fa 0%, #e4edf5 100%);
      min-height: 100vh;
    }

    .glass {
      background: var(--glass-bg);
      backdrop-filter: blur(10px);
      border: 1px solid var(--glass-border);
    }

    .card {
      background: white;
      border-radius: 16px;
      box-shadow: var(--shadow-card);
      border: 1px solid rgba(226, 232, 240, 0.8);
      transition: all 0.3s ease;
    }

    .card:hover {
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 10px 10px -5px rgba(0, 0, 0, 0.02);
      transform: translateY(-2px);
    }

    .btn {
      padding: 0.6rem 1.2rem;
      border-radius: 10px;
      font-weight: 600;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }

    .btn:active {
      transform: scale(0.98);
    }

    .input, .select, .textarea {
      width: 100%;
      padding: 0.75rem 1rem;
      border: 1px solid rgb(226, 232, 240);
      border-radius: 10px;
      background: white;
      transition: all 0.2s ease;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }

    .input:focus, .select:focus, .textarea:focus {
      border-color: rgb(14, 165, 233);
      box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
      outline: none;
    }

    .label {
      font-size: 0.8rem;
      font-weight: 600;
      color: rgb(71, 85, 105);
      margin-bottom: 0.5rem;
      display: block;
    }

    .kbd {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      background: rgb(241, 245, 249);
      border: 1px solid rgb(226, 232, 240);
      border-radius: 6px;
      padding: 0.2rem 0.4rem;
      font-size: 0.75rem;
      color: #374151 !important;
    }

    .kbd-short {
      max-width: 80px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      display: inline-block;
      vertical-align: middle;
    }

    .pill {
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.7rem;
      font-weight: 600;
      background: rgb(241, 245, 249);
      border: 1px solid rgb(226, 232, 240);
      color: #374151 !important;
    }

    .tab-btn {
      padding: 0.75rem 1.5rem;
      border-radius: 10px;
      font-weight: 600;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
      color: #64748b;
    }

    .tab-btn.active {
      background: rgba(14, 165, 233, 0.1);
      color: rgb(14, 165, 233);
    }

    .tab-btn:not(.active):hover {
      background: rgba(100, 116, 139, 0.05);
    }

    .muted {
      color: rgb(100, 116, 139);
    }

    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }

    .grid-3 {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 1rem;
    }

    .grid-aside {
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 1.5rem;
    }

    @media (max-width: 1024px) {
      .grid-aside {
        grid-template-columns: 1fr;
      }
    }

    .list {
      max-height: 420px;
      overflow: auto;
    }

    .json-invalid {
      border-color: rgb(239, 68, 68) !important;
      background: #fef2f2;
    }

    .hint {
      font-size: 0.75rem;
      color: rgb(100, 116, 139);
    }

    .header-gradient {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      position: relative;
      overflow: hidden;
    }

    .header-gradient::before {
      content: '';
      position: absolute;
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
    }

    .kpi-card {
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(10px);
      border-radius: 12px;
      padding: 1.25rem;
      border: 1px solid rgba(255, 255, 255, 0.5);
      transition: all 0.3s ease;
    }

    .kpi-card:hover {
      transform: translateY(-3px);
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
    }

    .kpi-card,
    .kpi-card *:not(i):not(input) {
      color: #1e293b !important;
    }

    .kpi-card .text-slate-600 {
      color: #475569 !important;
    }

    .status-indicator {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
      margin-right: 6px;
    }

    .status-active {
      background: #10b981;
      box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
    }

    .fade-in {
      animation: fadeIn 0.5s ease-in-out;
    }

    .slide-up {
      animation: slideUp 0.3s ease-out;
    }

    ::-webkit-scrollbar {
      width: 6px;
    }

    ::-webkit-scrollbar-track {
      background: #f1f5f9;
      border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb:hover {
      background: #94a3b8;
    }

    .loading-pulse {
      animation: pulseSoft 2s infinite;
    }

    .header-content h1,
    .header-content p,
    .header-content label {
      color: white !important;
      text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    }

    .glass .input {
      color: #1e293b !important;
    }

    .glass .btn {
      color: #1e293b !important;
    }

    .header-gradient,
    .header-gradient .header-text,
    .header-gradient label {
      color: white !important;
    }

    .header-gradient .text-slate-400 {
      color: rgba(255, 255, 255, 0.7) !important;
    }

    .header-gradient .placeholder-slate-500::placeholder {
      color: rgba(255, 255, 255, 0.6) !important;
    }

    /* Service Console specific styles */
    .json-box { 
      font-size: .8rem; 
      background: #f8fafc; 
      border: 1px solid #e2e8f0; 
      border-radius: 10px; 
      padding: .75rem; 
      overflow: auto; 
    }

    .readonly {
      background: #f8fafc !important;
      color: #64748b !important;
      pointer-events: none;
      user-select: none;
    }
  </style>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-7xl mx-auto p-4 md:p-8">
    <!-- Header with gradient -->
    <header class="header-gradient rounded-2xl p-6 md:p-8 mb-6 relative overflow-hidden fade-in">
      <div class="relative z-10">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div class="header-content">
            <div class="flex items-center gap-3 mb-2">
              <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                <i class="fas fa-cube text-white text-lg"></i>
              </div>
              <h1 class="text-3xl font-bold text-white">AuthBridge Service Console</h1>
            </div>
            <p class="opacity-95 text-sm text-white">Discover service configuration, issue tokens, and inspect JWTs.</p>
          </div>
          <div class="glass rounded-xl p-4 flex flex-col md:flex-row items-center gap-3">
            <div class="relative">
              <i class="fas fa-key absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"></i>
              <input id="svcApiKey" type="password" placeholder="Service API key"
               class="input !pl-10 !w-full md:!w-64 placeholder-slate-500 text-slate-900"
                class="input !pl-10 !w-full md:!w-64 placeholder-slate-500 text-slate-900"
                autocomplete="off"
                style="background-image:url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%2244%22><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23000000%22 fill-opacity=%220.12%22 font-size=%2220%22 font-family=%22Inter, sans-serif%22 font-weight=%22700%22 letter-spacing=%222%22>SERVICE API KEY</text></svg>');background-repeat:no-repeat;background-position:center;background-size:contain;">
            </div>
            <div class="relative">
              <i class="fas fa-id-badge absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"></i>
              <input id="svcIdInput" type="text" placeholder="Service ID"
                class="input !pl-10 !w-full md:!w-64 placeholder-slate-500 text-slate-900"
                style="background-image:url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%2244%22><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22%23000000%22 fill-opacity=%220.12%22 font-size=%2220%22 font-family=%22Inter, sans-serif%22 font-weight=%22700%22 letter-spacing=%222%22>SERVICE ID</text></svg>');background-repeat:no-repeat;background-position:center;background-size:contain;">          </div>
            <button id="saveKeyBtn" class="btn bg-white hover:bg-slate-100 text-slate-800 border border-slate-200 w-full md:w-auto">
              <i class="fas fa-sign-in-alt"></i> Use credentials
            </button>
            <button id="refreshBtn" class="btn bg-white/80 hover:bg-white text-slate-800 border border-white/30">
              <i class="fas fa-sync-alt"></i> Refresh
            </button>
          </div>
        </div>

        <!-- KPIs row -->
        <div class="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Detected Service</div>
              <i class="fas fa-cube text-primary-400"></i>
            </div>
            <div id="kSvcName" class="text-2xl font-bold mt-2 text-slate-800">–</div>
            <div id="kSvcType" class="text-xs text-slate-600 mt-1">Type: —</div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Workspaces Linked</div>
              <i class="fas fa-layer-group text-primary-400"></i>
            </div>
            <div id="kWsCount" class="text-2xl font-bold mt-2 text-slate-800">–</div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Inbound Links</div>
              <i class="fas fa-arrow-right text-primary-400"></i>
            </div>
            <div id="kInbound" class="text-2xl font-bold mt-2 text-slate-800">–</div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Outbound Links</div>
              <i class="fas fa-arrow-left text-primary-400"></i>
            </div>
            <div id="kOutbound" class="text-2xl font-bold mt-2 text-slate-800">–</div>
          </div>
        </div>
      </div>
    </header>

    <!-- Tabs -->
    <nav class="mb-6 slide-up">
      <div class="card p-2 flex flex-wrap gap-1">
        <button data-tab="discovery" class="tab-btn active">
          <i class="fas fa-compass"></i> Discovery
        </button>
        <button data-tab="tokens" class="tab-btn">
          <i class="fas fa-ticket-alt"></i> Tokens
        </button>
        <button data-tab="jwt" class="tab-btn">
          <i class="fas fa-shield-alt"></i> JWT Tools
        </button>
      </div>
    </nav>

    <!-- Panels -->
    <section class="slide-up">
      <!-- Discovery -->
      <div id="tab-discovery" class="tab-panel">
        <div class="grid-2">
          <div class="card p-5">
            <h2 class="font-bold text-lg mb-4 flex items-center gap-2">
              <i class="fas fa-circle-info text-primary-500"></i> Service
            </h2>
            <div id="svcSummary" class="text-sm">
              <div class="text-slate-500">Enter credentials above and press <span class="kbd">Use credentials</span>.</div>
            </div>
            <div class="mt-4">
              <h3 class="font-semibold text-sm mb-2">Info</h3>
              <pre id="svcInfoBox" class="json-box max-h-64">—</pre>
            </div>
            <div class="mt-4">
              <h3 class="font-semibold text-sm mb-2">Content</h3>
              <pre id="svcContentBox" class="json-box max-h-64">—</pre>
            </div>
          </div>
          <div class="card p-5">
            <h2 class="font-bold text-lg mb-4 flex items-center gap-2">
              <i class="fas fa-link text-primary-500"></i> Links
            </h2>
            <div class="grid-2">
              <div>
                <h3 class="font-semibold text-sm mb-2">Inbound (issuer ➜ <span class="kbd">service</span>)</h3>
                <div id="inboundList" class="text-sm space-y-2"></div>
              </div>
              <div>
                <h3 class="font-semibold text-sm mb-2">Outbound (<span class="kbd">service</span> ➜ audience)</h3>
                <div id="outboundList" class="text-sm space-y-2"></div>
              </div>
            </div>
            <div class="mt-4">
              <h3 class="font-semibold text-sm mb-2">Participating Workspaces</h3>
              <div id="wsListBox" class="text-sm flex flex-wrap gap-2"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tokens -->
      <div id="tab-tokens" class="tab-panel hidden">
        <div class="card p-5">
          <h2 class="font-bold text-lg mb-4 flex items-center gap-2">
            <i class="fas fa-ticket-alt text-primary-500"></i> Issue Token
          </h2>
          <div class="grid-3">
            <div>
              <label class="label">Issuer (service)</label>
              <input id="tokIssuer" class="input readonly" placeholder="issuer service id" readonly aria-readonly="true" title="Issuer is fixed by the selected Service ID above"/>
            </div>
            <div>
              <label class="label">Audience (service)</label>
              <select id="tokAudience" class="select"></select>
            </div>
            <div>
              <label class="label">Workspace (sub)</label>
              <select id="tokWorkspace" class="select"></select>
            </div>
          </div>
          <div class="grid-2 mt-4">
            <div>
              <label class="label">Context (JSON)</label>
              <textarea id="tokContext" class="textarea h-44" placeholder='{"scope":["read"],"trace":"abc"}' data-json></textarea>
              <div id="tokContextHint" class="hint mt-1 flex items-center gap-1">
                <i class="fas fa-code"></i> <span>JSON • valid</span>
              </div>
            </div>
            <div>
              <label class="label">Issued JWT</label>
              <textarea id="tokResult" class="textarea h-44" readonly placeholder="The issued token will appear here…"></textarea>
            </div>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button id="issueBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
              <i class="fas fa-paper-plane"></i> Issue
            </button>
            <button id="clearIssueBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800">
              <i class="fas fa-eraser"></i> Clear
            </button>
          </div>
          <div class="mt-3">
            <label class="label">Response</label>
            <pre id="tokLog" class="json-box max-h-48">—</pre>
          </div>
        </div>
      </div>

      <!-- JWT Tools -->
      <div id="tab-jwt" class="tab-panel hidden">
        <div class="card p-5">
          <h2 class="font-bold text-lg mb-4 flex items-center gap-2">
            <i class="fas fa-shield-alt text-primary-500"></i> Validate & Decode
          </h2>
          <div>
            <label class="label">Paste JWT</label>
            <textarea id="jwtInput" class="textarea h-32" placeholder="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...."></textarea>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button id="validateBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
              <i class="fas fa-check-circle"></i> Validate (server)
            </button>
            <button id="decodeBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800">
              <i class="fas fa-code"></i> Decode (client)
            </button>
            <button id="clearJwtBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800">
              <i class="fas fa-eraser"></i> Clear
            </button>
          </div>
          <div class="grid-2 mt-4">
            <div>
              <h3 class="font-semibold text-sm mb-2">Header</h3>
              <pre id="jwtHeader" class="json-box max-h-48">—</pre>
            </div>
            <div>
              <h3 class="font-semibold text-sm mb-2">Payload</h3>
              <pre id="jwtPayload" class="json-box max-h-48">—</pre>
            </div>
          </div>
          <div class="mt-4">
            <h3 class="font-semibold text-sm mb-2">Validation Result</h3>
            <pre id="jwtValidation" class="json-box max-h-56">—</pre>
          </div>
        </div>
      </div>
    </section>

    <footer class="mt-8 text-center text-xs text-slate-500">
      <div class="flex items-center justify-center gap-2 mb-2">
        <i class="fas fa-key text-primary-500"></i>
        <span>Works with a service API key • Calls public API endpoints with <span class="kbd">x-api-key</span></span>
      </div>
    </footer>
  </div>

<script>
(function(){
  // ======= Tabs =======
  const tabs = document.querySelectorAll(".tab-btn");
  const panels = {
    discovery: document.getElementById("tab-discovery"),
    tokens: document.getElementById("tab-tokens"),
    jwt: document.getElementById("tab-jwt"),
  };
  function activateTab(name){
    tabs.forEach(b => b.classList.toggle("active", b.dataset.tab === name));
    Object.entries(panels).forEach(([k,el]) => el.classList.toggle("hidden", k !== name));
  }
  tabs.forEach(b => b.addEventListener("click", () => activateTab(b.dataset.tab)));
  activateTab("discovery");

  // ======= Elements & state =======
  const svcApiKey = document.getElementById("svcApiKey");
  const svcIdInput = document.getElementById("svcIdInput");
  const saveKeyBtn = document.getElementById("saveKeyBtn");
  const refreshBtn = document.getElementById("refreshBtn");

  const kSvcName = document.getElementById("kSvcName");
  const kSvcType = document.getElementById("kSvcType");
  const kWsCount = document.getElementById("kWsCount");
  const kInbound = document.getElementById("kInbound");
  const kOutbound = document.getElementById("kOutbound");

  const svcSummary = document.getElementById("svcSummary");
  const svcInfoBox = document.getElementById("svcInfoBox");
  const svcContentBox = document.getElementById("svcContentBox");
  const inboundList = document.getElementById("inboundList");
  const outboundList = document.getElementById("outboundList");
  const wsListBox = document.getElementById("wsListBox");

  // Tokens tab
  const tokIssuer = document.getElementById("tokIssuer");
  const tokAudience = document.getElementById("tokAudience");
  const tokWorkspace = document.getElementById("tokWorkspace");
  const tokTtl = document.getElementById("tokTtl");
  const tokContext = document.getElementById("tokContext");
  const tokContextHint = document.getElementById("tokContextHint");
  const issueBtn = document.getElementById("issueBtn");
  const clearIssueBtn = document.getElementById("clearIssueBtn");
  const tokResult = document.getElementById("tokResult");
  const tokLog = document.getElementById("tokLog");

  // JWT tab
  const jwtInput = document.getElementById("jwtInput");
  const validateBtn = document.getElementById("validateBtn");
  const decodeBtn = document.getElementById("decodeBtn");
  const clearJwtBtn = document.getElementById("clearJwtBtn");
  const jwtHeader = document.getElementById("jwtHeader");
  const jwtPayload = document.getElementById("jwtPayload");
  const jwtValidation = document.getElementById("jwtValidation");

  const KEY_STORAGE = "authbridge_service_key";
  const SVCID_STORAGE = "authbridge_service_id";
  let snapshot = { services: [], workspaces: [], links: [], types: [], system: {} };

  // Persisted
  const savedKey = localStorage.getItem(KEY_STORAGE);
  const savedSvcId = localStorage.getItem(SVCID_STORAGE);
  if (savedKey) svcApiKey.value = savedKey;
  if (savedSvcId) svcIdInput.value = savedSvcId;

  function headers(extra){
    return Object.assign({"x-api-key": (svcApiKey.value||"").trim(), "accept":"application/json"}, extra || {});
  }

  // JSON helpers and validation
  function parseJSONOrEmpty(txt){ if(!txt || !txt.trim()) return {}; return JSON.parse(txt); }
  function tryParse(txt){ try { parseJSONOrEmpty(txt); return {ok:true, msg:"JSON • valid"} } catch(e){ return {ok:false, msg:e.message} }
  }
  function attachJsonLiveValidation(textarea, hintEl){
    const apply = ()=>{
      const {ok, msg} = tryParse(textarea.value);
      textarea.classList.toggle("json-invalid", !ok);
      if (hintEl) {
        hintEl.innerHTML = `<i class="fas fa-code"></i> <span>${ok ? "JSON • valid" : ("Invalid JSON: " + msg)}</span>`;
        hintEl.style.color = ok ? "" : "rgb(239 68 68)";
      }
    };
    apply();
    textarea.addEventListener("input", apply);
  }
  attachJsonLiveValidation(tokContext, tokContextHint);

  // Populate select helper
  function setSelectOptions(sel, arr, get){
    sel.replaceChildren();
    arr.forEach(o=>{
      const {value,label} = get ? get(o) : {value:o.id, label:o.name || o.id};
      const opt = document.createElement("option");
      opt.value = value; opt.textContent = label;
      sel.appendChild(opt);
    });
  }

  function formatJSON(obj){
    try { return JSON.stringify(obj, null, 2); } catch { return String(obj); }
  }

  function renderDiscovery(serviceId){
    const svc = snapshot.services.find(s => s.id === serviceId);
    const allLinks = snapshot.links || [];
    const inbound = allLinks.filter(l => l.audience_id === serviceId);
    const outbound = allLinks.filter(l => l.issuer_id === serviceId);

    // KPIs
    kSvcName.textContent = svc ? (svc.name || svc.id) : "Not found";
    kSvcType.textContent = "Type: " + (svc ? (svc.type || "unknown") : "—");
    kInbound.textContent = inbound.length;
    kOutbound.textContent = outbound.length;

    const wsIds = new Set([...inbound, ...outbound].map(l => l.workspace_id));
    kWsCount.textContent = wsIds.size;

    // Summary
    svcSummary.innerHTML = svc ? `
      <div class="text-sm">
        <div><span class="pill">${svc.type}</span> • <span class="kbd">id</span> ${svc.id} • <span class="kbd">ver</span> ${svc.version}</div>
      </div>
    ` : '<div class="text-slate-500">Service not found with provided credentials.</div>';

    svcInfoBox.textContent = svc ? formatJSON(svc.info || {}) : "—";
    svcContentBox.textContent = svc ? formatJSON(svc.content || {}) : "—";

    // Links
    inboundList.replaceChildren();
    outboundList.replaceChildren();
    function linkRow(l){
      const i = snapshot.services.find(s=>s.id===l.issuer_id);
      const a = snapshot.services.find(s=>s.id===l.audience_id);
      const el = document.createElement("div");
      el.className = "p-2 rounded border border-slate-200";
      el.innerHTML = `<div class="font-medium">${i?.name || l.issuer_id} ➜ ${a?.name || l.audience_id}</div>
      <div class="text-[11px] text-slate-500">ws: ${l.workspace_id}</div>`;
      el.addEventListener("click", ()=>{
        alert(JSON.stringify(l.context || {}, null, 2));
      });
      return el;
    }
    inbound.forEach(l => inboundList.appendChild(linkRow(l)));
    outbound.forEach(l => outboundList.appendChild(linkRow(l)));

    wsListBox.replaceChildren();
    if (wsIds.size === 0) {
      const t = document.createElement("div");
      t.className = "text-slate-500"; t.textContent = "No workspaces.";
      wsListBox.appendChild(t);
    } else {
      [...wsIds].forEach(id=>{
        const w = snapshot.workspaces.find(x=>x.id===id);
        const b = document.createElement("span");
        b.className = "pill";
        b.textContent = (w?.name || id);
        wsListBox.appendChild(b);
      });
    }

    // Tokens tab defaults (issuer fixed & read-only)
    tokIssuer.value = serviceId || "";
    tokIssuer.readOnly = true;
    tokIssuer.classList.add("readonly");

    // Audience: only linked audiences from this service's outbound links; exclude itself
    const linkedAudienceIds = Array.from(new Set(outbound.map(l => l.audience_id))).filter(id => id && id !== serviceId);
    const linkedAudienceObjs = linkedAudienceIds
      .map(id => snapshot.services.find(s => s.id === id))
      .filter(Boolean);
    setSelectOptions(tokAudience, linkedAudienceObjs, s=>({value:s.id,label:`${s.name} (${s.type})`}));

    // Workspace: only workspaces where this service has outbound links (has access)
    const outWsIds = Array.from(new Set(outbound.map(l => l.workspace_id)));
    const outWsObjs = outWsIds.map(id => {
      const w = snapshot.workspaces.find(x => x.id === id);
      return { id, name: (w && w.name) ? w.name : id };
    });
    setSelectOptions(tokWorkspace, outWsObjs, w=>({value:w.id, label:w.name}));
  }

  function fetchSnapshot(onDone){
    fetch("/bridge/data", { headers: headers() })
      .then(r=>{ if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
      .then(d => { snapshot = d; onDone && onDone(); })
      .catch(e => {
        svcSummary.innerHTML = '<div class="text-rose-600">Failed to fetch data. Check API key.</div>';
        console.error(e);
      });
  }

  // Credential actions
  saveKeyBtn.addEventListener("click", ()=>{
    const key = (svcApiKey.value||"").trim();
    const id = (svcIdInput.value||"").trim();
    if (!key || !id) { alert("Enter both Service API key and Service ID."); return; }
    localStorage.setItem(KEY_STORAGE, key);
    localStorage.setItem(SVCID_STORAGE, id);
    fetchSnapshot(()=> renderDiscovery(id));
  });

  refreshBtn.addEventListener("click", ()=>{
    const id = (svcIdInput.value||"").trim();
    if (!id) { alert("Enter a Service ID first."); return; }
    fetchSnapshot(()=> renderDiscovery(id));
  });

  // ======= Tokens actions =======
  function post(path, data){
    return fetch(path, {
      method: "POST",
      headers: headers({"content-type":"application/json"}),
      body: data ? JSON.stringify(data) : null
    }).then(async r=>{
      const txt = await r.text();
      const payload = (txt && txt.startsWith("{")) ? JSON.parse(txt) : {raw:txt};
      if (!r.ok) throw new Error((payload && payload.detail && (payload.detail.message || payload.detail.error_code)) || ("HTTP "+r.status));
      return payload;
    });
  }

  issueBtn.addEventListener("click", () => {
    try {
      const ctx = parseJSONOrEmpty(tokContext.value);

      // Issuer is locked to the selected service id (never trust the readonly input value)
      const issuerId = (svcIdInput.value || "").trim();
      if (!issuerId) {
        tokLog.textContent = "Issuer (Service ID) is required. Enter it at the top and press Use credentials.";
        return;
      }

      // Build payload: workspace comes from dropdown; keep context as claims.
      const payload = {
        aud: (tokAudience.value || "").trim(),
        sub: (tokWorkspace.value || "").trim(),
        claims: ctx && typeof ctx === "object" ? ctx : {}
      };

      // Ensure required fields
      if (!payload.aud) {
        tokLog.textContent = "Audience (service) is required.";
        return;
      }
      if (!payload.sub) {
        tokLog.textContent = "Workspace (sub) is required. Select it from the dropdown.";
        return;
      }

      (async () => {
        const ep = `/api/v1/token/${encodeURIComponent(issuerId)}/issue`;
        const res = await post(ep, payload);

        tokLog.textContent = JSON.stringify(res, null, 2);
        const token =
          res.access_token ||
          res.token ||
          (res.data && res.data.token) ||
          "";
        tokResult.value = token || "";
      })().catch((e) => {
        tokLog.textContent = "Error: " + e.message;
        tokResult.value = "";
      });
    } catch (e) {
      tokLog.textContent = "Invalid context JSON: " + e.message;
    }
  });

  clearIssueBtn.addEventListener("click", ()=>{
    tokContext.value = "";
    tokResult.value = "";
    tokLog.textContent = "—";
    tokContext.dispatchEvent(new Event("input"));
  });

  // ======= JWT tools =======
  function b64urlDecodeToString(b64url){
    const b64 = b64url.replace(/-/g,'+').replace(/_/g,'/');
    const pad = b64.length % 4 ? 4 - (b64.length % 4) : 0;
    const b64p = b64 + "=".repeat(pad);
    try {
      return decodeURIComponent(escape(atob(b64p)));
    } catch {
      return atob(b64p);
    }
  }
  function decodeJwtLocally(token){
    if (!token || token.split(".").length < 2) throw new Error("Not a JWT");
    const [h,p] = token.split(".");
    const header = JSON.parse(b64urlDecodeToString(h));
    const payload = JSON.parse(b64urlDecodeToString(p));
    return {header, payload};
  }

  decodeBtn.addEventListener("click", ()=>{
    try {
      const token = (jwtInput.value||"").trim();
      const {header, payload} = decodeJwtLocally(token);
      jwtHeader.textContent = JSON.stringify(header, null, 2);
      jwtPayload.textContent = JSON.stringify(payload, null, 2);
      jwtValidation.textContent = "—";
    } catch(e){
      jwtHeader.textContent = "—";
      jwtPayload.textContent = "—";
      jwtValidation.textContent = "Decode error: " + e.message;
    }
  });

  validateBtn.addEventListener("click", ()=>{
    const token = (jwtInput.value||"").trim();
    if (!token) { jwtValidation.textContent = "Paste a token first."; return; }
    (async () => {
      const payload = { token };
      const endpoints = ["/api/v1/token/verify", "/api/v1/token/introspect"];
      let res = null, lastErr = null;
      for (const ep of endpoints){
        try { res = await post(ep, payload); break; } catch(e){ lastErr = e; }
      }
      if (!res) throw lastErr || new Error("No validation endpoint available");
      jwtValidation.textContent = JSON.stringify(res, null, 2);
      try {
        const {header, payload:pl} = decodeJwtLocally(token);
        jwtHeader.textContent = JSON.stringify(header, null, 2);
        jwtPayload.textContent = JSON.stringify(pl, null, 2);
      } catch {}
    })().catch(e => { jwtValidation.textContent = "Validation error: " + e.message; });
  });

  clearJwtBtn.addEventListener("click", ()=>{
    jwtInput.value = "";
    jwtHeader.textContent = "—";
    jwtPayload.textContent = "—";
    jwtValidation.textContent = "—";
  });

  // Auto-init if saved
  if (savedKey && savedSvcId) {
    fetchSnapshot(()=> renderDiscovery(savedSvcId));
  }
})();
</script>
</body>
</html>
"""


@router.get("/bridge", response_class=HTMLResponse, include_in_schema=False)
async def service_console_page() -> HTMLResponse:
    """
    Service-facing console with 3 tabs:
      - Discovery (shows info, content, links for a specific service ID)
      - Tokens (issue tokens with JSON context validation)
      - JWT Tools (server validation + client-side decode)
    Uses the provided API key via x-api-key.
    """
    return HTMLResponse(SERVICE_CONSOLE_HTML)


@router.get("/bridge/data", response_class=JSONResponse, include_in_schema=False)
async def service_console_data(_: str = Depends(validate_service_api_key)) -> JSONResponse:
    """
    Aggregated snapshot (services, workspaces, links, types) for the service bridge.
    Requires a valid *service* API key in `x-api-key`. The console filters by the provided service ID on the client.
    """
    await reload_services()
    await reload_workspaces()

    # Services
    services: List[Dict[str, Any]] = []
    for s in caches.services.values():
        services.append(
            {
                "id": s.id,
                "name": s.name,
                "type": s.type or "unknown",
                "version": s.version,
                "info": s.info or {},
                "content": s.content or {},
            }
        )

    # Workspaces & links
    workspaces: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    for w in caches.workspaces.values():
        workspaces.append(
            {
                "id": w.id,
                "name": w.name,
                "version": w.version,
                "info": w.info or {},
            }
        )
        for link in (w.services or []):
            if isinstance(link, ServiceLink):
                links.append(
                    {
                        "workspace_id": w.id,
                        "issuer_id": link.issuer_id,
                        "audience_id": link.audience_id,
                        "context": link.context or {},
                    }
                )

    types = sorted(set(load_service_types()) | set([s["type"] for s in services]))

    payload = {
        "now": datetime.now(timezone.utc).isoformat(),
        "system": {
            "services_version": caches.service_sys_ver,
            "workspaces_version": caches.workspace_sys_ver,
        },
        "services": sorted(services, key=lambda x: (str(x["type"]).lower(), str(x["name"]).lower())),
        "workspaces": sorted(workspaces, key=lambda x: str(x["name"]).lower()),
        "links": links,
        "types": types,
    }
    return JSONResponse(payload)


@router.get("/bridge/ready", response_class=PlainTextResponse, include_in_schema=False)
async def service_console_ready() -> PlainTextResponse:
    """Simple readiness ping for this UI."""
    return PlainTextResponse("ok")
