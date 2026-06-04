# SEC EDGAR API

Clean REST API for SEC filings, insider trades, and company financials.

**Live API:** https://sec-edgar-api.onrender.com  
**Docs:** https://sec-edgar-api.onrender.com/docs

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /ticker-lookup?ticker=AAPL` | Resolve ticker to SEC CIK |
| `GET /filings?ticker=AAPL&form_type=10-K` | Recent SEC filings |
| `GET /company-facts?ticker=AAPL&concept=Revenues` | Financial data from XBRL |
| `GET /insider-trades?ticker=TSLA` | Form 4 insider transactions |
| `GET /health` | API health check |
| `GET /ping` | Keep-alive ping |

## Authentication

Add `X-API-Key: <your-key>` header. Free keys auto-register on first use.

## Data Source

All data from [SEC EDGAR](https://www.sec.gov/developer) — official US Securities and Exchange Commission data.
