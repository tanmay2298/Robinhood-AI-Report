# Privacy, Data Usage & FAQ

This document answers common questions about how the Robinhood Portfolio Report Generator handles your data, why specific APIs are used, what things cost, and what security practices are in place.

---

## Table of Contents

1. [Data Privacy Overview](#1-data-privacy-overview)
2. [What Data Is Collected?](#2-what-data-is-collected)
3. [What Data Leaves Your Machine?](#3-what-data-leaves-your-machine)
4. [What Data Is Stored?](#4-what-data-is-stored)
5. [Why Is Each API Used?](#5-why-is-each-api-used)
6. [API Costs](#6-api-costs)
7. [Credential Security](#7-credential-security)
8. [Robinhood Authentication](#8-robinhood-authentication)
9. [AI Analysis — What Does Claude Receive?](#9-ai-analysis--what-does-claude-receive)
10. [Email Privacy](#10-email-privacy)
11. [No Tracking, No Telemetry](#11-no-tracking-no-telemetry)
12. [Third-Party Terms of Service](#12-third-party-terms-of-service)
13. [Risk Disclaimers](#13-risk-disclaimers)

---

## 1. Data Privacy Overview

This is a **local, self-hosted tool**. There is no central server, no account to create, and no data collected by the tool's author. When you run it:

- Your credentials are read from environment variables on your own machine.
- Your portfolio data is fetched directly from Robinhood's servers to your machine.
- A subset of that data (holdings list, P&L figures, news snippets) is sent to third-party AI/search APIs to generate the report.
- The final PDF is saved locally on your machine.
- No data is sent anywhere else unless you explicitly configure email delivery.

---

## 2. What Data Is Collected?

The tool reads the following from your Robinhood account via the `robin_stocks` library:

| Data | Used For |
|---|---|
| Holdings (ticker, shares, avg cost, current price, equity) | Building the prompt for Claude, generating charts, holdings table in the PDF |
| Portfolio profile (total equity, previous close value) | KPI cards in the PDF, P&L calculations |
| Bank transfer history (deposit/withdrawal amounts) | Calculating your true all-time P&L (total invested vs current value) |

No personally identifiable information beyond what is required to authenticate with Robinhood is accessed or stored.

---

## 3. What Data Leaves Your Machine?

Data is sent to three external services:

### Anthropic (Claude AI)
**What is sent:** A text prompt containing:
- Your list of stock tickers and company names
- Share quantities, average cost basis, current prices, market values, and P&L figures
- Your total portfolio value and total P&L
- News snippets fetched by Tavily (see below)
- Today's date

**What is NOT sent:** Your name, Robinhood account ID, email address, Social Security Number, bank account details, or any other personal identifying information. Only financial position data is included.

### Tavily (Web Search)
**What is sent:** Search queries constructed from your ticker symbols and company names, for example:
- `"Apple AAPL stock news this week"`
- `"stock market news this week S&P 500 Fed interest rates"`

**What is NOT sent:** Any financial figures, quantities, cost basis, or portfolio values. Tavily only receives the names of the companies you hold stock in.

### Your Email SMTP Server (Optional)
**What is sent:** The generated PDF report as an email attachment, routed through whichever SMTP server you configure (default: Gmail). This is only active if you set `EMAIL_SENDER` and `EMAIL_PASSWORD`.

---

## 4. What Data Is Stored?

| Location | What Is Stored | Retention |
|---|---|---|
| `Portfolio_Reports/` directory | Generated PDF reports, one file per run | Permanent, until you delete them |
| Your shell profile (`~/.zshrc`) | API keys and credentials as environment variables | Until you remove them |
| Robinhood session cache | An authentication token stored by `robin_stocks` in `~/.tokens/` | Until it expires or you delete it |
| macOS logs (if scheduler is used) | stdout/stderr from each run | Permanent, until you delete the log files |

No database is created. No user data is written anywhere outside these locations.

---

## 5. Why Is Each API Used?

### `robin_stocks` — Robinhood Portfolio Data
**Why:** There is no official public Robinhood API for retail investors. `robin_stocks` is the most widely-used community-maintained Python library that reverse-engineers Robinhood's private API. It is the only practical way to programmatically retrieve your portfolio data without manually exporting CSVs.

**Alternative considered:** Manual data entry or CSV uploads. Rejected because it defeats the purpose of automation.

**Tradeoff:** Because `robin_stocks` uses an unofficial API, it may break without warning if Robinhood changes their backend. It also requires storing your Robinhood credentials, which carries security implications (see [Section 7](#7-credential-security)).

### Anthropic Claude — AI Analysis
**Why:** The core value of this tool is converting raw portfolio numbers into an opinionated, human-readable analysis — identifying trends, summarizing news implications, assessing risk, and suggesting what to watch. This requires a capable large language model. Claude was chosen for the quality of its structured output and its ability to follow strict formatting instructions reliably.

**What model is used:** `claude-opus-4-5` (configurable in `weekly_report_gen.py` line ~226).

**Why not a local model?** Local LLMs (e.g., Ollama, LM Studio) were considered but produce significantly lower quality financial analysis at the required context length. A cloud API was chosen to ensure report quality.

**Privacy tradeoff:** Your financial position data is sent to Anthropic's servers. Anthropic's [privacy policy](https://www.anthropic.com/privacy) governs how this data is handled. By default, Anthropic does not train on API data from paying customers.

### Tavily — Web Search / News
**Why:** Claude's training data has a knowledge cutoff and cannot access real-time news. To give the analysis current context (earnings reports, regulatory news, market events from this week), the tool fetches recent news for each holding using Tavily's web search API.

**Why Tavily instead of Google Search or another provider?**
Tavily is purpose-built for AI applications — it returns clean, structured text content optimized for use in LLM prompts, without requiring scraping or parsing HTML. It has a free tier and straightforward API.

**Alternative considered:** Scraping financial news sites directly. Rejected due to rate limiting, ToS restrictions, and the extra complexity of parsing HTML from different sites.

**Privacy tradeoff:** Tavily sees the names and tickers of the companies in your portfolio. It does not receive any financial figures.

### ReportLab — PDF Generation
**Why:** ReportLab is the industry-standard Python library for generating production-quality PDFs programmatically. It supports custom fonts, tables, embedded images, page-level callbacks for headers/footers, and precise layout control — all needed for the dark-themed, multi-section report format.

**Alternative considered:** `weasyprint` (HTML-to-PDF). Rejected because it requires a separate CSS styling layer and produces less predictable cross-platform output for complex layouts.

**Privacy:** ReportLab is a local library — no data leaves your machine during PDF generation.

### Matplotlib — Charts
**Why:** Matplotlib is the standard Python charting library. It generates the portfolio allocation pie chart and the P&L bar chart as in-memory PNG buffers that are embedded directly into the PDF. No network calls are made.

---

## 6. API Costs

All three external API services have free tiers. Below is an estimate for typical usage (one report per week):

### Anthropic (Claude)
- **Model:** `claude-opus-4-5`
- **Tokens per report:** ~3,000–4,000 input tokens (prompt) + ~2,500–3,500 output tokens (analysis)
- **Approximate cost per report:** ~$0.05–$0.15 USD (at Opus-level pricing)
- **Monthly cost (4 reports/month):** ~$0.20–$0.60 USD
- **Free tier:** Anthropic offers free credits for new accounts via [console.anthropic.com](https://console.anthropic.com)

You can reduce costs by switching to a smaller model (e.g., `claude-sonnet-4-6` or `claude-haiku-4-5-20251001`) in `weekly_report_gen.py` line ~226. Analysis quality will be somewhat lower but the cost drops significantly.

### Tavily
- **Calls per report:** 1 call per holding + 1 call for macro news. A 10-stock portfolio = ~11 calls.
- **Free tier:** 1,000 searches/month — more than enough for weekly personal use.
- **Paid tier:** ~$0.01 per search beyond the free tier
- **Monthly cost (4 reports/month, 10 holdings):** $0 (within free tier)
- Pricing details: [tavily.com/pricing](https://tavily.com/pricing)

### robin_stocks / Robinhood
- **Cost:** Free. `robin_stocks` is open-source and Robinhood does not charge for API access.

### Email (SMTP)
- **Cost:** Free. Standard SMTP via Gmail or any provider is free for personal use volumes.

### Summary

| Service | Typical monthly cost |
|---|---|
| Anthropic Claude | ~$0.20–$0.60 |
| Tavily | $0 (free tier) |
| Robinhood data | $0 |
| Email delivery | $0 |
| **Total** | **~$0.20–$0.60/month** |

---

## 7. Credential Security

Your credentials (Robinhood login, API keys) are stored only in your shell environment file (e.g., `~/.zshrc`). This is the standard Unix approach for local tool configuration.

**Best practices:**
- Never commit your shell profile or any file containing API keys to a public git repository.
- Add a `.gitignore` entry for any `.env` files if you choose to use them instead.
- Use your operating system's disk encryption (FileVault on macOS, BitLocker on Windows) to protect credentials at rest.
- Lock your computer when unattended.
- For Robinhood: use a strong, unique password and enable two-factor authentication on your account.
- For Gmail: use an [App Password](https://myaccount.google.com/apppasswords) rather than your main account password. App passwords can be revoked individually without changing your main password.
- For Anthropic and Tavily: set spending limits in their respective dashboards so an accidental loop or bug cannot generate unexpected charges.

**What happens if my API key is compromised?**
- Anthropic: Rotate the key at [console.anthropic.com](https://console.anthropic.com) → API Keys.
- Tavily: Rotate the key in your Tavily dashboard.
- Robinhood: Change your Robinhood password immediately. This invalidates existing session tokens.

---

## 8. Robinhood Authentication

`robin_stocks` authenticates using your Robinhood email and password via Robinhood's private API. After a successful login, Robinhood issues a session token (stored by `robin_stocks` in `~/.tokens/`) which is reused on subsequent runs to avoid repeated logins.

**Two-factor authentication:** If your Robinhood account has SMS or authenticator-app 2FA enabled, `robin_stocks` will prompt for your 2FA code interactively on first run. Once a session token is cached, subsequent runs do not require the 2FA code until the token expires.

**Important:** `robin_stocks` is an **unofficial, community-maintained library** that is not affiliated with or endorsed by Robinhood. Use of this library may technically violate Robinhood's Terms of Service. By using this tool, you accept responsibility for reviewing and complying with Robinhood's Terms of Service applicable to your account.

---

## 9. AI Analysis — What Does Claude Receive?

Here is an example of the type of data included in the Claude prompt (values are illustrative):

```
PORTFOLIO HOLDINGS:
AAPL (Apple Inc.)
  - Shares: 10.00
  - Avg Cost: $150.00
  - Current Price: $175.00
  - Market Value: $1,750.00
  - Total P&L: +$250.00 (+16.67%)

PORTFOLIO SUMMARY:
  - Total Portfolio Value: $12,500.00
  - Total Invested: $10,000.00
  - Total P&L (All-Time): +$2,500.00 (+25.00%)
  - Unrealized P&L: +$1,200.00

RECENT NEWS BY HOLDING:
AAPL:
  1. [News snippet up to 300 characters from Tavily search result]...
```

**What is NOT included in the prompt:**
- Your name, Robinhood username, or account number
- Your email address
- Your Social Security Number or tax ID
- Your bank account or routing numbers
- Any personally identifying information

The prompt contains only financial position data and public news snippets.

---

## 10. Email Privacy

If you configure email delivery:

- The PDF report is attached to an email and sent via your configured SMTP server.
- The email is sent **from your own email account to your own email account** (or a recipient you specify).
- Email content travels over TLS-encrypted SMTP (STARTTLS on port 587).
- The tool's author has no visibility into your email or its contents.

**Gmail note:** Google may scan email content for spam/malware detection per their Terms of Service. If you want a fully private channel, consider a self-hosted email server or a privacy-focused provider.

---

## 11. No Tracking, No Telemetry

This tool contains **no analytics, telemetry, crash reporting, or usage tracking** of any kind. The only outbound network connections are the ones explicitly listed above (Robinhood auth, Anthropic API, Tavily search, and optional SMTP email). There are no callbacks to any server controlled by the tool's author.

---

## 12. Third-Party Terms of Service

By using this tool you are interacting with the following third-party services. You are responsible for complying with their respective terms:

| Service | Terms of Service |
|---|---|
| Robinhood | [robinhood.com/us/en/support/articles/terms-conditions](https://robinhood.com/us/en/support/articles/terms-conditions) |
| Anthropic | [anthropic.com/legal/consumer-terms](https://www.anthropic.com/legal/consumer-terms) |
| Tavily | [tavily.com/terms](https://tavily.com/terms) |
| Gmail SMTP | [policies.google.com/terms](https://policies.google.com/terms) |

---

## 13. Risk Disclaimers

- **Not financial advice.** The AI-generated analysis in the report is for informational purposes only. It does not constitute investment advice, a recommendation to buy or sell any security, or a solicitation of any investment. Always consult a qualified financial advisor before making investment decisions.

- **No guarantee of accuracy.** Portfolio data depends on the correctness of `robin_stocks` and Robinhood's API. News data depends on Tavily's search results. AI analysis depends on Claude's interpretation of the data. None of these are guaranteed to be accurate or up-to-date.

- **Unofficial API.** `robin_stocks` uses Robinhood's private, undocumented API. It may break without warning if Robinhood changes their backend.

- **Use at your own risk.** The tool's author provides this software as-is with no warranty of any kind.
