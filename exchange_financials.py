"""Official NSE and BSE rupee financial statements for the fundamentals backfill.

NSE is first: the public corporate financial-results list, then the XBRL file
linked from each filing (nsearchives.nseindia.com). BSE is the backup, using
its public results API and the same XBRL parser when a filing link is present.
Yahoo stays the last fallback and is not called from this module.

No Screener or Moneycontrol. No API key. Requests use a normal browser header
and, when the homepage answers, the cookies from that visit. A homepage that
is blocked (common from cloud IPs) is skipped; the results list still often
answers without it.

Request budget (documented, not raised vs the existing per-run name cap):
- one optional NSE homepage warm-up per process
- two list calls per stock (quarterly and annual)
- at most nse_xbrl_quarters (default 8) + nse_xbrl_annuals (default 4) XBRL files
- a short pause between XBRL files
- statements_per_run stays as configured (200). Extra HTTP calls per name mean
  the 18-minute cap may finish fewer names when NSE answers.

Each saved row records source (NSE or BSE) and currency (usually INR).
"""
from __future__ import annotations

import datetime as dt
import math
import re
import time
from urllib.parse import quote

import pandas as pd
import requests

import netutil

NSE_HOME = "https://www.nseindia.com/"
NSE_RESULTS = "https://www.nseindia.com/api/corporates-financial-results"
NSE_FILINGS_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
BSE_HOME = "https://www.bseindia.com/"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"

BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,text/html,application/xml,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
}

REVENUE_TAGS = (
    "RevenueFromOperations",
    "InterestEarned",
    "IncomeFromOperations",
    "TotalIncomeFromOperations",
    "Revenue",
)
NET_INCOME_TAGS = (
    "ProfitOrLossAttributableToOwnersOfParent",
    "ProfitLossForPeriod",
    "ProfitLossForThePeriod",
    "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
    "ProfitLossFromOrdinaryActivitiesAfterTax",
    "ProfitLossForPeriodFromContinuingOperations",
)
EPS_TAGS = (
    "DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
    "DilutedEarningsLossPerShareFromContinuingOperations",
    "DilutedEarningsPerShareAfterExtraordinaryItems",
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
    "BasicEarningsLossPerShareFromContinuingOperations",
    "BasicEarningsPerShareAfterExtraordinaryItems",
    "BasicEarningsPerShareBeforeExtraordinaryItems",
    "DilutedEPS",
    "BasicEPS",
)
OP_INCOME_TAGS = (
    "ProfitBeforeExceptionalItemsAndTax",
    "OperatingProfitBeforeProvisionAndContingencies",
    "ProfitBeforeTax",
    "ProfitLossFromOrdinaryActivitiesBeforeTax",
)
GROSS_PROFIT_TAGS = ("GrossProfit",)
EQUITY_TAGS = ("EquityShareCapital", "PaidUpValueOfEquityShareCapital")
OCF_TAGS = (
    "CashFlowsFromUsedInOperatingActivities",
    "CashFlowsFromUsedInOperations",
)
CAPEX_TAGS = (
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsClassifiedAsInvestingActivities",
)
CURRENCY_TAGS = ("DescriptionOfPresentationCurrency", "ReportingCurrency")
PAIDUP_TAGS = ("PaidUpValueOfEquityShareCapital",)
FACE_TAGS = ("FaceValueOfEquityShareCapital",)

_SESSION = None
_WARMED = {"nse": False, "bse": False}


def settings(cfg):
    raw = (cfg or {}).get("fundamentals_backfill") or {}

    def num(key, default):
        try:
            return type(default)(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "xbrl_quarters": max(1, num("nse_xbrl_quarters", 8)),
        "xbrl_annuals": max(1, num("nse_xbrl_annuals", 4)),
        "max_age_days": max(30, num("nse_results_max_age_days", 200)),
        "xbrl_pause": max(0.0, num("nse_xbrl_pause_seconds", 0.35)),
    }


def browser_session():
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _headers(referer):
    out = dict(BROWSER)
    out["Referer"] = referer
    return out


def http_get(url, cfg, referer, timeout=30):
    delays = tuple((cfg or {}).get("rate_limit", {}).get("backoff_seconds") or (1.5, 3, 6))
    tries = int(((cfg or {}).get("rate_limit") or {}).get("max_retries") or 3)
    return netutil.http_get(
        browser_session(), url, _headers(referer), timeout,
        max_tries=min(tries, 3), delays=delays,
    )


def warm_nse(cfg):
    """Visit the NSE homepage once so later calls can reuse its cookies."""
    if _WARMED["nse"]:
        return
    _WARMED["nse"] = True
    try:
        http_get(NSE_HOME, cfg, NSE_HOME, timeout=20)
    except Exception:
        # Cloud IPs are often blocked on the homepage even when the results
        # list still answers. Keep going without those cookies.
        return


def warm_bse(cfg):
    if _WARMED["bse"]:
        return
    _WARMED["bse"] = True
    try:
        http_get(BSE_HOME, cfg, BSE_HOME, timeout=20)
    except Exception:
        return


def _parse_day(value):
    text = str(value or "").strip()
    if not text or text in ("-", "NA", "None", "nan"):
        return None
    if len(text) >= 10 and text[4] == "-":
        stamp = pd.to_datetime(text, errors="coerce")
    else:
        stamp = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if stamp is None or pd.isna(stamp):
        stamp = pd.to_datetime(text, errors="coerce")
    if stamp is None or pd.isna(stamp):
        return None
    return pd.Timestamp(stamp).normalize()


def _num(value):
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text in ("", "-", "NA", "N/A", "None", "nan", "INF"):
        return None
    try:
        num = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _frame_label(end, quarterly):
    end = _parse_day(end)
    if end is None:
        return ""
    year = int(end.year)
    if quarterly:
        quarter = (int(end.month) - 1) // 3 + 1
        return "CY%dQ%d" % (year, quarter)
    return "CY%d" % year


def parse_contexts(text):
    """Map context id to (start, end, dimensional)."""
    out = {}
    for match in re.finditer(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', text, re.S):
        body = match.group(2)
        start = re.search(r"<xbrli:startDate>([^<]+)</xbrli:startDate>", body)
        end = re.search(r"<xbrli:endDate>([^<]+)</xbrli:endDate>", body)
        instant = re.search(r"<xbrli:instant>([^<]+)</xbrli:instant>", body)
        dimensional = "xbrldi:" in body or "explicitMember" in body
        start_d = _parse_day(start.group(1) if start else None)
        if start_d is None and instant:
            start_d = _parse_day(instant.group(1))
        end_d = _parse_day(end.group(1) if end else (instant.group(1) if instant else None))
        out[match.group(1)] = (start_d, end_d, dimensional)
    return out


def parse_units(text):
    """Map unit id to an ISO currency code when the unit is a money measure."""
    out = {}
    for match in re.finditer(r'<xbrli:unit id="([^"]+)">(.*?)</xbrli:unit>', text, re.S):
        body = match.group(2)
        measure = re.search(r"<xbrli:measure>([^<]+)</xbrli:measure>", body)
        if not measure:
            continue
        token = measure.group(1).split(":")[-1].strip().upper()
        out[match.group(1)] = token
    return out


def iter_xbrl_facts(text):
    """Yield (local_name, context_id, unit_id, value) for financial facts."""
    pattern = re.compile(
        r"<([A-Za-z0-9_-]+:)?([A-Za-z0-9]+)([^>]*)>([^<]*)</(?:[A-Za-z0-9_-]+:)?\2>"
    )
    for prefix, name, attrs, raw in pattern.findall(text):
        if prefix and "fin" not in prefix:
            continue
        ctx = re.search(r'contextRef="([^"]+)"', attrs)
        unit = re.search(r'unitRef="([^"]+)"', attrs)
        yield name, (ctx.group(1) if ctx else ""), (unit.group(1) if unit else ""), raw.strip()



def overlay_reporting_period_dates(contexts, facts):
    """Prefer the stated reporting period over the raw xbrli start and end dates."""
    starts = {ctx: _parse_day(raw) for ctx, _unit, raw in facts.get("DateOfStartOfReportingPeriod", [])}
    ends = {ctx: _parse_day(raw) for ctx, _unit, raw in facts.get("DateOfEndOfReportingPeriod", [])}
    out = dict(contexts)
    for cid, (start, end, dim) in contexts.items():
        ns = starts.get(cid)
        ne = ends.get(cid)
        if ns is not None or ne is not None:
            out[cid] = (ns or start, ne or end, dim)
    return out


def pick_context(contexts, target_start, target_end):
    """Choose the non-segment context for this filing's period."""
    target_start = _parse_day(target_start)
    target_end = _parse_day(target_end)
    plain = [(cid, start, end) for cid, (start, end, dim) in contexts.items() if not dim]
    if target_start is not None and target_end is not None:
        matched = [item for item in plain if item[1] == target_start and item[2] == target_end]
        if matched:
            for item in matched:
                if item[0] == "OneD":
                    return item[0]
            return matched[0][0]
    for cid, _start, _end in plain:
        if cid == "OneD":
            return cid
    return plain[0][0] if plain else None


def _fact_map(text):
    facts = {}
    for name, ctx, unit, raw in iter_xbrl_facts(text):
        facts.setdefault(name, []).append((ctx, unit, raw))
    return facts


def _value_on(facts, names, context_id, numeric=True):
    for name in names:
        for ctx, _unit, raw in facts.get(name, []):
            if context_id and ctx != context_id:
                continue
            if numeric:
                num = _num(raw)
                if num is not None:
                    return num
            elif raw:
                return raw
    return None


def _value_any_context(facts, names, allowed_ctx, numeric=True):
    for name in names:
        for ctx, _unit, raw in facts.get(name, []):
            if allowed_ctx and ctx not in allowed_ctx:
                continue
            if numeric:
                num = _num(raw)
                if num is not None:
                    return num
            elif raw:
                return raw
    return None


def parse_financial_xbrl(text, from_date=None, to_date=None):
    """Pull revenue, profit, EPS and cash flow (when present) from one filing."""
    if not text or ("xbrli" not in text and "in-bse-fin" not in text):
        return None
    contexts = parse_contexts(text)
    units = parse_units(text)
    facts = _fact_map(text)
    if not facts:
        return None
    # Year-end filings often give OneD and FourD the same xbrli dates (the
    # last quarter). DateOfStartOfReportingPeriod on FourD is the financial
    # year start and that is the context with the full-year totals.
    contexts = overlay_reporting_period_dates(contexts, facts)
    ctx_id = pick_context(contexts, from_date, to_date)
    allowed = set()
    if ctx_id:
        allowed.add(ctx_id)
    # Cash flow on an annual filing is often tagged on FourD with the same dates.
    if ctx_id and ctx_id in contexts:
        start, end, _dim = contexts[ctx_id]
        for cid, (st, en, dim) in contexts.items():
            if not dim and st == start and en == end:
                allowed.add(cid)
    if not allowed:
        allowed = {cid for cid, (_s, _e, dim) in contexts.items() if not dim}

    def pick(names, numeric=True):
        val = _value_on(facts, names, ctx_id, numeric=numeric) if ctx_id else None
        if val is not None:
            return val
        return _value_any_context(facts, names, allowed, numeric=numeric)

    currency = pick(CURRENCY_TAGS, numeric=False)
    if currency:
        currency = str(currency).strip().upper()
        if currency in ("RS", "RS.", "INR=X"):
            currency = "INR"
    if not currency:
        for name in REVENUE_TAGS:
            for c, unit, _raw in facts.get(name, []):
                if c in allowed and unit in units and units[unit] in ("INR", "USD", "EUR", "GBP"):
                    currency = units[unit]
                    break
    revenue = pick(REVENUE_TAGS)
    net_income = pick(NET_INCOME_TAGS)
    eps = pick(EPS_TAGS)
    if revenue is None and net_income is None and eps is None:
        return None
    paidup = pick(PAIDUP_TAGS)
    face = pick(FACE_TAGS)
    shares = None
    if paidup is not None and face is not None and face > 0:
        shares = paidup / face
    capex = pick(CAPEX_TAGS)
    if capex is not None:
        capex = abs(capex)
    start = from_date
    end = to_date
    if ctx_id and ctx_id in contexts:
        start = contexts[ctx_id][0] or start
        end = contexts[ctx_id][1] or end
    return {
        "from": _parse_day(start),
        "end": _parse_day(end),
        "revenue": revenue,
        "net_income": net_income,
        "eps": eps,
        "gross_profit": pick(GROSS_PROFIT_TAGS),
        "op_income": pick(OP_INCOME_TAGS),
        "equity": pick(EQUITY_TAGS),
        "debt": None,
        "ocf": pick(OCF_TAGS),
        "capex": capex,
        "dps": None,
        "shares": shares,
        "currency": currency or "INR",
    }


def filing_row(ticker, parsed, quarterly, source, filed=None):
    if not parsed or parsed.get("end") is None:
        return None
    end = parsed["end"]
    filed_day = _parse_day(filed)
    if filed_day is None:
        filed_day = end + pd.Timedelta(days=45)
    return {
        "ticker": ticker,
        "frame": _frame_label(end, quarterly),
        "end": end.strftime("%Y-%m-%d"),
        "filed": filed_day.strftime("%Y-%m-%d"),
        "revenue": parsed.get("revenue"),
        "net_income": parsed.get("net_income"),
        "eps": parsed.get("eps"),
        "gross_profit": parsed.get("gross_profit"),
        "op_income": parsed.get("op_income"),
        "equity": parsed.get("equity"),
        "debt": parsed.get("debt"),
        "ocf": parsed.get("ocf"),
        "capex": parsed.get("capex"),
        "dps": parsed.get("dps"),
        "shares": parsed.get("shares"),
        "source": source,
        "currency": parsed.get("currency") or "INR",
    }


def is_consolidated(item):
    text = str((item or {}).get("consolidated") or (item or {}).get("Consolidation") or "").lower()
    return text.startswith("consol")


def select_filings(items, quarterly, limit):
    """Newest consolidated filing per period, then standalone if that is all we have."""
    ranked = []
    for item in items or []:
        period = str(item.get("period") or "").lower()
        if quarterly and period and "annual" in period:
            continue
        if not quarterly and period and "quarter" in period:
            continue
        end = _parse_day(item.get("toDate") or item.get("todate") or item.get("ToDate"))
        start = _parse_day(item.get("fromDate") or item.get("fromdate") or item.get("FromDate"))
        xbrl = (item.get("xbrl") or item.get("XBRL") or item.get("xbrlUrl") or "").strip()
        if end is None or not xbrl:
            continue
        ranked.append((end, 1 if is_consolidated(item) else 0, start, xbrl, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    seen = set()
    out = []
    for end, _consol, start, xbrl, item in ranked:
        key = end.strftime("%Y-%m-%d")
        if key in seen:
            continue
        seen.add(key)
        out.append((start, end, xbrl, item))
        if len(out) >= int(limit):
            break
    return out


def _as_list(payload):
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if payload.get("msg") and not payload.get("data"):
            return []
        for key in ("data", "Table", "Table1", "results", "Results"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
    return []


def nse_list_results(symbol, period, cfg):
    """Return filing dicts for one symbol and period (Quarterly or Annual)."""
    warm_nse(cfg)
    symbol = quote(str(symbol or "").strip().upper(), safe="")
    url = "%s?index=equities&symbol=%s&period=%s" % (NSE_RESULTS, symbol, period)
    resp = http_get(url, cfg, NSE_FILINGS_REFERER)
    try:
        payload = resp.json()
    except ValueError as exc:
        raise netutil.PermanentError("NSE results list was not JSON") from exc
    items = _as_list(payload)
    today = dt.date.today()
    start = (today.replace(year=today.year - 4)).strftime("%d-%m-%Y")
    end = today.strftime("%d-%m-%Y")
    dated = "%s?index=equities&symbol=%s&period=%s&from_date=%s&to_date=%s" % (
        NSE_RESULTS, symbol, period, start, end,
    )
    try:
        extra = _as_list(http_get(dated, cfg, NSE_FILINGS_REFERER).json())
    except Exception:
        extra = []
    seen = set()
    out = []
    for item in list(items) + list(extra):
        if not isinstance(item, dict):
            continue
        key = (
            item.get("toDate"), item.get("fromDate"),
            item.get("consolidated"), item.get("xbrl"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _download_xbrl(url, cfg, referer):
    if not url:
        return ""
    resp = http_get(url, cfg, referer, timeout=40)
    return resp.text or ""


def _bundle_from_filings(ticker, quarterly_items, annual_items, cfg, source, referer):
    spec = settings(cfg)
    rows_q, rows_a = [], []
    currencies = []
    newest = None
    for quarterly, items, dest, cap in (
        (True, quarterly_items, rows_q, spec["xbrl_quarters"]),
        (False, annual_items, rows_a, spec["xbrl_annuals"]),
    ):
        for start, end, xbrl, item in select_filings(items, quarterly, cap):
            text = _download_xbrl(xbrl, cfg, referer)
            if spec["xbrl_pause"]:
                time.sleep(spec["xbrl_pause"])
            parsed = parse_financial_xbrl(text, start, end)
            row = filing_row(
                ticker, parsed, quarterly, source,
                filed=item.get("filingDate") or item.get("broadCastDate"),
            )
            if not row:
                continue
            dest.append(row)
            if row.get("currency"):
                currencies.append(row["currency"])
            end_ts = _parse_day(row["end"])
            if end_ts is not None and (newest is None or end_ts > newest):
                newest = end_ts
    if not rows_q and not rows_a:
        return None
    if newest is not None:
        age = (pd.Timestamp.now().normalize() - newest).days
        if age > spec["max_age_days"]:
            # The structured list is still answering, but the newest period is
            # too old (seen after NSE moved later results into PDF integrated
            # filings). Treat as empty so BSE or Yahoo can try.
            return None
    currency = next((c for c in currencies if c), "INR")
    info = {
        "ticker": ticker,
        "source": source,
        "financial_currency": currency,
        "company": "",
    }
    return {
        "info": info,
        "annual": rows_a,
        "quarters": rows_q,
        "earn": [],
        "symbol": ticker,
        "source": source,
        "currency": currency,
    }


def fetch_nse_statements(symbol, cfg, ticker=None):
    """Download rupee statements for one NSE symbol. None if nothing useful."""
    symbol = str(symbol or "").strip().upper()
    ticker = str(ticker or symbol).strip().upper()
    if not symbol:
        return None
    quarterly = nse_list_results(symbol, "Quarterly", cfg)
    annual = nse_list_results(symbol, "Annual", cfg)
    if not quarterly and not annual:
        return None
    return _bundle_from_filings(
        ticker, quarterly, annual, cfg, "NSE", NSE_FILINGS_REFERER,
    )


def walk_xbrl_links(obj, found=None):
    if found is None:
        found = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            if str(key).lower() in ("xbrl", "xbrlurl", "xbrllink", "xmlurl") and isinstance(val, str):
                if val.startswith("http") and val not in found:
                    found.append(val)
            else:
                walk_xbrl_links(val, found)
    elif isinstance(obj, list):
        for item in obj:
            walk_xbrl_links(item, found)
    elif isinstance(obj, str) and obj.startswith("http") and obj.lower().endswith(".xml"):
        if obj not in found:
            found.append(obj)
    return found


def parse_bse_result_tables(payload, ticker):
    """Best-effort read of BSE JSON tables that already contain numbers."""
    rows_q, rows_a = [], []
    items = _as_list(payload)
    if not items and isinstance(payload, dict):
        items = []
        for val in payload.values():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                items.extend(val)
    for item in items:
        if not isinstance(item, dict):
            continue
        end = _parse_day(
            item.get("toDate") or item.get("To_Date") or item.get("resultDate")
            or item.get("QtrDt") or item.get("PeriodEnd") or item.get("year_ended")
        )
        revenue = _num(
            item.get("Revenue") or item.get("TotalIncome") or item.get("Sales")
            or item.get("IncomeFromOperations") or item.get("revenue")
        )
        profit = _num(
            item.get("NetProfit") or item.get("PAT") or item.get("ProfitAfterTax")
            or item.get("net_income") or item.get("Profit")
        )
        eps = _num(item.get("EPS") or item.get("DilutedEPS") or item.get("eps"))
        if end is None or (revenue is None and profit is None and eps is None):
            continue
        period = str(item.get("period") or item.get("Period") or item.get("Type") or "")
        quarterly = "annual" not in period.lower() and "year" not in period.lower()
        parsed = {
            "end": end,
            "from": None,
            "revenue": revenue,
            "net_income": profit,
            "eps": eps,
            "gross_profit": None,
            "op_income": None,
            "equity": None,
            "debt": None,
            "ocf": _num(item.get("OCF") or item.get("OperatingCashFlow")),
            "capex": None,
            "dps": None,
            "shares": None,
            "currency": "INR",
        }
        row = filing_row(ticker, parsed, quarterly, "BSE")
        if not row:
            continue
        (rows_q if quarterly else rows_a).append(row)
    return rows_q, rows_a


def fetch_bse_payloads(code, cfg):
    warm_bse(cfg)
    code = str(code or "").strip()
    if not code:
        return []
    urls = (
        "%s/ResultsComparison/w?scripcode=%s" % (BSE_API, code),
        "%s/TabResultsNew/w?scripcode=%s&tabtype=RESULT" % (BSE_API, code),
        "%s/FinancialsNew/w?scripcode=%s&resulttype=Q" % (BSE_API, code),
        "%s/Corpforthresults/w?scripcode=%s" % (BSE_API, code),
    )
    out = []
    last_err = None
    for url in urls:
        try:
            resp = http_get(url, cfg, BSE_HOME)
        except Exception as exc:
            last_err = exc
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        out.append(payload)
    if not out and last_err is not None:
        raise last_err
    return out


def fetch_bse_statements(code, cfg, ticker=None):
    """Download rupee statements for one BSE scrip code. None if nothing useful."""
    ticker = str(ticker or code or "").strip().upper()
    payloads = fetch_bse_payloads(code, cfg)
    if not payloads:
        return None
    rows_q, rows_a = [], []
    xbrl_items = []
    for payload in payloads:
        q, a = parse_bse_result_tables(payload, ticker)
        rows_q.extend(q)
        rows_a.extend(a)
        for link in walk_xbrl_links(payload):
            xbrl_items.append({
                "toDate": None,
                "fromDate": None,
                "consolidated": "Consolidated",
                "xbrl": link,
                "period": "",
            })
    if xbrl_items and not rows_q and not rows_a:
        return _bundle_from_filings(
            ticker, xbrl_items, [], cfg, "BSE", BSE_HOME,
        )
    if not rows_q and not rows_a:
        return None
    spec = settings(cfg)
    newest = None
    for row in rows_q + rows_a:
        end_ts = _parse_day(row.get("end"))
        if end_ts is not None and (newest is None or end_ts > newest):
            newest = end_ts
    if newest is not None:
        age = (pd.Timestamp.now().normalize() - newest).days
        if age > spec["max_age_days"]:
            return None
    info = {"ticker": ticker, "source": "BSE", "financial_currency": "INR", "company": ""}
    return {
        "info": info,
        "annual": rows_a,
        "quarters": rows_q,
        "earn": [],
        "symbol": ticker,
        "source": "BSE",
        "currency": "INR",
    }


def newest_period_end(bundle):
    newest = None
    if not bundle:
        return None
    for key in ("annual", "quarters"):
        for row in bundle.get(key) or []:
            end = _parse_day(row.get("end"))
            if end is not None and (newest is None or end > newest):
                newest = end
    return newest
