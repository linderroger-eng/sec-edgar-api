"""
SEC EDGAR API — Clean REST wrapper for SEC EDGAR data
Endpoints: /filings, /insider-trades, /company-facts, /ticker-lookup, /health, /ping
"""
import os
import time
import json
import httpx
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(
    title="SEC EDGAR API",
    description="Clean REST API for SEC filings, insider trades, and company financials. Data from SEC EDGAR.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── constants ──────────────────────────────────────────────────────────────
SEC_BASE = "https://data.sec.gov"
SEC_HEADERS = {"User-Agent": "SEC-EDGAR-API contact@government-data-api.onrender.com"}
DB_PATH = os.getenv("DATABASE_URL", "/tmp/sec_edgar.db").replace("sqlite:///", "")
TICKER_CACHE_TTL = 86400  # 24h
FILING_CACHE_TTL = 3600   # 1h

# ── api key / rate limiting ────────────────────────────────────────────────
DAILY_LIMITS = {"free": 100, "starter": 1000, "pro": 10000, "enterprise": 999999}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            api_key TEXT PRIMARY KEY,
            tier TEXT DEFAULT 'free',
            request_count INTEGER DEFAULT 0,
            last_reset TEXT DEFAULT (date('now')),
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS ticker_cache (
            ticker TEXT PRIMARY KEY,
            cik TEXT NOT NULL,
            name TEXT,
            cached_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS filing_cache (
            cache_key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            cached_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

init_db()

async def check_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Add header: X-API-Key: <your-key>. Get a free key at https://rapidapi.com"
        )
    conn = get_db()
    row = conn.execute("SELECT * FROM api_keys WHERE api_key = ?", (x_api_key,)).fetchone()
    if not row:
        # Auto-register as free tier
        conn.execute("INSERT INTO api_keys (api_key, tier) VALUES (?, 'free')", (x_api_key,))
        conn.commit()
        row = conn.execute("SELECT * FROM api_keys WHERE api_key = ?", (x_api_key,)).fetchone()

    # Reset daily counter if new day
    today = datetime.now().strftime("%Y-%m-%d")
    if row["last_reset"] != today:
        conn.execute("UPDATE api_keys SET request_count = 0, last_reset = ? WHERE api_key = ?", (today, x_api_key))
        conn.commit()
        row = conn.execute("SELECT * FROM api_keys WHERE api_key = ?", (x_api_key,)).fetchone()

    limit = DAILY_LIMITS.get(row["tier"], 100)
    if row["request_count"] >= limit:
        conn.close()
        raise HTTPException(status_code=429, detail=f"Daily limit reached ({limit} req/day on {row['tier']} tier). Upgrade at https://rapidapi.com")

    conn.execute("UPDATE api_keys SET request_count = request_count + 1 WHERE api_key = ?", (x_api_key,))
    conn.commit()
    conn.close()
    return x_api_key

async def ticker_to_cik(ticker: str) -> dict:
    """Resolve ticker → CIK using SEC company_tickers.json (cached 24h)"""
    ticker = ticker.upper()
    conn = get_db()

    # Check cache
    row = conn.execute("SELECT cik, name FROM ticker_cache WHERE ticker = ?", (ticker,)).fetchone()
    if row:
        conn.close()
        return {"cik": row["cik"], "name": row["name"]}

    # Fetch from SEC
    async with httpx.AsyncClient(headers=SEC_HEADERS, timeout=15) as client:
        resp = await client.get("https://www.sec.gov/files/company_tickers.json")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not fetch ticker data from SEC")
        data = resp.json()

    # Find ticker
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker:
            cik = str(entry["cik_str"]).zfill(10)
            name = entry.get("title", "")
            conn.execute(
                "INSERT OR REPLACE INTO ticker_cache (ticker, cik, name) VALUES (?, ?, ?)",
                (ticker, cik, name)
            )
            conn.commit()
            conn.close()
            return {"cik": cik, "name": name}

    conn.close()
    raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in SEC database")

# ── endpoints ─────────────────────────────────────────────────────────────

@app.get("/ping")
async def ping():
    return {"status": "ok"}

@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(headers=SEC_HEADERS, timeout=10) as client:
            resp = await client.get("https://www.sec.gov/files/company_tickers.json")
            sec_ok = resp.status_code == 200
    except Exception:
        sec_ok = False
    return {
        "status": "healthy" if sec_ok else "degraded",
        "sec_edgar": "up" if sec_ok else "down",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/ticker-lookup")
async def ticker_lookup(
    ticker: str = Query(..., description="Stock ticker symbol (e.g. AAPL, TSLA, MSFT)"),
    x_api_key: str = Header(None)
):
    """Resolve a ticker symbol to SEC CIK and company name."""
    await check_api_key(x_api_key)
    result = await ticker_to_cik(ticker)
    return {"ticker": ticker.upper(), "cik": result["cik"], "company_name": result["name"], "source": "SEC EDGAR"}

@app.get("/filings")
async def get_filings(
    ticker: str = Query(..., description="Stock ticker symbol (e.g. AAPL, TSLA)"),
    form_type: Optional[str] = Query(None, description="Filter by form type: 10-K, 10-Q, 8-K, 4, etc."),
    limit: int = Query(10, ge=1, le=50, description="Number of results (max 50)"),
    x_api_key: str = Header(None)
):
    """Get recent SEC filings for a company by ticker symbol."""
    await check_api_key(x_api_key)
    company = await ticker_to_cik(ticker)
    cik = company["cik"]

    cache_key = f"filings_{cik}_{form_type}_{limit}"
    conn = get_db()
    cached = conn.execute("SELECT data, cached_at FROM filing_cache WHERE cache_key = ?", (cache_key,)).fetchone()
    if cached:
        age = (datetime.now() - datetime.fromisoformat(cached["cached_at"])).seconds
        if age < FILING_CACHE_TTL:
            conn.close()
            return json.loads(cached["data"])
    conn.close()

    async with httpx.AsyncClient(headers=SEC_HEADERS, timeout=20) as client:
        resp = await client.get(f"{SEC_BASE}/submissions/CIK{cik}.json")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not fetch filings from SEC EDGAR")
        data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    descriptions = recent.get("primaryDocument", [])

    filings = []
    for i, form in enumerate(forms):
        if form_type and form.upper() != form_type.upper():
            continue
        accession = accessions[i].replace("-", "") if i < len(accessions) else ""
        doc = descriptions[i] if i < len(descriptions) else ""
        filings.append({
            "form_type": form,
            "filing_date": dates[i] if i < len(dates) else "",
            "accession_number": accessions[i] if i < len(accessions) else "",
            "document_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{doc}" if accession and doc else None,
            "index_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=40"
        })
        if len(filings) >= limit:
            break

    result = {
        "ticker": ticker.upper(),
        "company": company["name"],
        "cik": cik,
        "count": len(filings),
        "filings": filings,
        "source": "SEC EDGAR"
    }

    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO filing_cache (cache_key, data) VALUES (?, ?)",
        (cache_key, json.dumps(result))
    )
    conn.commit()
    conn.close()
    return result

@app.get("/company-facts")
async def company_facts(
    ticker: str = Query(..., description="Stock ticker symbol (e.g. AAPL, TSLA)"),
    concept: Optional[str] = Query(None, description="Specific XBRL concept (e.g. Revenues, NetIncomeLoss, Assets)"),
    x_api_key: str = Header(None)
):
    """Get financial facts (revenue, earnings, assets) for a company from SEC XBRL data."""
    await check_api_key(x_api_key)
    company = await ticker_to_cik(ticker)
    cik = company["cik"]

    async with httpx.AsyncClient(headers=SEC_HEADERS, timeout=30) as client:
        resp = await client.get(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not fetch company facts from SEC EDGAR")
        data = resp.json()

    us_gaap = data.get("facts", {}).get("us-gaap", {})

    if concept:
        # Return specific concept
        if concept not in us_gaap:
            available = list(us_gaap.keys())[:20]
            raise HTTPException(
                status_code=404,
                detail=f"Concept '{concept}' not found. Available concepts (first 20): {available}"
            )
        concept_data = us_gaap[concept]
        units = concept_data.get("units", {})
        # Get most recent values
        all_values = []
        for unit_type, entries in units.items():
            for entry in entries[-10:]:  # last 10 periods
                all_values.append({
                    "value": entry.get("val"),
                    "unit": unit_type,
                    "period_start": entry.get("start"),
                    "period_end": entry.get("end"),
                    "form": entry.get("form"),
                    "filed": entry.get("filed")
                })
        return {
            "ticker": ticker.upper(),
            "company": company["name"],
            "concept": concept,
            "label": concept_data.get("label", concept),
            "description": concept_data.get("description", ""),
            "recent_values": sorted(all_values, key=lambda x: x.get("filed", ""), reverse=True)[:10],
            "source": "SEC EDGAR XBRL"
        }

    # Return summary of available concepts
    summary = []
    key_concepts = ["Revenues", "NetIncomeLoss", "Assets", "Liabilities", "StockholdersEquity",
                    "EarningsPerShareBasic", "OperatingIncomeLoss", "CashAndCashEquivalentsAtCarryingValue"]
    for c in key_concepts:
        if c in us_gaap:
            units = us_gaap[c].get("units", {})
            latest = None
            for unit_type, entries in units.items():
                if entries:
                    e = entries[-1]
                    latest = {"value": e.get("val"), "unit": unit_type, "period_end": e.get("end"), "form": e.get("form")}
            summary.append({"concept": c, "label": us_gaap[c].get("label", c), "latest": latest})

    return {
        "ticker": ticker.upper(),
        "company": company["name"],
        "cik": cik,
        "total_concepts": len(us_gaap),
        "key_financials": summary,
        "all_concepts": list(us_gaap.keys()),
        "source": "SEC EDGAR XBRL"
    }

@app.get("/insider-trades")
async def insider_trades(
    ticker: str = Query(..., description="Stock ticker symbol (e.g. AAPL, TSLA)"),
    limit: int = Query(10, ge=1, le=50, description="Number of results (max 50)"),
    x_api_key: str = Header(None)
):
    """Get recent insider trading (Form 4) filings for a company."""
    await check_api_key(x_api_key)
    company = await ticker_to_cik(ticker)
    cik = company["cik"]

    async with httpx.AsyncClient(headers=SEC_HEADERS, timeout=20) as client:
        resp = await client.get(f"{SEC_BASE}/submissions/CIK{cik}.json")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not fetch data from SEC EDGAR")
        data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    reporters = recent.get("reporterName", []) if "reporterName" in recent else []

    trades = []
    for i, form in enumerate(forms):
        if form not in ("4", "4/A"):
            continue
        trades.append({
            "form_type": form,
            "filing_date": dates[i] if i < len(dates) else "",
            "accession_number": accessions[i] if i < len(accessions) else "",
            "reporter": reporters[i] if i < len(reporters) else "See filing",
            "filing_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=40"
        })
        if len(trades) >= limit:
            break

    return {
        "ticker": ticker.upper(),
        "company": company["name"],
        "cik": cik,
        "count": len(trades),
        "insider_trades": trades,
        "note": "For full transaction details (shares, price, buy/sell), fetch the individual filing document.",
        "source": "SEC EDGAR Form 4"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
