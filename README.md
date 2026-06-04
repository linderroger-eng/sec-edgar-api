# SEC EDGAR API

![Build Status](https://img.shields.io/badge/build-passing-brightgreen) ![Version](https://img.shields.io/badge/version-1.0.0-blue) ![License](https://img.shields.io/badge/license-MIT-green) [![RapidAPI](https://img.shields.io/badge/RapidAPI-Subscribe-orange?logo=rapid)](https://rapidapi.com/linderroger-eng/api/sec-edgar-api1)

**Real-time SEC EDGAR data API — query filings, insider trades, company facts, and ticker lookups for any public company.**

## ✨ Key Features

- 🔍 **Instant Ticker Lookup** — Resolve any stock ticker to its full SEC CIK and company profile
- 📄 **Full Filing History** — Retrieve 10-K, 10-Q, 8-K, and all SEC form types with date filters
- 💰 **Insider Trading Data** — Live Form 4 filings: who's buying and selling executive shares
- 📊 **Structured Company Facts** — XBRL-parsed financial data (revenue, EPS, assets) ready for analysis

## 🚀 Quick Start

```bash
# 1. Health check — verify the API is live
curl -s https://sec-edgar-api-0nxw.onrender.com/health

# 2. Look up a company by ticker
curl -s "https://sec-edgar-api-0nxw.onrender.com/ticker-lookup?ticker=AAPL"

# 3. Get Tesla's 10-K annual filings
curl -s "https://sec-edgar-api-0nxw.onrender.com/filings?ticker=TSLA&form_type=10-K"

# 4. Fetch insider trades for NVIDIA
curl -s "https://sec-edgar-api-0nxw.onrender.com/insider-trades?ticker=NVDA"
```

> **With RapidAPI key** — add `-H "X-RapidAPI-Key: YOUR_KEY"` to each request.

## 📡 All Endpoints

| Method | Path | Description | Example Params |
|--------|------|-------------|----------------|
| GET | `/health` | API status and uptime check | — |
| GET | `/ticker-lookup` | Resolve ticker → CIK + company name | `?ticker=AAPL` |
| GET | `/filings` | List SEC filings by ticker and form type | `?ticker=TSLA&form_type=10-K` |
| GET | `/company-facts` | XBRL financial facts for a company | `?ticker=MSFT` |
| GET | `/insider-trades` | Recent Form 4 insider transactions | `?ticker=NVDA` |

> **Note:** All endpoints return JSON. Dates are ISO 8601 format. Pagination supported via `offset` and `limit` params.

## 🐍 Python Example

```python
import requests

BASE_URL = "https://sec-edgar-api-0nxw.onrender.com"
HEADERS = {"X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY"}

# Look up Apple's SEC profile
lookup = requests.get(f"{BASE_URL}/ticker-lookup", params={"ticker": "AAPL"}, headers=HEADERS)
print("Company:", lookup.json())

# Get the last 5 annual reports for Tesla
filings = requests.get(
    f"{BASE_URL}/filings",
    params={"ticker": "TSLA", "form_type": "10-K"},
    headers=HEADERS
)
for f in filings.json()[:5]:
    print(f["form"], f["filed"], f.get("primaryDocument", ""))

# Insider trades for NVIDIA
trades = requests.get(f"{BASE_URL}/insider-trades", params={"ticker": "NVDA"}, headers=HEADERS)
print("Recent insider trades:", trades.json()[:3])
```

## 💳 Pricing Tiers

| Plan | Price | Requests / Month | Features |
|------|-------|-----------------|----------|
| **BASIC** | Free | 100 | All endpoints, no credit card |
| **PRO** | $9 / mo | 1,000 | Higher limits, priority support |
| **ULTRA** | $29 / mo | 10,000 | Bulk queries, low latency |
| **MEGA** | $99 / mo | 100,000 | Enterprise scale, SLA guarantee |

## 🔗 RapidAPI Listing

Subscribe and manage your API key at:
👉 **[https://rapidapi.com/linderroger-eng/api/sec-edgar-api1](https://rapidapi.com/linderroger-eng/api/sec-edgar-api1)**

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push and open a Pull Request

Bug reports and feature requests are welcome via [GitHub Issues](https://github.com/linderroger-eng/sec-edgar-api/issues).

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ by [linderroger-eng](https://github.com/linderroger-eng) · Powered by SEC EDGAR public data*
