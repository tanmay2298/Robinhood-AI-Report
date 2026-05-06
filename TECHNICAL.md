# Technical Design — Robinhood Portfolio Report Generator

## Overview

A single-process Python pipeline that pulls live Robinhood portfolio data, enriches it with web-sourced news, sends it to a Claude LLM for structured analysis, and assembles the result into a styled PDF report. The pipeline runs end-to-end in one invocation of `weekly_report_gen.py` with no persistent state beyond an auth session cache managed by `robin_stocks`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    weekly_report_gen.py                     │
│                                                             │
│  get_portfolio()                                            │
│      └─ robin_stocks → Robinhood API                        │
│           holdings dict + portfolio profile dict            │
│                  │                                          │
│  get_news()      ▼                                          │
│      └─ TavilyClient.search() × (N holdings + 1 macro)     │
│           news dict keyed by ticker + "MACRO"               │
│                  │                                          │
│  build_prompt()  ▼                                          │
│      └─ Format portfolio + news into structured text prompt │
│                  │                                          │
│  generate_report()▼                                         │
│      └─ anthropic.messages.create() → markdown text        │
│                  │                                          │
│  build_pdf()     ▼                                          │
│      ├─ generate_charts() → matplotlib → BytesIO PNGs      │
│      ├─ calculate_portfolio_pnl() → KPI metrics            │
│      ├─ _parse_report() → ReportLab Flowables              │
│      └─ SimpleDocTemplate.build() → PDF file               │
│                  │                                          │
│  email_sender.py ▼                                          │
│      └─ SMTP → send PDF attachment                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Pipeline Steps

### 1. Authentication & Portfolio Fetch (`get_portfolio`)

Uses `robin_stocks.robinhood.login()` with `store_session=True`, which caches a session token locally to avoid re-authentication on subsequent runs. On first run with 2FA enabled, the library prompts for an OTP interactively.

Two calls are made:
- `rh.build_holdings()` — returns a dict keyed by ticker with per-position data: shares, average buy price, current price, market value, equity change, percent change.
- `rh.load_portfolio_profile()` — returns account-level fields including `equity`, `equity_previous_close`, and extended-hours variants.

### 2. News Enrichment (`get_news`)

For each ticker, a Tavily search is issued with `max_results=3`:

```
query: "{company_name} {ticker} stock news this week"
```

A final macro search runs independently:

```
query: "stock market news this week S&P 500 Fed interest rates"
```

Results are stored as `news[ticker] = [content_str, ...]` with the first 300 characters of each result used in the prompt to stay within token budget.

### 3. P&L Calculation (`calculate_portfolio_pnl`, `get_total_invested`)

Portfolio P&L is calculated against actual cash invested rather than Robinhood's reported equity change, which only covers current open positions:

```
total_invested = Σ deposits - Σ withdrawals   (from rh.get_bank_transfers())
total_pnl      = portfolio_value - total_invested
pnl_pct        = total_pnl / total_invested × 100
unrealized_pnl = Σ equity_change across all holdings  (open positions only)
```

`get_portfolio_value()` reads from `equity_previous_close` by default. The `PORTFOLIO_VALUE_MODE` config controls whether to use regular or extended-hours equity.

### 4. Prompt Construction (`build_prompt`)

The prompt encodes a strict persona and output schema:

- **Persona:** Goldman Sachs portfolio analyst, 20 years experience
- **Date injection:** `datetime.now()` so the model can reason about recency
- **Formatting contract:** Five numbered sections with exact bullet structures enforced via instructions embedded in the user turn
- **Data:** Full holdings table (shares, avg cost, price, equity, P&L) + portfolio summary metrics + per-ticker news snippets

The strict formatting contract is critical for the PDF parser downstream — `_parse_report` relies on predictable markdown headings (`##`, `###`) and bullet structure.

### 5. LLM Generation (`generate_report`)

```python
anthropic.messages.create(
    model="claude-opus-4-5",
    max_tokens=4000,
    messages=[{"role": "user", "content": prompt}],
)
```

No streaming, no system prompt (instructions are inlined in the user turn), no tool use. The response is expected to be markdown with the five-section structure.

### 6. Chart Generation (`generate_charts`)

Two charts are produced as in-memory `BytesIO` PNG buffers (never written to disk):

**Donut pie chart** — portfolio allocation by market value. Slices below 1% of total are collapsed into an "Other" segment. Uses a 20-color palette cycling by position index.

**Horizontal bar chart** — unrealized P&L % per holding, sorted best-to-worst. Bars are green (`#48bb78`) for gains and red (`#fc8181`) for losses. Rendered landscape (14×4 inches) to span the full PDF page width.

Both charts render at 150 DPI on a dark `#0f1117` background to match the PDF theme.

### 7. PDF Assembly (`build_pdf`)

Built with ReportLab's `SimpleDocTemplate` on US Letter with a custom page callback (`_make_page_cb`) that draws the dark background, a top border line, and a footer on every page via the canvas layer.

**Layout sequence:**
1. Cover block — title + generation timestamp + disclaimer
2. KPI row — three card-style tables: Total Value, Total P&L (all-time), Open Positions
3. Holdings Snapshot — table with alternating row backgrounds, right-aligned numeric columns, sorted by market value descending
4. Portfolio Visualizations — pie image then bar image, both scaled to page width
5. `PageBreak`
6. AI Portfolio Analysis — parsed from Claude's markdown output via `_parse_report()`

**Markdown parser (`_parse_report`):**

Converts Claude's output line-by-line into ReportLab `Flowable` objects:

| Markdown pattern | Flowable |
|---|---|
| `### heading` | `Paragraph` with h3 style; ticker headers use green/red based on P&L |
| `## heading` | `Paragraph` with blue accent bar prefix |
| `- bullet` or `* bullet` | `Paragraph` with bullet indent |
| `---` | `HRFlowable` |
| blank line | `Spacer(1, 4)` |
| plain text | `Paragraph` with body style |

Bold/italic markdown is converted to ReportLab XML tags (`<b>`, `<i>`). Raw `&` characters are escaped to `&amp;` to prevent XML parse errors.

**Color palette:**

| Token | Hex | Usage |
|---|---|---|
| `BG` | `#0f1117` | Page background |
| `SURFACE` | `#1a1f2e` | Card/row backgrounds |
| `BORDER` | `#2d3748` | Lines, table borders |
| `TEXT_MAIN` | `#e2e8f0` | Body text |
| `TEXT_DIM` | `#718096` | Labels, footer |
| `ACCENT_BLU` | `#4299e1` | Section headers, KPI labels |
| `ACCENT_GRN` | `#48bb78` | Gains, positive P&L |
| `ACCENT_RED` | `#fc8181` | Losses, negative P&L |

### 8. Email Delivery (`email_sender.py`)

Plain SMTP via `smtplib` with STARTTLS. The PDF is attached as `MIMEApplication` with subtype `pdf`. Two entry points:

- `send_report_email(pdf_path)` — sends the report on success
- `send_error_email(error_message, traceback_str)` — called from the top-level `try/except` in `main()` on fatal crash

Email is only sent if `SEND_EMAIL = True` and the `email_sender` module imported successfully. The module import is wrapped in a `try/except` at the top of `weekly_report_gen.py` so the pipeline runs without email if the module is missing.

### 9. Scheduling

**macOS:** `launchd` via a `.plist` in `~/Library/LaunchAgents/`. The `run_report.sh` wrapper activates the venv and runs `python3 weekly_report_gen.py --no-open`. The `--no-open` flag skips the `subprocess.run(["open", ...])` call that would be a no-op in a headless context.

**Linux:** `cron` with the same shell wrapper.

---

## Configuration Reference

| Constant / Env Var | Location | Default | Description |
|---|---|---|---|
| `PORTFOLIO_VALUE_MODE` | `weekly_report_gen.py:43` | `"regular"` | `"regular"` or `"extended"` |
| `SEND_EMAIL` | `weekly_report_gen.py:46` | `True` | Master email toggle |
| `ROBINHOOD_EMAIL` | env | — | Robinhood login |
| `ROBINHOOD_PASSWORD` | env | — | Robinhood login |
| `ANTHROPIC_API_KEY` | env | — | Claude API key |
| `TAVILY_API_KEY` | env | — | Tavily search API key |
| `EMAIL_SENDER` | env | — | SMTP sender address |
| `EMAIL_PASSWORD` | env | — | SMTP password / app password |
| `EMAIL_RECIPIENT` | env | `EMAIL_SENDER` | Report recipient |
| `EMAIL_SMTP_HOST` | env | `smtp.gmail.com` | SMTP host |
| `EMAIL_SMTP_PORT` | env | `587` | SMTP port |

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `robin-stocks` | ≥3.0.0 | Robinhood API (unofficial) |
| `anthropic` | ≥0.18.0 | Claude LLM API |
| `tavily-python` | ≥0.3.0 | Web search for news |
| `matplotlib` | ≥3.7.0 | Chart generation |
| `numpy` | ≥1.24.0 | Chart data processing |
| `reportlab` | ≥4.0.0 | PDF generation |

---

## Error Handling

The entire `main()` body is wrapped in a `try/except Exception` at the module level. On any unhandled exception:
1. The full traceback is printed to stdout
2. `send_error_email()` is called if email is configured
3. `sys.exit(1)` is called so the scheduler can detect failure

Individual subsystems degrade gracefully:
- `get_total_invested()` catches all exceptions and returns `0` with a warning, so a Robinhood API change to the transfers endpoint won't break the entire run
- `send_report_email()` returns `False` on failure rather than raising, so a broken email config doesn't abort a successful report generation

---

## Known Limitations

- **Unofficial Robinhood API.** `robin_stocks` reverse-engineers Robinhood's private API. Session tokens expire and 2FA prompts require an interactive terminal on first run.
- **Portfolio value field.** `get_portfolio_value()` currently reads `equity_previous_close` rather than `equity` (see `weekly_report_gen.py:271`). The displayed total reflects prior-close value, not real-time.
- **No prompt caching.** The Claude call sends the full prompt on every run. Adding a system prompt with a cache breakpoint would reduce cost on repeated runs with large portfolios.
- **Serial news fetches.** News fetches run one ticker at a time. Parallelizing with `concurrent.futures.ThreadPoolExecutor` would cut wall time significantly for larger portfolios.
