"""Update keeper for Nick's India Stock Desk: the desk's own clock inside GitHub Actions. Standard library only.

It never downloads market data. Three commands:

    python keeper.py keeper         # keeper workflow: sleep to each slot, make it up if it did not run, verify it
    python keeper.py ensure-keeper  # end of every update and watchdog run: start a keeper if none is live
    python keeper.py guard          # first step of the update job: drop a late cron or make-up for a slot that already ran

Slots are India time (Asia/Kolkata, no daylight saving), Monday to Friday, NSE trading holidays skipped.
They match the crons in update.yml:

    08:00 IST  02:30 UTC  morning  news and FII/DII, no prices   (cron "30 2 * * 1-5")
    16:30 IST  11:00 UTC  close    the main run after the close   (cron "0 11 * * 1-5")
    18:30 IST  13:00 UTC  retry    late bhavcopy, last sessions  (cron "0 13 * * 1-5")

keeper (switch features.self_heal_keeper, settings in the keeper block of config.json). One keeper job is
always alive. It sleeps until check_after_min (10) past the next slot and checks it: if no real update
started at or after the slot, none is queued or running, and the last one started over min_gap_min (50)
minutes ago, it dispatches exactly one update with that slot's mode (reason=keeper; the guard still drops
the late cron when GitHub fires it hours later). The retry slot is made up only while price_as_of is still
older than that IST date: if the close run already brought today's prices there is nothing to retry.
At verify_after_min (45) past the slot it verifies:
    morning  every run for the slot failed -> one retry (reason=keeper_retry), then "gave up".
    close    every run failed -> one retry, then "gave up". Succeeded but price_as_of in data/meta.json is
             not that IST date -> warning only; the 18:30 IST retry slot is the second look at late data.
    retry    it is already the retry, so it is not retried again: failed or stale -> warning only.
max_tries (2) counts the slot's runs from the GitHub run list, so a restarted keeper never retries twice.
A run still going is looked at again every recheck_min (15) minutes, up to 3 hours after the slot.
A hosted job lives at most 6 hours, so after chunk_min (330) minutes the keeper dispatches the next keeper
and exits. A keeper exits without chaining when the switch is off (read live from main each wake), or when
a newer keeper is live. ensure-keeper starts one only when the switch is on and none is queued or running.

guard (scheduled runs and keeper make-ups only; manual, watchdog and keeper_retry runs are never skipped):
skip when another real update already started for the same slot. A scheduled run's slot is the time its
cron was due (GitHub often fires this repo's crons hours late); a keeper make-up's slot is the latest slot
of its mode. If the run list cannot be read, the update runs as it always did.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
IST = ZoneInfo("Asia/Kolkata")
PT = ZoneInfo("America/Los_Angeles")
WORKFLOW_FILE = "update.yml"
KEEPER_FILE = "keeper.yml"
DATA_STEP = "Update the desk"
# (IST hour, minute, mode), in day order.
SLOTS_IST = [(8, 0, "morning"), (16, 30, "close"), (18, 30, "retry")]
CRON_MODE = {"30 2 * * 1-5": "morning", "0 11 * * 1-5": "close", "0 13 * * 1-5": "retry"}
MODES = ("morning", "close", "retry")
PRICE_MODES = ("close", "retry")       # runs that must bring that IST date's prices
NO_KEEPER_RETRY = ("retry",)          # the 18:30 IST slot is already the retry of the close
LOOKBACK_MIN = 15
VERIFY_FOR_MIN = 180                  # stop re-verifying a slot whose run is still going after 3 hours
KEEPER_DEFAULTS = {"check_after_min": 10, "verify_after_min": 45, "recheck_min": 15,
                   "chunk_min": 330, "min_gap_min": 50, "max_tries": 2}
FAILED = {"failure", "timed_out"}
ACTIVE = {"queued", "in_progress", "waiting", "requested", "pending"}
NOT_A_RUN = {"cancelled", "skipped", "startup_failure", "stale"}
# NSE Capital Market trading holidays on weekdays, from NSE's own holiday list
# (nseindia.com/resources/exchange-communication-holidays, api/holiday-master?type=trading, segment CM;
# circular NSE/CMTR/71775 of 12 Dec 2025 and addendum NSE/CMTR/72260 of 12 Jan 2026 adding 15 Jan).
# Weekend-dated holidays (15 Feb, 21 Mar, 15 Aug, 8 Nov Muhurat Sunday) need no entry: weekends have no slots.
# NSE had not published 2027 by 2 Nov 2026 (it usually does in mid-December): years not in
# HOLIDAY_YEARS are treated as plain weekdays and the keeper says so in its log. Add 2027 when it is out.
NSE_HOLIDAYS = {dt.date.fromisoformat(d) for d in (
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02",
    "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
)}
HOLIDAY_YEARS = {2026}


def parse_time(s):
    if not s:
        return None
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def fmt(t):
    """'Tue 03 Nov 08:00 IST / Mon 02 Nov 18:30 PT'."""
    return "%s / %s" % (t.astimezone(IST).strftime("%a %d %b %H:%M IST"), t.astimezone(PT).strftime("%a %d %b %H:%M PT"))


def ist_date(t):
    return t.astimezone(IST).date()


def slots_for_day(day):
    """(utc_time, mode) slots for one IST calendar date. Empty on weekends."""
    if day.weekday() >= 5:
        return []
    return [(dt.datetime(day.year, day.month, day.day, h, m, tzinfo=IST).astimezone(UTC), mode)
            for h, m, mode in SLOTS_IST]


def market_slots_for_day(day):
    """Slots on an NSE trading day: weekdays minus NSE_HOLIDAYS."""
    if day in NSE_HOLIDAYS:
        return []
    return slots_for_day(day)


def last_slot_of_mode(at, mode):
    """Latest market slot of `mode` at or before `at`, looking back up to two weeks."""
    day = ist_date(at)
    for back in range(0, 15):
        due = [s for s, m in market_slots_for_day(day - dt.timedelta(days=back)) if m == mode and s <= at]
        if due:
            return due[-1]
    return None


# ---------------------------------------------------------------- cron
def _field(spec, lo, hi):
    if spec == "*":
        return set(range(lo, hi + 1))
    out = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def cron_fire_time(cron, created):
    """Latest UTC time <= created that matches a simple 'M H * * DOW' cron. None if unknown."""
    try:
        minute, hour, dom, mon, dow = cron.split()
        if dom != "*" or mon != "*":
            return None
        minutes = _field(minute, 0, 59)
        hours = _field(hour, 0, 23)
        days = {d % 7 for d in _field(dow, 0, 7)}
    except Exception:
        return None
    t = created.replace(second=0, microsecond=0)
    for _ in range(0, 60 * 24 * 7):
        if t.minute in minutes and t.hour in hours and (t.weekday() + 1) % 7 in days:
            return t
        t -= dt.timedelta(minutes=1)
    return None


# ---------------------------------------------------------------- runs
def run_start(run):
    return parse_time(run.get("run_started_at") or run.get("created_at"))


def counts_as_run(run, did_work=None):
    """A run that happened or is happening. Cancelled runs and guard-skipped runs do not count."""
    if run.get("status") in ACTIVE:
        return True
    if run.get("conclusion") in NOT_A_RUN:
        return False
    if did_work is not None and not did_work(run):
        return False
    return True


def guard_slot(event, schedule, reason, mode, created):
    """(slot, why) the run belongs to for the duplicate check, or (None, why) when it is never skipped."""
    if event == "schedule":
        fired = cron_fire_time(schedule or "", created)
        if fired is None:
            return None, "could not read the cron, run as usual"
        return fired, "cron %s was due %s" % (schedule, fmt(fired))
    if reason == "keeper":
        slot = last_slot_of_mode(created, mode if mode in MODES else "close")
        if slot is None:
            return None, "no %s slot found, run as usual" % mode
        return slot, "keeper make-up for the %s slot %s" % (mode, fmt(slot))
    return None, "manual, watchdog or retry run, never skipped"


def duplicate(me, slot, runs, did_work=None):
    """(skip, why): skip when another real run was created at or after `slot` and before this one."""
    created = parse_time(me.get("created_at"))
    if created is None or slot is None:
        return False, "no slot, run as usual"
    for r in runs:
        if str(r.get("id")) == str(me.get("id")):
            continue
        c = parse_time(r.get("created_at"))
        if c is None:
            continue
        if not (slot <= c < created or (c == created and int(r.get("id") or 0) < int(me.get("id") or 0))):
            continue
        if counts_as_run(r, did_work):
            return True, "run %s (created %s) already covers the slot due %s" % (r.get("id"), fmt(c), fmt(slot))
    return False, "first run for the slot due %s" % fmt(slot)


# ---------------------------------------------------------------- keeper (pure; never reads the clock)
def next_event(after, check_after_min=10, verify_after_min=None):
    """(kind, time, slot, mode) for the first keeper event strictly after `after`: 'check' at
    slot + check_after_min and, when verify_after_min is set, 'verify' at slot + verify_after_min."""
    lags = [("check", check_after_min)] + ([("verify", verify_after_min)] if verify_after_min else [])
    longest = max(m for _, m in lags)
    day = ist_date(after - dt.timedelta(minutes=longest))
    best = None
    for ahead in range(0, 21):
        for when, mode in market_slots_for_day(day + dt.timedelta(days=ahead)):
            for kind, lag in lags:
                t = when + dt.timedelta(minutes=lag)
                if t > after and (best is None or t < best[1]):
                    best = (kind, t, when, mode)
        if best is not None and ahead >= 1:
            break
    return best or (None, None, None, None)


def next_check(after, check_after_min=10):
    kind, when, slot, mode = next_event(after, check_after_min, None)
    return when, slot, mode


def next_slot_start(slot):
    _, nxt, _ = next_check(slot, 0)
    return nxt


def plan(now, deadline, after=None, check_after_min=10, verify_after_min=None, extra=()):
    """('check' or 'verify', time, slot, mode) when the next event falls before `deadline`, else
    ('handoff', deadline, None, None). `after` is the last event already done (a new keeper passes its
    start minus LOOKBACK_MIN, so an event due during a hand-off is not lost). `extra` holds re-verifies."""
    kind, when, slot, mode = next_event(after if after is not None else now, check_after_min, verify_after_min)
    for t, s_, m in extra:
        if when is None or t < when:
            kind, when, slot, mode = "verify", t, s_, m
    if when is None or when > deadline:
        return "handoff", deadline, None, None
    return kind, when, slot, mode


def sleep_seconds(now, until):
    return max(0, int((until - now).total_seconds()))


def slot_already_ran(slot, runs, did_work=None):
    """(True, why) when a real update started at or after `slot`, or one is queued or running."""
    for r in runs:
        if r.get("status") in ACTIVE:
            return True, "update run %s is %s" % (r.get("id"), r.get("status"))
    for r in runs:
        start = run_start(r)
        if start is not None and start >= slot and counts_as_run(r, did_work):
            return True, "run %s started %s" % (r.get("id"), fmt(start))
    return False, "no update started since %s" % fmt(slot)


def fresh(price_as_of, slot):
    return bool(price_as_of) and str(price_as_of)[:10] >= ist_date(slot).isoformat()


def keeper_decide(now, slot, mode, runs, did_work=None, min_gap_min=50, price_as_of=None):
    """(action, reason) at the check: 'dispatch' one make-up of `mode`, or 'none'."""
    ran, why = slot_already_ran(slot, runs, did_work)
    if ran:
        return "none", "%s slot %s already ran: %s" % (mode, fmt(slot), why)
    if mode == "retry" and fresh(price_as_of, slot):
        return "none", "retry slot %s not needed: price_as_of is already %s" % (fmt(slot), price_as_of)
    latest = None
    for r in runs:
        start = run_start(r)
        if start is not None and counts_as_run(r, did_work) and (latest is None or start > latest):
            latest = start
    if latest is not None and (now - latest).total_seconds() / 60.0 < min_gap_min:
        return "none", "last start %s is under %d min ago" % (fmt(latest), min_gap_min)
    return "dispatch", "missed %s slot %s; last start %s" % (mode, fmt(slot), fmt(latest) if latest else "none")


def slot_runs(slot, runs, did_work=None, until=None):
    """Real update runs that started at or after `slot` and before `until` (the next slot)."""
    out = []
    for r in runs:
        start = run_start(r)
        if start is None or start < slot or (until is not None and start >= until):
            continue
        if counts_as_run(r, did_work):
            out.append(r)
    return sorted(out, key=run_start)


def verify_decide(slot, mode, runs, price_as_of=None, did_work=None, max_tries=2, until=None):
    """After a slot's run should be done. (action, reason):
    'wait'    an update is still queued or running: look again later
    'none'    no run for this slot (the check handles make-ups; a skipped retry slot lands here)
    'ok'      a run succeeded (and for close/retry, price_as_of reached the slot's IST date)
    'stale'   close/retry succeeded but price_as_of is older than the slot's IST date: recorded, not retried
    'retry'   every run for the slot failed and fewer than max_tries ran: start one more
    'gave_up' the slot failed max_tries times (the retry slot: once): recorded, never retried again
    """
    active = [r for r in runs if r.get("status") in ACTIVE]
    if active:
        return "wait", "update run %s is %s" % (active[0].get("id"), active[0].get("status"))
    mine = slot_runs(slot, runs, did_work, until)
    if not mine:
        return "none", "no run for the %s slot %s" % (mode, fmt(slot))
    good = [r for r in mine if r.get("conclusion") == "success"]
    if good:
        rid = good[-1].get("id")
        if mode not in PRICE_MODES:
            return "ok", "%s run %s succeeded" % (mode, rid)
        day = ist_date(slot).isoformat()
        if not price_as_of:
            return "ok", "%s run %s succeeded (price_as_of unreadable)" % (mode, rid)
        if str(price_as_of)[:10] < day:
            tail = "; the 18:30 IST retry slot looks again" if mode == "close" else "; no more retries today"
            return "stale", "%s run %s succeeded but price_as_of is %s, expected %s%s" % (mode, rid, price_as_of, day, tail)
        return "ok", "%s run %s succeeded, price_as_of %s" % (mode, rid, price_as_of)
    failed = [r for r in mine if r.get("conclusion") in FAILED]
    if not failed:
        return "none", "no finished run for the %s slot %s" % (mode, fmt(slot))
    tries = 1 if mode in NO_KEEPER_RETRY else max_tries
    if len(mine) >= tries:
        return "gave_up", "%s slot %s failed %d time(s) (runs %s); not retrying again" % (
            mode, fmt(slot), len(mine), ", ".join(str(r.get("id")) for r in mine))
    return "retry", "%s run %s for slot %s ended %s; one retry" % (
        mode, failed[-1].get("id"), fmt(slot), failed[-1].get("conclusion"))


def live_keepers(keeper_runs, my_id=None):
    return [r for r in keeper_runs if r.get("status") in ACTIVE and str(r.get("id")) != str(my_id)]


def should_yield(my_id, keeper_runs):
    """A keeper steps aside when a newer keeper is queued or running, so the chain never forks."""
    newer = [r for r in live_keepers(keeper_runs, my_id) if int(r.get("id") or 0) > int(my_id or 0)]
    return (True, "newer keeper %s is %s" % (newer[0].get("id"), newer[0].get("status"))) if newer else (False, "")


def should_start_keeper(keeper_runs, enabled=True):
    if not enabled:
        return False, "switch self_heal_keeper is off"
    live = live_keepers(keeper_runs)
    if live:
        return False, "keeper %s is already %s" % (live[0].get("id"), live[0].get("status"))
    return True, "no live keeper"


def keeper_on(cfg):
    return bool(((cfg or {}).get("features") or {}).get("self_heal_keeper", True))


def keeper_settings(cfg):
    out = dict(KEEPER_DEFAULTS)
    for k, v in ((cfg or {}).get("keeper") or {}).items():
        if k in out:
            out[k] = int(v)
    out["chunk_min"] = max(30, min(out["chunk_min"], 340))  # hosted jobs stop at 360 min
    out["max_tries"] = max(1, min(out["max_tries"], 2))       # at most one retry per slot
    out["recheck_min"] = max(5, out["recheck_min"])
    return out


def holiday_note(slot):
    if slot is not None and ist_date(slot).year not in HOLIDAY_YEARS:
        return " (no NSE holiday list for %d yet: every weekday counts)" % ist_date(slot).year
    return ""


# ---------------------------------------------------------------- GitHub API
def _api(method, path, body=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    url = "https://api.github.com/repos/%s%s" % (repo, path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def fetch_runs(n=50):
    return _api("GET", "/actions/workflows/%s/runs?per_page=%d" % (WORKFLOW_FILE, n)).get("workflow_runs", [])


def fetch_keeper_runs(n=20):
    return _api("GET", "/actions/workflows/%s/runs?per_page=%d" % (KEEPER_FILE, n)).get("workflow_runs", [])


_WORK = {}


def api_did_work(run):
    """True unless the run finished and its data step was skipped by the guard. Looked up lazily."""
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return True
    rid = run.get("id")
    if rid not in _WORK:
        try:
            jobs = _api("GET", "/actions/runs/%s/jobs" % rid).get("jobs", [])
            steps = [s for j in jobs for s in (j.get("steps") or []) if s.get("name") == DATA_STEP]
            _WORK[rid] = not steps or any(s.get("conclusion") != "skipped" for s in steps)
        except Exception:
            _WORK[rid] = True
    return _WORK[rid]


def read_config(path="config.json"):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _raw_from_main(path):
    repo = os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request("https://api.github.com/repos/%s/contents/%s?ref=main" % (repo, path), headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def live_config(path="config.json"):
    """config.json as it is on main right now, so a switch flipped mid-sleep is obeyed."""
    try:
        return _raw_from_main("config.json")
    except Exception as e:
        print("could not read config.json from main (%s), using the checkout" % e, flush=True)
        return read_config(path)


def fetch_price_as_of():
    """data/meta.json price_as_of on main right now, or None."""
    try:
        return _raw_from_main("data/meta.json").get("price_as_of")
    except Exception as e:
        print("could not read data/meta.json (%s)" % e, flush=True)
        return None


def record(level, text):
    """Leave a mark in the Actions run (annotation and job summary). No email, no message."""
    print("::%s title=Update keeper::%s" % (level, text), flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a") as f:
                f.write("- %s: %s\n" % (level.upper(), text))
        except Exception:
            pass


def _dispatch(workflow, inputs, tries=3):
    for i in range(tries):
        try:
            _api("POST", "/actions/workflows/%s/dispatches" % workflow, {"ref": "main", "inputs": inputs})
            return True
        except Exception as e:
            print("dispatch %s failed (%s), try %d of %d" % (workflow, e, i + 1, tries), flush=True)
            time.sleep(20)
    return False


def ensure_keeper(cfg=None, dry=False):
    cfg = read_config() if cfg is None else cfg
    try:
        runs = fetch_keeper_runs() if keeper_on(cfg) else []
    except Exception as e:
        print("ensure-keeper: could not read keeper runs (%s), leaving it" % e)
        return False
    start, why = should_start_keeper(runs, keeper_on(cfg))
    print("ensure-keeper:", "START" if start else "NONE", "-", why, "(dry run)" if dry else "", flush=True)
    if start and not dry:
        return _dispatch(KEEPER_FILE, {})
    return False


def run_keeper(env, now=None, sleep=time.sleep):
    """The keeper job's loop. Only this wrapper reads the clock."""
    now = now or (lambda: dt.datetime.now(UTC).replace(microsecond=0))
    me = env.get("GITHUB_RUN_ID")
    cfg = live_config()
    settings = keeper_settings(cfg)
    started = now()
    deadline = started + dt.timedelta(minutes=settings["chunk_min"])
    last = started - dt.timedelta(minutes=LOOKBACK_MIN)
    extra = []  # re-verifies: (time, slot, mode)
    print("keeper: started %s, hands off at %s; settings %s" % (fmt(started), fmt(deadline), settings), flush=True)
    while True:
        if not keeper_on(cfg):
            print("keeper: switch self_heal_keeper is off, stopping (no next keeper)", flush=True)
            return "off"
        try:
            yield_, why = should_yield(me, fetch_keeper_runs())
        except Exception as e:
            yield_, why = False, ""
            print("keeper: could not read keeper runs (%s)" % e, flush=True)
        if yield_:
            print("keeper: stepping aside -", why, flush=True)
            return "yield"
        kind, when, slot, mode = plan(now(), deadline, last, settings["check_after_min"],
                                      settings["verify_after_min"], extra)
        if kind == "handoff":
            nk, nw, ns, nm = next_event(last, settings["check_after_min"], settings["verify_after_min"])
            target = " (next: %s of the %s slot %s)%s" % (nk, nm, fmt(ns), holiday_note(ns)) if ns else ""
            print("keeper: next hand-off at %s (%s UTC)%s, sleeping %d s" % (
                fmt(when), when.strftime("%Y-%m-%d %H:%M"), target, sleep_seconds(now(), when)), flush=True)
        else:
            print("keeper: next %s at %s (%s UTC) for the %s slot %s%s, sleeping %d s" % (
                kind, fmt(when), when.strftime("%Y-%m-%d %H:%M"), mode, fmt(slot), holiday_note(slot),
                sleep_seconds(now(), when)), flush=True)
        sleep(sleep_seconds(now(), when))
        cfg = live_config()
        if not keeper_on(cfg):
            continue  # top of loop prints and stops
        if kind == "handoff":
            try:
                others = live_keepers(fetch_keeper_runs(), me)
            except Exception:
                others = []
            if others:
                print("keeper: keeper %s is already live, not chaining" % others[0].get("id"), flush=True)
                return "yield"
            ok = _dispatch(KEEPER_FILE, {})
            print("keeper: handed off to the next keeper" if ok else "keeper: hand-off failed, crons will restart one", flush=True)
            return "handoff"
        if (when, slot, mode) in extra:
            extra.remove((when, slot, mode))
        else:
            last = when
        try:
            runs = fetch_runs()
        except Exception as e:
            print("keeper: could not read update runs (%s), skipping this %s" % (e, kind), flush=True)
            continue
        if kind == "check":
            asof = fetch_price_as_of() if mode == "retry" else None
            action, why = keeper_decide(now(), slot, mode, runs, api_did_work, settings["min_gap_min"], asof)
            print("keeper decision:", action.upper(), "-", why, flush=True)
            if action == "dispatch" and _dispatch(WORKFLOW_FILE, {"mode": mode, "reason": "keeper"}):
                print("keeper: dispatched one %s update" % mode, flush=True)
            continue
        asof = fetch_price_as_of() if mode in PRICE_MODES else None
        action, why = verify_decide(slot, mode, runs, asof, api_did_work, settings["max_tries"], next_slot_start(slot))
        print("keeper verify:", action.upper(), "-", why, flush=True)
        if action == "wait":
            t = now() + dt.timedelta(minutes=settings["recheck_min"])
            if (t - slot).total_seconds() / 60.0 <= VERIFY_FOR_MIN:
                extra.append((t, slot, mode))
        elif action == "retry":
            if _dispatch(WORKFLOW_FILE, {"mode": mode, "reason": "keeper_retry"}):
                print("keeper: dispatched one %s retry" % mode, flush=True)
                extra.append((now() + dt.timedelta(minutes=settings["verify_after_min"]), slot, mode))
        elif action in ("stale", "gave_up"):
            record("warning", why)
        elif action == "none":
            # Second chance for the check: a late cron that the guard was dropping may have looked
            # like a live run at check time. Same rules as the check, so never a second make-up.
            asof = asof if mode in PRICE_MODES else None
            action, why = keeper_decide(now(), slot, mode, runs, api_did_work, settings["min_gap_min"], asof)
            print("keeper decision (at verify):", action.upper(), "-", why, flush=True)
            if action == "dispatch" and _dispatch(WORKFLOW_FILE, {"mode": mode, "reason": "keeper"}):
                print("keeper: dispatched one %s update" % mode, flush=True)
                extra.append((now() + dt.timedelta(minutes=settings["verify_after_min"]), slot, mode))


def _out(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write("%s=%s\n" % (key, value))


def run_guard(env, fetch=None):
    """Return skip (True/False). Fails open: if the run list cannot be read, the update runs."""
    fetch = fetch or fetch_runs
    now = dt.datetime.now(UTC).replace(microsecond=0)
    runs, err = None, None
    try:
        runs = fetch()
    except Exception as e:
        err = e
    me = None
    if runs is not None:
        me = next((r for r in runs if str(r.get("id")) == str(env.get("GITHUB_RUN_ID"))), None)
    if me is None:
        me = {"id": int(env.get("GITHUB_RUN_ID", "0") or 0), "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    created = parse_time(me.get("created_at")) or now
    slot, why = guard_slot(env.get("EVENT_NAME", ""), env.get("SCHEDULE", ""), env.get("REASON", ""),
                           env.get("MODE", ""), created)
    print("guard (slot):", why)
    if slot is None:
        return False
    if runs is None:
        print("guard (duplicate slot): RUN - could not read runs (%s), run as usual" % err)
        return False
    skip, why = duplicate(me, slot, runs, api_did_work)
    print("guard (duplicate slot):", "SKIP" if skip else "RUN", "-", why)
    return skip


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "keeper":
        run_keeper(os.environ)
        return 0
    if cmd == "ensure-keeper":
        ensure_keeper(dry=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"))
        return 0
    if cmd == "guard":
        _out("skip", "true" if run_guard(os.environ) else "false")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
