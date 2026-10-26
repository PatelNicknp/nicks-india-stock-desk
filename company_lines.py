"""One plain line about what each company does, shown next to every stock chart.

Sources, first good answer wins:
  1. Yahoo business summary. The backfill already reads Yahoo's profile for each
     name, so the summary rides along in cache/yahoo_info.csv at no extra request.
  2. cache/company_profiles.csv, filled by earlier runs from Yahoo or Screener.in.
  3. Screener.in "About" text, then NSE and BSE for industry and sector.
  4. A line built from the industry and sector, so no stock is ever blank.

The summary is cut to one short line with fixed rules. No AI service is used.
"""
import html as html_lib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd

MAX_WORDS = 20
SUMMARY_KEEP = 320
PROFILE_COLS = ["ticker", "summary", "sector", "industry", "source", "fetched_on"]
LINE_COLS = ["ticker", "line", "source", "as_of"]

# Abbreviations that end with a dot but do not end a sentence.
_ABBR = (
    "Ltd", "Pvt", "Co", "Inc", "Corp", "No", "Nos", "St", "Mr", "Mrs", "Dr", "Jr", "Sr",
    "Bros", "vs", "etc", "approx", "Govt", "Intl", "Mfg", "Est", "Rs", "Ind", "Engg",
)
_ABBR_RE = re.compile(r"\b(?:%s)\.$" % "|".join(_ABBR), re.I)
_INITIAL_RE = re.compile(r"(?:\b[A-Z]\.)+$")

# Verb phrases that start the useful part of a summary, matched after the name.
# Each maps to the plain words that replace it. Longest first.
_VERBS = [
    (r"(?:is|are) (?:primarily |principally |mainly )?engaged in the (?:business of )?(?:manufactur(?:e|ing)) and (?:sale|selling|marketing|trading) of", "Makes and sells"),
    (r"engages? in the (?:business of )?(?:manufactur(?:e|ing)) and (?:sale|selling|marketing|trading) of", "Makes and sells"),
    (r"(?:is|are) (?:primarily |principally |mainly )?engaged in the (?:business of )?(?:manufactur(?:e|ing)|production) of", "Makes"),
    (r"engages? in the (?:business of )?(?:manufactur(?:e|ing)|production) of", "Makes"),
    (r"(?:is|are) (?:primarily |principally |mainly )?engaged in the (?:business of )?(?:provision|providing) of", "Provides"),
    (r"engages? in the (?:business of )?(?:provision|providing) of", "Provides"),
    (r"(?:is|are) (?:primarily |principally |mainly )?engaged in the (?:business of )?(?:trading|trade) (?:of|in)", "Trades"),
    (r"(?:is|are) (?:primarily |principally |mainly )?engaged in the business of", "Works in"),
    (r"(?:is|are) (?:primarily |principally |mainly )?engaged in", "Works in"),
    (r"engages? (?:primarily |principally |mainly )?in the business of", "Works in"),
    (r"engages? (?:primarily |principally |mainly )?in", "Works in"),
    (r"(?:is|are) (?:primarily |principally |mainly )?involved in", "Works in"),
    (r"manufactures?,? (?:and |& )?(?:sells|markets|trades|distributes|exports)", "Makes and sells"),
    (r"manufactures?", "Makes"),
    (r"produces?", "Makes"),
    (r"provides?", "Provides"),
    (r"offers?", "Offers"),
    (r"(?:operates?|functions?|serves?) as an", "An"),
    (r"(?:operates?|functions?|serves?) as a", "A"),
    (r"operates? (?:primarily |mainly )?in", "Works in"),
    (r"operates?", "Runs"),
    (r"develops?", "Develops"),
    (r"designs?", "Designs"),
    (r"distributes?", "Distributes"),
    (r"markets?", "Sells"),
    (r"sells?", "Sells"),
    (r"trades? in", "Trades"),
    (r"trades?", "Trades"),
    (r"owns?", "Owns"),
    (r"builds?", "Builds"),
    (r"constructs?", "Builds"),
    (r"generates?", "Generates"),
    (r"invests? in", "Invests in"),
    (r"focuse?s? on", "Focuses on"),
    (r"(?:is|are|was|were) (?:one of the |among the )?(?:leading |largest )?an", "An"),
    (r"(?:is|are|was|were) a", "A"),
]
_VERB_RES = [(re.compile(r"(?:^|[\s,])(" + pat + r")(?=[\s,]|$)", re.I), rep) for pat, rep in _VERBS]

_SUBSIDIARY_RE = re.compile(
    r",?\s*(?:together|along) with its (?:subsidiaries|subsidiary|associates|joint ventures|group companies)"
    r"(?:(?:,| and) (?:its )?(?:subsidiaries|associates|joint ventures|affiliates))*,?", re.I)
_THROUGH_RE = re.compile(r",?\s*through its (?:subsidiaries|subsidiary|group companies)[^,]*,", re.I)
_AND_SUBS_RE = re.compile(r"\s+and its (?:subsidiaries|subsidiary)\b", re.I)
_SINCE_RE = re.compile(r"^(?:Incorporated|Established|Founded|Set up|Started|Formed)(?: in| on)? [^,]{0,40},\s*", re.I)
_PAREN_RE = re.compile(r"\s*\([^()]*\)")
_REF_RE = re.compile(r"\[\d+\]")
_TAIL_DROP = {
    "and", "or", "of", "the", "in", "for", "with", "to", "a", "an", "including", "such", "as", "its", "their",
    "through", "on", "at", "by", "from", "into", "that", "which", "is", "are", "&", "under", "like", "other",
}
_PLAIN = [
    (re.compile(r"^Works in (?:the )?(?:trading|trade|dealing) (?:of|in) ", re.I), "Trades "),
    (re.compile(r"^Works in (?:the )?(?:granting|grant|provision|providing|rendering) of ", re.I), "Provides "),
    (re.compile(r"^Works in (?:the )?(?:manufacture|manufacturing|production) and (?:sale|selling|marketing|trading) of ", re.I), "Makes and sells "),
    (re.compile(r"^Works in (?:the )?(?:manufacture|manufacturing|production) of ", re.I), "Makes "),
    (re.compile(r"^Works in (?:the )?(?:sale|selling|marketing) and (?:service|servicing) of ", re.I), "Sells and services "),
    (re.compile(r"^Works in (?:the )?(?:sale|selling|marketing|distribution) of ", re.I), "Sells "),
    (re.compile(r"^Works in (?:the )?(?:development|developing) of ", re.I), "Develops "),
    (re.compile(r"^Makes and sells,?(?: (?:and |& )?(?:sells|markets|trades(?: in)?|distributes|exports|supplies),?)+", re.I), "Makes and sells"),
    (re.compile(r"^(Makes and sells|Makes|Sells|Trades|Provides|Offers) (?:in|of) ", re.I), r"\1 "),
    (re.compile(r"\s*\b(?:primarily|principally|mainly|predominantly)\b", re.I), ""),
    (re.compile(r"\s*[\u2014\u2013]\s*"), ", "),
    (re.compile(r"\s*;\s*"), ", "),
    (re.compile(r"\binternationally\b", re.I), "abroad"),
    (re.compile(r"\bin India and abroad\b", re.I), "in India and abroad"),
    (re.compile(r"\bthe Republic of India\b"), "India"),
    (re.compile(r"\butili[sz]e\b", re.I), "use"),
    (re.compile(r"\bcommence[sd]?\b", re.I), "started"),
    (re.compile(r"\bvarious\b", re.I), "many"),
]


def _clean(text):
    t = html_lib.unescape(str(text or ""))
    t = re.sub(r"<[^>]+>", " ", t)
    t = _REF_RE.sub("", t)
    t = re.sub(r"\*+", " ", t)
    t = t.replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def first_sentence(text):
    """The first sentence, skipping dots in Ltd., Co., initials, and decimals."""
    t = _clean(text)
    if not t:
        return ""
    for m in re.finditer(r"[.!?](?=\s+[A-Z0-9\"']|$)", t):
        head = t[: m.end()]
        if _ABBR_RE.search(head) or _INITIAL_RE.search(head):
            continue
        return head.strip()
    return t


def _strip_subject(s, company=""):
    """Drop 'X Limited, together with its subsidiaries,' and keep what it does."""
    s = _SUBSIDIARY_RE.sub("", s)
    s = _THROUGH_RE.sub(" ", s)
    s = _AND_SUBS_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    best = None
    for rx, rep in _VERB_RES:
        m = rx.search(s)
        if not m:
            continue
        start = m.start(1)
        # The name in front should be short. A long prefix means the verb is mid-sentence.
        if len(s[:start].split()) > 14:
            continue
        if best is None or start < best[0] or (start == best[0] and m.end(1) > best[1]):
            best = (start, m.end(1), rep)
    if best is None:
        name = str(company or "").strip()
        if name and s.lower().startswith(name.lower()):
            s = s[len(name):].lstrip(" ,")
        return s
    start, end, rep = best
    rest = s[end:]
    if rest.startswith(",") and not rep.endswith(" ") and rep[0].isupper() and rep not in ("A", "An"):
        return rep + rest.rstrip()
    rest = rest.lstrip(" ,")
    if rep.endswith(" "):
        return rep + rest
    return rep + " " + rest


def _trim_tail(words):
    while words and (words[-1].lower().strip(",.") in _TAIL_DROP or words[-1] in (",", "-")):
        words.pop()
    if words:
        words[-1] = words[-1].rstrip(",;:-")
    return words


_PLACES_RE = re.compile(r",?\s+(?:in|across|throughout|to customers in)\s+(?:the\s+)?(?:[A-Z][\w.'-]*|India|abroad)(?:[\s,]+(?:and\s+)?(?:the\s+)?(?:[A-Z][\w.'-]*|abroad|internationally|worldwide))*\s*$")


def _cut(s, max_words=MAX_WORDS):
    words = s.split()
    if len(words) <= max_words:
        return s.rstrip(" ,;:")
    # A long list of countries at the end goes first. What the company does matters more.
    short = _PLACES_RE.sub("", s).rstrip(" ,;:")
    if short != s and len(short.split()) >= 4:
        s = short
        words = s.split()
        if len(words) <= max_words:
            return s
    room = words[: max_words - 2]
    commas = [i for i, w in enumerate(room) if w.endswith(",")]
    if commas and commas[-1] >= 5:
        head = _trim_tail(room[: commas[-1] + 1])
        return " ".join(head) + " and more"
    return " ".join(_trim_tail(words[:max_words]))


def shorten(summary, company="", max_words=MAX_WORDS):
    """Business summary to one plain line of about 20 words. Empty in, empty out."""
    s = first_sentence(summary)
    if not s:
        return ""
    s = _PAREN_RE.sub("", s)
    s = _SINCE_RE.sub("", s)
    s = s.rstrip(" .!?")
    s = _strip_subject(s, company)
    for rx, rep in _PLAIN:
        s = rx.sub(rep, s)
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    s = _cut(s, max_words)
    if not s:
        return ""
    s = s[0].upper() + s[1:]
    if len(s.split()) < 3:
        return ""
    return s.rstrip(".") + "."


def _nice(value):
    v = str(value or "").strip()
    if v.lower() in ("", "nan", "none", "-", "na", "n/a"):
        return ""
    return v


def fallback_line(industry="", sector="", isin="", exchange=""):
    """Plain line from the industry and sector. Never empty."""
    ind = _nice(industry)
    sec = _nice(sector)
    if str(isin or "").upper().startswith("INF"):
        return "A fund, such as an ETF, that trades on the stock exchange."
    if ind and sec and ind.lower() != sec.lower():
        return "A company in %s (%s sector)." % (ind, sec)
    if ind or sec:
        word = ind or sec
        return "A company in the %s sector." % word if "sector" not in word.lower() else "A company in the %s." % word
    where = "BSE" if str(exchange or "").upper() == "BSE" else "the stock exchange"
    return "A company listed on %s." % where


def keep_summary(text):
    """What the backfill saves in yahoo_info.csv: the first sentence, capped."""
    s = first_sentence(text)
    return s[:SUMMARY_KEEP]


# ---------- free sources ----------

def parse_screener_about(page):
    if not page:
        return ""
    m = re.search(r'class="sub show-more-box about"[^>]*>(.*?)</div>', page, re.S)
    if not m:
        return ""
    return _clean(m.group(1))


def fetch_screener_about(symbol, cfg=None):
    import fallback
    import india_data
    import netutil
    import requests
    safe = quote(str(symbol), safe="")
    url = "https://www.screener.in/company/%s/" % safe
    if not fallback.robots_allows(url):
        raise netutil.PermanentError("robots.txt does not allow this page")
    headers = dict(india_data.BROWSER)
    headers["Accept"] = "text/html"
    r = netutil.http_get(requests, url, headers, 20, max_tries=2, delays=(2.0, 4.0))
    about = parse_screener_about(r.text)
    return {"summary": about, "source": "Screener About"} if about else None


def fetch_nse_industry(symbol, cfg):
    import india_data
    url = "https://www.nseindia.com/api/quote-equity?symbol=%s" % quote(str(symbol), safe="")
    r = india_data.nse_get(url, cfg)
    payload = r.json()
    info = payload.get("industryInfo") or {}
    meta = payload.get("metadata") or {}
    industry = info.get("basicIndustry") or info.get("industry") or meta.get("industry") or ""
    sector = info.get("sector") or info.get("macro") or ""
    if not industry and not sector:
        return None
    return {"industry": industry, "sector": sector, "source": "NSE industry"}


def fetch_bse_industry(code, cfg):
    import india_data
    import netutil
    import requests
    code = str(code or "").strip()
    if not code.isdigit():
        return None
    url = "https://api.bseindia.com/BseIndiaAPI/api/ComHeadernew/w?quotetype=EQ&scripcode=%s&seriesid=" % code
    headers = dict(india_data.BROWSER)
    headers["Referer"] = "https://www.bseindia.com/"
    headers["Accept"] = "application/json"
    r = netutil.http_get(requests, url, headers, 15, max_tries=2, delays=(1.5, 3.0))
    if r.text.lstrip().startswith("<"):
        raise netutil.PermanentError("BSE profile page was blocked")
    p = r.json() or {}
    industry = p.get("IndustryNew") or p.get("Industry") or p.get("IGroup") or ""
    sector = p.get("Sector") or p.get("ISubGroup") or ""
    if not industry and not sector:
        return None
    return {"industry": industry, "sector": sector, "source": "BSE profile"}


# ---------- build the data file ----------

def _read(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")


def build_lines(universe, info, profiles, today=None):
    """One row per universe ticker. Real summaries first, the industry line last."""
    today = today or _today()
    info_map = {r["ticker"]: r for r in info.to_dict("records")} if len(info) and "ticker" in info.columns else {}
    prof_map = {r["ticker"]: r for r in profiles.to_dict("records")} if len(profiles) and "ticker" in profiles.columns else {}
    rows = []
    for rec in universe.to_dict("records"):
        t = str(rec.get("ticker") or "").strip()
        if not t:
            continue
        inf = info_map.get(t, {})
        prof = prof_map.get(t, {})
        company = _nice(inf.get("company")) or _nice(rec.get("company"))
        line, source, as_of = "", "", ""
        cands = []
        if _nice(inf.get("summary")):
            cands.append((inf.get("summary"), "Yahoo", inf.get("fetched_on")))
        if _nice(prof.get("summary")):
            cands.append((prof.get("summary"), prof.get("source") or "Yahoo", prof.get("fetched_on")))
        for text, src, day in cands:
            line = shorten(text, company)
            if line:
                source, as_of = src, _nice(day) or today
                break
        if not line:
            industry = _nice(inf.get("industry")) or _nice(prof.get("industry"))
            sector = _nice(inf.get("sector")) or _nice(prof.get("sector")) or _nice(rec.get("sector"))
            line = fallback_line(industry, sector, rec.get("isin"), rec.get("exchange"))
            source, as_of = "Industry fallback", today
        rows.append({"ticker": t, "line": line, "source": source, "as_of": as_of})
    return pd.DataFrame(rows, columns=LINE_COLS)


def write_lines(root, today=None):
    data = os.path.join(root, "data")
    cache = os.path.join(root, "cache")
    universe = _read(os.path.join(data, "universe.csv"))
    if len(universe) == 0:
        return None
    info = _read(os.path.join(cache, "yahoo_info.csv"))
    profiles = _read(os.path.join(cache, "company_profiles.csv"))
    out = build_lines(universe, info, profiles, today)
    out.to_csv(os.path.join(data, "company_lines.csv"), index=False)
    return out


def fill_missing(root, cfg, codes, book, limit=40, deadline=None, pause=1.0, today=None):
    """Try Screener, NSE, and BSE for names with no summary yet. Saves company_profiles.csv.

    A name that was tried is not tried again for 30 days, so each run moves on.
    """
    today = today or _today()
    cache = os.path.join(root, "cache")
    universe = _read(os.path.join(root, "data", "universe.csv"))
    info = _read(os.path.join(cache, "yahoo_info.csv"))
    profiles = _read(os.path.join(cache, "company_profiles.csv"))
    have = set()
    if len(info) and "summary" in info.columns:
        have |= set(info.loc[info["summary"].astype(str).str.strip() != "", "ticker"])
    prof_map = {r["ticker"]: r for r in profiles.to_dict("records")} if len(profiles) else {}
    for t, r in prof_map.items():
        if _nice(r.get("summary")):
            have.add(t)
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    todo = []
    for rec in universe.to_dict("records"):
        t = rec.get("ticker")
        if not t or t in have or str(rec.get("isin") or "").upper().startswith("INF"):
            continue
        old = prof_map.get(t)
        if old and str(old.get("fetched_on") or "") >= cutoff:
            continue
        todo.append(rec)
    done = 0
    for rec in todo[: int(limit)]:
        if deadline and time.time() >= deadline:
            break
        t = rec["ticker"]
        nse = str(rec.get("nse_symbol") or "").strip()
        bse = str(rec.get("bse_symbol") or "").strip()
        row = dict(prof_map.get(t) or {"ticker": t})
        row["ticker"] = t
        got = None
        code = codes.get(t) or codes.get(bse.upper()) or codes.get(str(rec.get("isin") or "").upper())
        # Screener pages use the NSE symbol, or the BSE code for BSE-only names.
        page_id = nse or code or bse or t
        for name, fn in (("Screener About", lambda: fetch_screener_about(page_id, cfg)),):
            if not book.allow(name):
                continue
            try:
                got = fn()
                if got:
                    book.ok("company_line:" + t, name, "answered")
                    break
            except Exception as exc:
                book.hit("company_line:" + t, name, "FAILED", str(exc)[:160])
        if got:
            row["summary"] = keep_summary(got["summary"])
            row["source"] = got["source"]
        inf_row = info[info["ticker"] == t] if len(info) and "ticker" in info.columns else pd.DataFrame()
        has_ind = len(inf_row) and _nice(inf_row.iloc[0].get("industry"))
        if not got and not has_ind and not _nice(row.get("industry")):
            steps = []
            if nse:
                steps.append(("NSE industry", lambda s=nse: fetch_nse_industry(s, cfg)))
            if code:
                steps.append(("BSE profile", lambda c=code: fetch_bse_industry(c, cfg)))
            for name, fn in steps:
                if not book.allow(name):
                    continue
                try:
                    ind = fn()
                except Exception as exc:
                    book.hit("company_line:" + t, name, "FAILED", str(exc)[:160])
                    continue
                if ind:
                    row["industry"] = ind["industry"]
                    row["sector"] = ind["sector"]
                    row["source"] = row.get("source") or ind["source"]
                    book.ok("company_line:" + t, name, "answered")
                    break
        row["fetched_on"] = today
        prof_map[t] = row
        done += 1
        time.sleep(pause)
    if done:
        out = pd.DataFrame(list(prof_map.values()))
        for c in PROFILE_COLS:
            if c not in out.columns:
                out[c] = ""
        out[PROFILE_COLS].sort_values("ticker").to_csv(os.path.join(cache, "company_profiles.csv"), index=False)
    return done


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    frame = write_lines(here)
    if frame is not None:
        real = int((frame["source"] != "Industry fallback").sum())
        print("company lines %d, real %d, industry fallback %d" % (len(frame), real, len(frame) - real))
