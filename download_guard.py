"""Keep a failed or interrupted India download from destroying saved work.

A file is written to the side and swapped in only when the write finishes.
Two jobs on the same machine do not download the same thing at once.
A source that keeps failing is left alone for a few hours.
A job that saves nothing several times in a row stops and says a person should look.

This does not fix a bad login, a blocked site, or a source that stays down.
The NSE, BSE, Screener, and Yahoo sources and the daily clock are unchanged.
"""
import json
import os
import tempfile
import time


LEDGER_NAME = "download_ledger.json"
DEFAULTS = {
    "provider_fail_limit": 3,
    "provider_cooldown_hours": 6,
    "stall_runs": 3,
    "stall_cooldown_hours": 6,
    "statement_hard_fail_after": 5,
    "incomplete_price_bars": 20,
    "lock_stale_minutes": 150,
}


class JobBusy(Exception):
    """Another download of this kind is already running."""


class CacheUnreadable(Exception):
    """A saved file is there but cannot be read. It was not replaced."""


def settings(cfg):
    raw = (cfg or {}).get("download_guard") or {}
    out = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        try:
            value = type(default)(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        if value < 1 and key != "incomplete_price_bars":
            value = default
        out[key] = value
    if out["incomplete_price_bars"] < 1:
        out["incomplete_price_bars"] = DEFAULTS["incomplete_price_bars"]
    return out


def _pid_alive(pid):
    if not pid or int(pid) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    else:
        return True


class JobLock:
    """One lock file per job. A stale lock is taken. A live one refuses."""

    def __init__(self, path, stale_seconds, clock=None, pid_alive=None):
        self.path = path
        self.stale_seconds = float(stale_seconds)
        self.clock = clock or time.time
        self.pid_alive = pid_alive or _pid_alive
        self.held = False

    def acquire(self):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if self._stale():
                    try:
                        os.remove(self.path)
                    except OSError:
                        raise JobBusy("Another download is already running.")
                    continue
                raise JobBusy("Another download is already running. This start did not download.")
            else:
                payload = json.dumps({"pid": os.getpid(), "started": self.clock()}).encode("utf-8")
                os.write(fd, payload)
                os.close(fd)
                self.held = True
                return self

    def _stale(self):
        try:
            with open(self.path) as handle:
                data = json.load(handle)
        except Exception:
            return True
        try:
            started = float(data.get("started") or 0)
        except (TypeError, ValueError):
            return True
        if self.clock() - started > self.stale_seconds:
            return True
        return not self.pid_alive(data.get("pid"))

    def release(self):
        if self.held:
            self.held = False
            try:
                os.remove(self.path)
            except OSError:
                pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def atomic_write_bytes(path, data):
    """Swap the file in only after the bytes are on disk. A failure keeps the old file."""
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_df(path, frame, compression=None):
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=folder)
    os.close(fd)
    try:
        frame.to_csv(tmp, index=False, compression=compression)
        with open(tmp, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path, default):
    """Read JSON. A broken file is kept beside it as .bad and the default is used."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return default
    try:
        with open(path) as handle:
            data = json.load(handle)
    except Exception:
        bad = path + ".bad"
        try:
            os.replace(path, bad)
        except OSError:
            pass
        return default
    return data


def atomic_write_json(path, data):
    atomic_write_text(path, json.dumps(data, indent=1, sort_keys=True))


def empty_ledger():
    return {
        "providers": {},
        "unavailable": {},
        "incomplete": {},
        "stalls": {},
        "needs_person": {},
    }


def load_ledger(cache):
    data = read_json(os.path.join(cache, LEDGER_NAME), empty_ledger())
    if not isinstance(data, dict):
        return empty_ledger()
    base = empty_ledger()
    for key in base:
        if isinstance(data.get(key), dict):
            base[key] = data[key]
    return base


def save_ledger(cache, ledger):
    os.makedirs(cache, exist_ok=True)
    atomic_write_json(os.path.join(cache, LEDGER_NAME), ledger)


def _stamp(now):
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(now))


def provider_open(ledger, name, now):
    rec = (ledger.get("providers") or {}).get(name) or {}
    until = rec.get("cooldown_until") or ""
    if until and until > _stamp(now):
        return False
    return True


def note_provider(ledger, name, ok, now, limit, cooldown_seconds, error=""):
    providers = dict(ledger.get("providers") or {})
    rec = dict(providers.get(name) or {})
    if ok:
        rec = {"fails": 0, "cooldown_until": "", "last_error": ""}
    else:
        try:
            fails = int(rec.get("fails") or 0) + 1
        except (TypeError, ValueError):
            fails = 1
        rec["fails"] = fails
        rec["last_error"] = str(error or "")[:180]
        if fails >= int(limit):
            rec["cooldown_until"] = _stamp(now + float(cooldown_seconds))
        else:
            rec["cooldown_until"] = ""
    providers[name] = rec
    ledger["providers"] = providers
    return ledger


def note_unavailable(ledger, ticker, kind, note, today, retry_after):
    key = "%s:%s" % (kind, str(ticker).strip().upper())
    book = dict(ledger.get("unavailable") or {})
    prev = book.get(key) or {}
    try:
        tries = int(prev.get("tries") or 0) + 1
    except (TypeError, ValueError):
        tries = 1
    book[key] = {
        "ticker": str(ticker).strip().upper(),
        "kind": kind,
        "tries": tries,
        "since": prev.get("since") or today,
        "last_on": today,
        "retry_after": retry_after,
        "note": str(note or "")[:180],
    }
    # Keep the file from growing without bound. The newest notes stay.
    if len(book) > 500:
        ordered = sorted(book.items(), key=lambda item: item[1].get("last_on") or "")
        book = dict(ordered[-500:])
    ledger["unavailable"] = book
    return ledger


def clear_unavailable(ledger, ticker, kind):
    key = "%s:%s" % (kind, str(ticker).strip().upper())
    book = dict(ledger.get("unavailable") or {})
    book.pop(key, None)
    ledger["unavailable"] = book
    return ledger


def unavailable_waiting(ledger, ticker, kind, today):
    key = "%s:%s" % (kind, str(ticker).strip().upper())
    rec = (ledger.get("unavailable") or {}).get(key) or {}
    after = str(rec.get("retry_after") or "")
    return bool(after) and after > today


def note_incomplete(ledger, kind, names):
    current = list((ledger.get("incomplete") or {}).get(kind) or [])
    merged = []
    seen = set()
    for name in list(names) + current:
        token = str(name).strip().upper()
        if token and token not in seen:
            seen.add(token)
            merged.append(token)
    incomplete = dict(ledger.get("incomplete") or {})
    incomplete[kind] = merged[:200]
    ledger["incomplete"] = incomplete
    return ledger


def note_progress(ledger, kind, saved, attempted, now, stall_limit, cooldown_seconds):
    """Count runs that tried and saved nothing. A save clears the count.

    Returns a sentence when a person should look, else "".
    """
    stalls = dict(ledger.get("stalls") or {})
    needs = dict(ledger.get("needs_person") or {})
    rec = dict(stalls.get(kind) or {})
    if not attempted:
        ledger["stalls"] = stalls
        return ""
    if saved:
        rec = {"runs": 0, "cooldown_until": ""}
        needs.pop(kind, None)
    else:
        try:
            runs = int(rec.get("runs") or 0) + 1
        except (TypeError, ValueError):
            runs = 1
        rec["runs"] = runs
        if runs >= int(stall_limit):
            rec["cooldown_until"] = _stamp(now + float(cooldown_seconds))
            needs[kind] = (
                "%s saved nothing on %d runs in a row. Left alone until %s. "
                "This does not fix a source that is down or a login that failed."
                % (kind, runs, rec["cooldown_until"])
            )
    stalls[kind] = rec
    ledger["stalls"] = stalls
    ledger["needs_person"] = needs
    return needs.get(kind) or ""


def blocked_reason(ledger, kind, now):
    rec = (ledger.get("stalls") or {}).get(kind) or {}
    until = rec.get("cooldown_until") or ""
    if until and until > _stamp(now):
        return (ledger.get("needs_person") or {}).get(kind) or (
            "%s is paused until %s after runs that saved nothing." % (kind, until)
        )
    return ""


def person_notes(ledger, now):
    lines = []
    for kind in (ledger.get("needs_person") or {}):
        reason = blocked_reason(ledger, kind, now)
        if reason:
            lines.append(reason)
    return " ".join(lines)


def session_status(nse_bars, bse_bars, index_bars):
    """A day is complete only when the NSE file had bars.

    Bars from BSE or the index alone are partial. The day stays pending so the
    NSE file is asked again. An empty day is empty, not done.
    """
    if int(nse_bars or 0) > 0:
        return "complete"
    if int(bse_bars or 0) > 0 or int(index_bars or 0) > 0:
        return "partial"
    return "empty"


def price_history_status(bar_count, market_days, minimum):
    """none, incomplete, or ok. A short saved history is kept either way."""
    count = int(bar_count or 0)
    if count <= 0:
        return "none"
    if market_days >= int(minimum) and count < int(minimum):
        return "incomplete"
    return "ok"
