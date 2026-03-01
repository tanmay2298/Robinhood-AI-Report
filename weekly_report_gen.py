import os
import io
import re
import sys
import argparse
import subprocess
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

import robin_stocks.robinhood as rh
from anthropic import Anthropic
from tavily import TavilyClient

# Email functionality (optional)
try:
    from email_sender import send_report_email, send_error_email
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    print("Warning: email_sender module not found. Email functionality disabled.")

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    HRFlowable, PageBreak, Table, TableStyle, KeepTogether
)
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.pdfgen import canvas as rl_canvas

# ── Configuration ─────────────────────────────────────────────────────────
# Portfolio value source configuration
# Options: "regular" (market hours), "extended" (after/pre-market)
PORTFOLIO_VALUE_MODE = "regular"  # Change to "extended" for extended hours value

# Email configuration
SEND_EMAIL = True  # Set to False to disable email sending

# ── Palette ───────────────────────────────────────────────────────────────
BG         = colors.HexColor("#0f1117")
SURFACE    = colors.HexColor("#1a1f2e")
BORDER     = colors.HexColor("#2d3748")
TEXT_MAIN  = colors.HexColor("#e2e8f0")
TEXT_DIM   = colors.HexColor("#718096")
ACCENT_BLU = colors.HexColor("#4299e1")
ACCENT_GRN = colors.HexColor("#48bb78")
ACCENT_YEL = colors.HexColor("#f6ad55")
ACCENT_RED = colors.HexColor("#fc8181")
WHITE      = colors.white

# Chart colours – a curated palette for the pie
CHART_PALETTE = [
    "#4299e1", "#48bb78", "#f6ad55", "#9f7aea", "#fc8181",
    "#38b2ac", "#ed8936", "#667eea", "#68d391", "#f687b3",
    "#4fd1c5", "#fbb6ce", "#76e4f7", "#d6bcfa", "#90cdf4",
    "#faf089", "#c6f6d5", "#bee3f8", "#fed7d7", "#e9d8fd",
]

# ── Clients ───────────────────────────────────────────────────────────────
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
tavily    = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


# ─────────────────────────────────────────────────────────────────────────
# Step 1: Login + portfolio
# ─────────────────────────────────────────────────────────────────────────
def get_portfolio():
    print("Logging in to Robinhood...")
    rh.login(
        username=os.environ["ROBINHOOD_EMAIL"],
        password=os.environ["ROBINHOOD_PASSWORD"],
        store_session=True,
    )
    print("Fetching portfolio...")
    holdings = rh.build_holdings()
    profile  = rh.load_portfolio_profile()
    return holdings, profile


# ─────────────────────────────────────────────────────────────────────────
# Step 2: News fetch
# ─────────────────────────────────────────────────────────────────────────
def get_news(holdings):
    print("Fetching news for each holding...")
    news = {}
    for ticker, data in holdings.items():
        company = data.get("name", ticker)
        print(f"  Searching news for {ticker}...")
        results = tavily.search(
            query=f"{company} {ticker} stock news this week",
            max_results=3,
        )
        news[ticker] = [r["content"] for r in results.get("results", [])]

    print("  Fetching macro market news...")
    macro = tavily.search(
        query="stock market news this week S&P 500 Fed interest rates",
        max_results=3,
    )
    news["MACRO"] = [r["content"] for r in macro.get("results", [])]
    return news


# ─────────────────────────────────────────────────────────────────────────
# Step 3: Prompt assembly
# ─────────────────────────────────────────────────────────────────────────
def build_prompt(holdings, profile, news, pnl_metrics=None):
    # Calculate P&L if not provided
    if pnl_metrics is None:
        pnl_metrics = calculate_portfolio_pnl(holdings, profile)

    total_pnl, total_equity, total_invested, pnl_pct, unrealized_pnl = pnl_metrics

    portfolio_text = "PORTFOLIO HOLDINGS:\n"
    for ticker, data in holdings.items():
        portfolio_text += f"""
{ticker} ({data.get('name', '')})
  - Shares: {data.get('quantity')}
  - Avg Cost: ${data.get('average_buy_price')}
  - Current Price: ${data.get('price')}
  - Market Value: ${data.get('equity')}
  - Total P&L: ${data.get('equity_change')} ({data.get('percent_change')}%)
"""

    # Format P&L with proper sign
    pnl_sign = "+" if total_pnl >= 0 else ""
    unrealized_sign = "+" if unrealized_pnl >= 0 else ""

    portfolio_text += f"""
PORTFOLIO SUMMARY:
  - Total Portfolio Value: ${total_equity:,.2f}
  - Total Invested: ${total_invested:,.2f}
  - Total P&L (All-Time): {pnl_sign}${total_pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)
  - Unrealized P&L (Current Positions): {unrealized_sign}${unrealized_pnl:,.2f}
"""

    news_text = "RECENT NEWS BY HOLDING:\n"
    for ticker, articles in news.items():
        news_text += f"\n{ticker}:\n"
        for i, article in enumerate(articles, 1):
            news_text += f"  {i}. {article[:300]}...\n"

    prompt = f"""
You are a professional portfolio analyst. Today is {datetime.now().strftime('%A, %B %d, %Y')}.

STRICT FORMATTING RULES — follow these exactly every week, no exceptions:
- Use the section headers and sub-headers exactly as specified below.
- For every individual holding, use ONLY the 5-bullet format shown — no paragraphs, no extra bullets.
- Each bullet must be ONE concise sentence (max ~20 words). Be direct and specific.
- Do not add commentary, transitions, or summaries between stocks.
- For technical analysis, use the price data provided. Infer trend from price vs avg cost and context.

---

## 1. PORTFOLIO SUMMARY

- **Total Value:** [value] | **Unrealized P&L:** [$ amount] ([%]) overall
- **Week in Review:** [1 sentence on broad portfolio direction this week]
- **Top Performer:** [TICKER] +X% — [why in 5 words]
- **Worst Performer:** [TICKER] -X% — [why in 5 words]
- **Key Macro Influence:** [1 sentence on the biggest macro factor affecting the portfolio]

---

## 2. INDIVIDUAL STOCK ANALYSIS

For EVERY holding, output exactly this block — no more, no less:

### [TICKER] — [Company Name] | [emoji: 🟢 gain / 🔴 loss]
- **Performance:** Current $X.XX vs avg cost $X.XX → [+/-X%] total return
- **Technical:** [Trend: up/down/sideways], [key level to watch], [momentum note e.g. "near 52-week low" or "breaking out"]
- **News:** [Most relevant news headline this week in one sentence, and its direct implication for this position]
- **Risk:** [Single biggest risk to this position right now]
- **Outlook:** [Bullish / Neutral / Bearish] — [one-sentence reason]

---

## 3. PORTFOLIO HEALTH

- **Concentration:** [Top holding and % of portfolio; flag if >30%]
- **Diversification:** [Sector spread in 1 sentence — what's missing or over-represented]
- **Correlation Risk:** [Which holdings would all drop together and why]
- **Suggested Action:** [One specific rebalancing observation]

---

## 4. MARKET CONTEXT

- **Macro:** [Single most important macro event this week and its portfolio impact]
- **Fed / Rates:** [Current rate sentiment and implication for growth vs value holdings]
- **Sector Trends:** [1–2 sentences on trends relevant to holdings e.g. AI, biotech, energy]

---

## 5. WEEK AHEAD — WATCH LIST

- **Earnings:** [Any holdings reporting earnings this week — date and expectation]
- **Key Events:** [Economic releases or events that could move the portfolio]
- **Action Items:** [1–2 specific positions to watch or reconsider, with a brief reason]

---

{portfolio_text}

---

{news_text}
"""
    return prompt


# ─────────────────────────────────────────────────────────────────────────
# Step 4: Claude report generation
# ─────────────────────────────────────────────────────────────────────────
def generate_report(prompt):
    print("Generating report with Claude...")
    message = anthropic.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ─────────────────────────────────────────────────────────────────────────
# Step 5: Chart generation
# ─────────────────────────────────────────────────────────────────────────
def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def get_portfolio_value(profile):
    """
    Get the current portfolio value based on configuration.

    Supports both regular market hours and extended hours values.

    Args:
        profile: Profile dict from rh.load_portfolio_profile()

    Returns:
        float: Portfolio value based on PORTFOLIO_VALUE_MODE setting

    Available modes:
        - "regular": Uses equity (market hours value)
        - "extended": Uses extended_hours_equity (pre/after-market value)
    """
    if PORTFOLIO_VALUE_MODE == "extended":
        # Try extended hours fields in order of preference
        value = (profile.get('extended_hours_portfolio_equity') or
                 profile.get('extended_hours_equity') or
                 profile.get('equity'))
    else:
        # Use regular market hours equity
        value = profile.get('equity')

    # return _safe_float(value)
    return _safe_float(profile.get('equity_previous_close', 0))


def get_total_invested():
    """
    Calculate total amount invested by summing all deposits minus withdrawals.

    Returns:
        float: Net amount invested (deposits - withdrawals)
    """
    try:
        transfers = rh.get_bank_transfers()
        total_deposits = 0
        total_withdrawals = 0

        if transfers:
            for t in transfers:
                direction = t.get('direction', '')
                amount = _safe_float(t.get('amount', 0))
                if direction == 'deposit':
                    total_deposits += amount
                elif direction == 'withdraw':
                    total_withdrawals += amount

        return total_deposits - total_withdrawals
    except Exception as e:
        print(f"Warning: Could not fetch bank transfers: {e}")
        return 0


def calculate_portfolio_pnl(holdings, profile, total_invested=None):
    """
    Calculate total portfolio P&L using actual invested amount.

    Args:
        holdings: Dictionary of holdings from rh.build_holdings()
        profile: Portfolio profile from rh.load_portfolio_profile()
        total_invested: Optional pre-calculated total invested amount

    Returns:
        tuple: (total_pnl, total_equity, total_invested, pnl_pct, unrealized_pnl)
            - total_pnl: Total P&L (realized + unrealized) in dollars
            - total_equity: Current total portfolio value
            - total_invested: Total amount deposited (net of withdrawals)
            - pnl_pct: Total P&L as percentage of invested amount
            - unrealized_pnl: Unrealized P&L on current positions
    """
    # Get total invested amount if not provided
    if total_invested is None:
        total_invested = get_total_invested()

    # Current portfolio value (uses configured mode: regular or extended hours)
    total_equity = get_portfolio_value(profile)

    # Total P&L = Current Value - Amount Invested
    total_pnl = total_equity - total_invested
    pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0

    # Also calculate unrealized P&L on current positions for reference
    holdings_list = list(holdings.items())
    unrealized_pnl = sum(_safe_float(d.get("equity_change", 0)) for _, d in holdings_list)

    return total_pnl, total_equity, total_invested, pnl_pct, unrealized_pnl


def generate_charts(holdings):
    """Return (pie_buf, bar_buf) as BytesIO PNG image buffers."""
    tickers   = list(holdings.keys())
    values    = [_safe_float(holdings[t].get("equity")) for t in tickers]
    pnl_pcts  = [_safe_float(holdings[t].get("percent_change")) for t in tickers]
    total_val = sum(values)

    # ── Pie chart ────────────────────────────────────────────────────────
    # Combine tiny slices (< 1%) into "Other"
    threshold = 0.01 * total_val
    pie_labels, pie_vals, pie_colors = [], [], []
    other_val = 0.0
    for i, (t, v) in enumerate(zip(tickers, values)):
        if v >= threshold:
            pie_labels.append(t)
            pie_vals.append(v)
            pie_colors.append(CHART_PALETTE[i % len(CHART_PALETTE)])
        else:
            other_val += v
    if other_val > 0:
        pie_labels.append("Other")
        pie_vals.append(other_val)
        pie_colors.append("#4a5568")

    fig, ax = plt.subplots(figsize=(9, 6), facecolor="#0f1117")
    ax.set_facecolor("#0f1117")

    wedges, _ = ax.pie(
        pie_vals,
        colors=pie_colors,
        startangle=140,
        wedgeprops=dict(width=0.55, edgecolor="#0f1117", linewidth=1.5),
    )

    # Legend (two columns)
    legend_labels = [
        f"{lbl}  ${v:,.0f}" for lbl, v in zip(pie_labels, pie_vals)
    ]
    ax.legend(
        wedges, legend_labels,
        loc="center left",
        bbox_to_anchor=(0.92, 0.5),
        fontsize=7.5,
        labelcolor="#e2e8f0",
        facecolor="#1a1f2e",
        edgecolor="#2d3748",
        framealpha=0.9,
        ncol=1,
    )

    # Center annotation
    ax.text(0, 0, f"${total_val:,.0f}\nTotal",
            ha="center", va="center", fontsize=11,
            color="white", fontweight="bold", linespacing=1.6)

    ax.set_title("Portfolio Allocation", color="white", fontsize=14,
                 fontweight="bold", pad=14)
    plt.tight_layout()

    pie_buf = io.BytesIO()
    fig.savefig(pie_buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="#0f1117")
    plt.close(fig)
    pie_buf.seek(0)

    # ── P&L bar chart (LANDSCAPE) ────────────────────────────────────────
    # Sort by pct change (best → worst)
    pairs = sorted(zip(tickers, pnl_pcts), key=lambda x: x[1], reverse=True)
    s_tickers = [p[0] for p in pairs]
    s_pcts    = [p[1] for p in pairs]
    bar_clrs  = ["#48bb78" if p >= 0 else "#fc8181" for p in s_pcts]

    # Landscape: extra wide, short height - spans full page width
    fig2, ax2 = plt.subplots(figsize=(14, 4), facecolor="#0f1117")
    fig2.patch.set_facecolor("#0f1117")
    ax2.set_facecolor("#1a1f2e")

    y_pos = np.arange(len(s_tickers))
    bars  = ax2.barh(y_pos, s_pcts, color=bar_clrs, edgecolor="#0f1117",
                     linewidth=0.5, height=0.65)

    # Labels inside / outside bars
    for bar, pct in zip(bars, s_pcts):
        w = bar.get_width()
        x_pos = w + (0.3 if w >= 0 else -0.3)
        ha    = "left" if w >= 0 else "right"
        ax2.text(x_pos, bar.get_y() + bar.get_height() / 2,
                 f"{pct:+.1f}%",
                 va="center", ha=ha, fontsize=7.5,
                 color="#e2e8f0", fontweight="bold")

    ax2.axvline(0, color="#4a5568", linewidth=0.8)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(s_tickers, color="#e2e8f0", fontsize=8)
    ax2.tick_params(axis="x", colors="#718096", labelsize=8)
    ax2.spines[:].set_color("#2d3748")
    ax2.set_xlabel("Unrealized P&L (%)", color="#718096", fontsize=9)
    ax2.set_title("Unrealized P&L by Holding", color="white",
                  fontsize=13, fontweight="bold", pad=12)
    ax2.grid(axis="x", color="#2d3748", linewidth=0.5, linestyle="--")

    plt.tight_layout()
    bar_buf = io.BytesIO()
    fig2.savefig(bar_buf, format="png", dpi=150, bbox_inches="tight",
                 facecolor="#0f1117")
    plt.close(fig2)
    bar_buf.seek(0)

    return pie_buf, bar_buf


# ─────────────────────────────────────────────────────────────────────────
# Step 6: PDF assembly
# ─────────────────────────────────────────────────────────────────────────

# ── Page-level canvas callback (background + footer) ─────────────────────
def _make_page_cb(date_str):
    def on_page(canvas, doc):
        canvas.saveState()
        w, h = letter
        # Dark background
        canvas.setFillColor(BG)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        # Subtle top border line
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(1)
        canvas.line(0.5 * inch, h - 0.55 * inch, w - 0.5 * inch, h - 0.55 * inch)
        # Footer
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(TEXT_DIM)
        canvas.drawString(0.6 * inch, 0.35 * inch,
                          f"Portfolio Report · {date_str} · For personal use only")
        canvas.drawRightString(w - 0.6 * inch, 0.35 * inch,
                               f"Page {doc.page}")
        canvas.restoreState()
    return on_page


# ── Paragraph styles ──────────────────────────────────────────────────────
def _styles():
    base = dict(fontName="Helvetica", textColor=TEXT_MAIN, leading=16)

    h1 = ParagraphStyle("h1", fontSize=20, fontName="Helvetica-Bold",
                         textColor=WHITE, spaceAfter=6, spaceBefore=20,
                         leading=26)
    h2 = ParagraphStyle("h2", fontSize=14, fontName="Helvetica-Bold",
                         textColor=ACCENT_BLU, spaceAfter=4, spaceBefore=16,
                         leading=20, borderPad=4,
                         borderColor=ACCENT_BLU, borderWidth=0)
    h3 = ParagraphStyle("h3", fontSize=11, fontName="Helvetica-Bold",
                         textColor=ACCENT_GRN, spaceAfter=2, spaceBefore=12,
                         leading=16)
    body = ParagraphStyle("body", fontSize=9.5, leading=15,
                           textColor=TEXT_MAIN, spaceAfter=6,
                           fontName="Helvetica")
    bullet = ParagraphStyle("bullet", fontSize=9.5, leading=15,
                              textColor=TEXT_MAIN, spaceAfter=3,
                              leftIndent=14, bulletIndent=0,
                              fontName="Helvetica")
    dim = ParagraphStyle("dim", fontSize=8.5, leading=13,
                          textColor=TEXT_DIM, fontName="Helvetica")
    kpi_val = ParagraphStyle("kpi_val", fontSize=22, fontName="Helvetica-Bold",
                              textColor=WHITE, leading=28, alignment=TA_CENTER)
    kpi_lbl = ParagraphStyle("kpi_lbl", fontSize=8, fontName="Helvetica",
                              textColor=TEXT_DIM, leading=11, alignment=TA_CENTER)
    return h1, h2, h3, body, bullet, dim, kpi_val, kpi_lbl


def _kpi_box(value, label, color=WHITE):
    """Return a 1-cell Table that looks like a KPI card."""
    _, _, _, body, _, _, kpi_val, kpi_lbl = _styles()
    val_style = ParagraphStyle("kv", fontSize=22, fontName="Helvetica-Bold",
                                textColor=color, leading=28, alignment=TA_CENTER)
    data = [[
        Paragraph(value, val_style),
        Spacer(1, 4),
        Paragraph(label, kpi_lbl),
    ]]
    # Use a nested single-column table
    inner = Table([[Paragraph(value, val_style)],
                   [Paragraph(label, kpi_lbl)]],
                  colWidths=[2.0 * inch])
    inner.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("ROUNDEDCORNERS", [6]),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 1, BORDER),
    ]))
    return inner


def _section_header(text, style):
    """A coloured left-bar paragraph to mark section starts."""
    return Paragraph(
        f'<font color="#4299e1">▌</font> {text}', style
    )


def _parse_report(report_text, h1, h2, h3, body, bullet, holdings=None):
    """Convert Claude's markdown output to a list of reportlab Flowables."""
    flowables = []
    lines = report_text.split("\n")

    # Build ticker P&L lookup for color determination
    ticker_colors = {}
    if holdings:
        for ticker, data in holdings.items():
            pnl = _safe_float(data.get("equity_change", 0))
            ticker_colors[ticker] = ACCENT_GRN if pnl >= 0 else ACCENT_RED

    # Strip markdown bold/italic for clean rendering
    def clean(t):
        t = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', t)
        t = re.sub(r'\*\*(.+?)\*\*',     r'<b>\1</b>', t)
        t = re.sub(r'\*(.+?)\*',         r'<i>\1</i>', t)
        t = re.sub(r'`(.+?)`',           r'<font name="Courier">\1</font>', t)
        # Escape raw ampersands not already escaped
        t = re.sub(r'&(?!amp;|lt;|gt;|quot;|#)', '&amp;', t)
        return t

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if line.startswith("### "):
            header_text = line[4:]
            # Check if this is a ticker symbol header
            ticker_match = None
            for ticker in ticker_colors.keys():
                if ticker in header_text:
                    ticker_match = ticker
                    break

            if ticker_match:
                # Use profit/loss color for stock headers
                color = ticker_colors[ticker_match]
                h3_colored = ParagraphStyle("h3_colored", fontSize=11, fontName="Helvetica-Bold",
                                          textColor=color, spaceAfter=2, spaceBefore=12,
                                          leading=16)
                flowables.append(Paragraph(clean(header_text), h3_colored))
            else:
                # Use default green for non-stock headers
                flowables.append(Paragraph(clean(header_text), h3))
        elif line.startswith("## "):
            flowables.append(Spacer(1, 6))
            flowables.append(Paragraph(
                f'<font color="#4299e1">▌</font> {clean(line[3:])}', h2))
        elif line.startswith("# "):
            flowables.append(Paragraph(clean(line[2:]), h1))
        elif re.match(r"^[-*] ", line):
            flowables.append(Paragraph(f"• {clean(line[2:])}", bullet))
        elif re.match(r"^\d+\. ", line):
            m = re.match(r"^(\d+)\. (.+)$", line)
            if m:
                flowables.append(
                    Paragraph(f"{m.group(1)}.&nbsp; {clean(m.group(2))}", bullet))
        elif re.match(r"^---+$", line):
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.5,
                                         color=BORDER, spaceAfter=4))
        elif line.strip() == "":
            flowables.append(Spacer(1, 4))
        else:
            flowables.append(Paragraph(clean(line), body))

        i += 1

    return flowables


def build_pdf(report_text, holdings, profile, date_str):
    print("Generating charts...")
    pie_buf, bar_buf = generate_charts(holdings)

    # Create Portfolio_Reports directory if it doesn't exist
    reports_dir = "Portfolio_Reports"
    os.makedirs(reports_dir, exist_ok=True)

    filename = os.path.join(reports_dir, f"report_{date_str}.pdf")
    w_pt, h_pt = letter

    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.65 * inch,
    )

    h1, h2, h3, body, bullet, dim, kpi_val, kpi_lbl = _styles()
    page_cb = _make_page_cb(date_str)
    story   = []

    # ── Cover block ───────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * inch))
    cover_title = ParagraphStyle(
        "ct", fontSize=28, fontName="Helvetica-Bold",
        textColor=WHITE, leading=36, alignment=TA_CENTER
    )
    cover_sub = ParagraphStyle(
        "cs", fontSize=11, fontName="Helvetica",
        textColor=TEXT_DIM, leading=16, alignment=TA_CENTER
    )
    story.append(Paragraph("📊 Weekly Portfolio Report", cover_title))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%A, %B %d, %Y')} · "
        "For personal use only · Not financial advice",
        cover_sub
    ))
    story.append(Spacer(1, 0.3 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 0.25 * inch))

    # ── KPI row ───────────────────────────────────────────────────────────
    # Calculate portfolio P&L using shared function
    holdings_list = list(holdings.items())
    total_pnl, total_equity, total_invested, pnl_pct, unrealized_pnl = calculate_portfolio_pnl(holdings, profile)
    n_pos = len(holdings)

    pnl_color  = ACCENT_GRN if total_pnl >= 0 else ACCENT_RED
    pnl_sign   = "+" if total_pnl >= 0 else ""

    kpi1 = _kpi_box(f"${total_equity:,.2f}", "Total Portfolio Value", WHITE)
    kpi2 = _kpi_box(f"{pnl_sign}${total_pnl:,.2f}\n({pnl_sign}{pnl_pct:.1f}%)",
                    "Total P&L (All-Time)", pnl_color)
    kpi3 = _kpi_box(str(n_pos), "Open Positions", ACCENT_BLU)

    kpi_row = Table([[kpi1, kpi2, kpi3]],
                    colWidths=[(w_pt - 1.3 * inch) / 3] * 3)
    kpi_row.setStyle(TableStyle([
        ("ALIGN",   (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_row)
    story.append(Spacer(1, 0.3 * inch))

    # ── Holdings summary table ────────────────────────────────────────────
    story.append(Paragraph(
        '<font color="#4299e1">▌</font> Holdings Snapshot', h2))
    story.append(Spacer(1, 6))

    tbl_header = ["Ticker", "Name", "Shares", "Avg Cost", "Price",
                  "Mkt Value", "P&L $", "P&L %"]
    tbl_rows   = [tbl_header]
    for ticker, d in sorted(holdings_list,
                             key=lambda x: _safe_float(x[1].get("equity", 0)),
                             reverse=True):
        pnl_d   = _safe_float(d.get("equity_change", 0))
        pnl_p   = _safe_float(d.get("percent_change", 0))
        clr     = "#48bb78" if pnl_d >= 0 else "#fc8181"
        sign    = "+" if pnl_d >= 0 else ""
        tbl_rows.append([
            ticker,
            (d.get("name", "") or "")[:22],
            f'{_safe_float(d.get("quantity", 0)):.2f}',
            f'${_safe_float(d.get("average_buy_price", 0)):.2f}',
            f'${_safe_float(d.get("price", 0)):.2f}',
            f'${_safe_float(d.get("equity", 0)):,.2f}',
            f'{sign}${abs(pnl_d):.2f}',
            f'{sign}{pnl_p:.1f}%',
        ])

    col_w = [0.55, 1.6, 0.6, 0.75, 0.65, 0.85, 0.8, 0.7]
    col_w = [c * inch for c in col_w]

    tbl_style = TableStyle([
        # Header row
        ("BACKGROUND",  (0, 0), (-1, 0),  SURFACE),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  ACCENT_BLU),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  8),
        ("BOTTOMPADDING",(0, 0),(-1, 0),  8),
        ("TOPPADDING",  (0, 0), (-1, 0),  8),
        # Body rows
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8),
        ("TEXTCOLOR",   (0, 1), (-1, -1), TEXT_MAIN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG, SURFACE]),
        ("TOPPADDING",  (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING",(0,1), (-1, -1), 5),
        # Grid
        ("LINEBELOW",   (0, 0), (-1, 0),  0.5, BORDER),
        ("LINEBELOW",   (0, 1), (-1, -1), 0.3, BORDER),
        ("ALIGN",       (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN",       (0, 0), (1, -1),  "LEFT"),
    ])
    holdings_tbl = Table(tbl_rows, colWidths=col_w,
                         repeatRows=1, splitByRow=True)
    holdings_tbl.setStyle(tbl_style)
    story.append(holdings_tbl)

    # ── Charts section ────────────────────────────────────────────────────
    # Follow the holdings table naturally — no hard page break so there's
    # no blank page when the table spills only a row or two onto a new page.
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        '<font color="#4299e1">▌</font> Portfolio Visualizations', h2))
    story.append(Spacer(1, 8))

    usable_w = w_pt - 1.3 * inch  # ~7.2 inches
    chart_h  = usable_w * 0.44    # ~3.17 inches; two charts + spacers ≈ 7in

    pie_img = Image(pie_buf, width=usable_w, height=chart_h)
    pie_img.hAlign = "CENTER"
    story.append(pie_img)
    story.append(Spacer(1, 14))

    bar_img = Image(bar_buf, width=usable_w, height=chart_h * 1.1)
    bar_img.hAlign = "CENTER"
    story.append(bar_img)

    # ── Analysis section ──────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph(
        '<font color="#4299e1">▌</font> AI Portfolio Analysis', h2))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Analysis generated by Claude · {date_str}", dim))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 8))

    analysis_flowables = _parse_report(report_text, h1, h2, h3, body, bullet, holdings)
    story.extend(analysis_flowables)

    print("Assembling PDF...")
    doc.build(story, onFirstPage=page_cb, onLaterPages=page_cb)
    print(f"PDF saved to {filename}")
    return filename


# ─────────────────────────────────────────────────────────────────────────
# Step 7: Open PDF
# ─────────────────────────────────────────────────────────────────────────
def open_pdf(filename):
    filepath = os.path.abspath(filename)
    if sys.platform == "darwin":
        subprocess.run(["open", filepath])
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", filepath])
    else:
        subprocess.run(["start", filepath], shell=True)
    print(f"Opened {filename}")


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate weekly portfolio report")
    parser.add_argument('--no-open', action='store_true',
                        help='Generate report without opening PDF (for scheduled runs)')
    args = parser.parse_args()

    date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*52}")
    print(f"  Weekly Portfolio Report — {datetime.now().strftime('%B %d, %Y')}")
    print(f"{'='*52}\n")

    holdings, profile = get_portfolio()
    news              = get_news(holdings)

    # Show which portfolio value mode is being used
    print(f"Portfolio value mode: {PORTFOLIO_VALUE_MODE}")
    portfolio_value = get_portfolio_value(profile)
    print(f"Current portfolio value: ${portfolio_value:,.2f}")

    # Calculate P&L using actual invested amount
    print("Calculating total invested amount from bank transfers...")
    total_invested    = get_total_invested()
    print(f"Total invested: ${total_invested:,.2f}")

    pnl_metrics       = calculate_portfolio_pnl(holdings, profile, total_invested)
    prompt            = build_prompt(holdings, profile, news, pnl_metrics)
    report_text       = generate_report(prompt)

    pdf_file = build_pdf(report_text, holdings, profile, date_str)

    # Only open PDF if not running in scheduled mode
    if not args.no_open:
        open_pdf(pdf_file)

    # Send email if enabled
    if SEND_EMAIL and EMAIL_AVAILABLE:
        try:
            send_report_email(pdf_file)
        except Exception as e:
            print(f"\n⚠️  Failed to send email: {e}")
            print("The report was still generated successfully.")
    elif SEND_EMAIL and not EMAIL_AVAILABLE:
        print("\n⚠️  Email sending is enabled but email_sender module is not available.")

    if args.no_open:
        print(f"\nDone! Report saved to {pdf_file}\n")
    else:
        print("\nDone! Report opened in your PDF viewer.\n")


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as e:
        tb = traceback.format_exc()
        print(f"\n❌ Fatal error: {e}")
        print(tb)
        if EMAIL_AVAILABLE:
            send_error_email(str(e), tb)
        sys.exit(1)