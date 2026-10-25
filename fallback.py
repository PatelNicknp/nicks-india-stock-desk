"""Try free sources in order. The first good answer wins. Later answers are compared.

Official files (NSE, BSE, RBI, MOSPI) stay ahead of websites. A big gap between
two answers is written down. The last resort is the saved copy.
"""
import time
from urllib.parse import urlparse

import requests

import india_data
import netutil


OFFICIAL_HOSTS = {
    "www.nseindia.com",
    "nsearchives.nseindia.com",
    "archives.nseindia.com",
    "www.bseindia.com",
    "www.rbi.org.in",
    "www.mospi.gov.in",
    "esankhyiki.mospi.gov.in",
    "api.worldbank.org",
    "fred.stlouisfed.org",
    "www.niftyindices.com",
    "www.fpi.nsdl.co.in",
    "www.nsdl.co.in",
}


class SourceBook:
    """Remember which sites failed so one run does not hammer a dead host."""

    def __init__(self, give_up_after=3):
        self.give_up_after = give_up_after
        self.fails = {}
        self.dead = set()
        self.rows = []

    def allow(self, name):
        return name not in self.dead

    def hit(self, field, source, status, detail, counts=True):
        self.rows.append({
            "field": field,
            "source": source,
            "status": status,
            "detail": str(detail or "")[:180],
        })
        # An empty filing is not a dead host. Only real errors retire a source.
        if counts and status in ("MISSING", "FAILED"):
            self.fails[source] = self.fails.get(source, 0) + 1
            if self.fails[source] >= self.give_up_after:
                self.dead.add(source)

    def ok(self, field, source, detail):
        self.fails[source] = 0
        self.hit(field, source, "OK", detail)


def empty(value):
    if value is None:
        return True
    if value is False:
        return True
    try:
        if hasattr(value, "__len__") and len(value) == 0:
            return True
    except TypeError:
        pass
    if isinstance(value, str) and not value.strip():
        return True
    return False


def run_chain(field, steps, cache_value=None, book=None, pause=0.0):
    """steps is a list of (source name, function). The function returns a value or raises.

    The first non-empty value is kept. Later values are only used to flag a disagreement
    when both are plain numbers. If every step fails, cache_value is returned.
    """
    book = book or SourceBook()
    chosen = None
    chosen_name = ""
    note = ""
    for name, fn in steps:
        if not book.allow(name):
            book.hit(field, name, "FAILED", "skipped after repeated failures")
            continue
        try:
            value = fn()
        except Exception as exc:
            book.hit(field, name, "FAILED", str(exc)[:160])
            if pause:
                time.sleep(pause)
            continue
        if empty(value):
            book.hit(field, name, "MISSING", "empty reply")
            if pause:
                time.sleep(pause)
            continue
        book.ok(field, name, "answered")
        if chosen is None:
            chosen = value
            chosen_name = name
        else:
            gap = number_gap(chosen, value)
            if gap is not None and gap > 0.08:
                note = (note + " " if note else "") + (
                    "%s and %s disagree (%.4g vs %.4g); kept %s."
                    % (chosen_name, name, _as_float(chosen), _as_float(value), chosen_name)
                )
        if pause:
            time.sleep(pause)
    if chosen is None and not empty(cache_value):
        book.ok(field, "cache", "used the saved copy")
        return cache_value, "cache", "Live sources failed. Showing the saved copy."
    if chosen is None:
        book.hit(field, "cache", "MISSING", "no saved copy")
        return None, "", "not available"
    return chosen, chosen_name, note.strip()


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def number_gap(a, b):
    left, right = _as_float(a), _as_float(b)
    if left is None or right is None:
        return None
    base = max(abs(left), abs(right), 1.0)
    return abs(left - right) / base


_ROBOTS = {}


def robots_allows(url, timeout=12):
    """True when robots.txt does not disallow this URL for a generic bot.

    Official market-file hosts are allowed. If a site's robots file cannot be
    read, scraping that site is skipped.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in OFFICIAL_HOSTS:
        return True
    rules = _ROBOTS.get(host)
    if rules is None:
        robots_url = "%s://%s/robots.txt" % (parsed.scheme or "https", host)
        try:
            response = requests.get(
                robots_url,
                headers={"User-Agent": india_data.BROWSER["User-Agent"]},
                timeout=timeout,
            )
            if response.status_code != 200:
                _ROBOTS[host] = False
                return False
            rules = _parse_robots(response.text)
        except Exception:
            _ROBOTS[host] = False
            return False
        _ROBOTS[host] = rules
    if rules is False:
        return False
    path = parsed.path or "/"
    for disallowed in rules:
        if disallowed and path.startswith(disallowed):
            return False
    return True


def _parse_robots(text):
    """Disallow paths for User-agent * . Other agents are ignored."""
    star = False
    paths = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            star = value == "*"
        elif key == "disallow" and star:
            paths.append(value)
    return paths


def polite_get(url, cfg, timeout=25, headers=None):
    """One GET with the browser header, backoff, and a robots check for non-official hosts."""
    if not robots_allows(url):
        raise netutil.PermanentError("robots.txt does not allow %s" % url)
    hdrs = dict(india_data.BROWSER)
    if headers:
        hdrs.update(headers)
    return india_data.nse_get(url, cfg) if "nseindia" in url else netutil.http_get(
        requests, url, hdrs, timeout, max_tries=2, delays=(1.5, 3.0)
    )
