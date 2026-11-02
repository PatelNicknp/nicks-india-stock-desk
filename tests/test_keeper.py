"""Offline checks for the India update keeper (keeper.py): IST slots, NSE holidays, the make-up check,
success and fresh-data verify with one retry, the duplicate guard for late crons, single-keeper rules,
the switch, and the run loop with a fake clock and fake GitHub API. No network, no real clock.

India time has no daylight saving: 08:00 IST = 02:30 UTC (morning), 16:30 IST = 11:00 UTC (close),
18:30 IST = 13:00 UTC (retry). 2026-11-02 is a Monday. NSE holidays used here: Tue 2026-11-10
(Diwali Balipratipada), Tue 2026-11-24 (Guru Nanak Jayanti), Fri 2026-12-25 (Christmas).
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import keeper as k
import tables

UTC = dt.timezone.utc


def T(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def S(t):
    return t.strftime("%Y-%m-%d %H:%M")


def run(i, start, status="completed", conclusion="success", worked=True, event="workflow_dispatch"):
    stamp = T(start).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": i, "status": status, "conclusion": conclusion, "event": event,
            "created_at": stamp, "run_started_at": stamp, "_worked": worked}


def did_work(r):
    return r.get("_worked", True)


def nc(now, lag=10):
    when, slot, mode = k.next_check(T(now), lag)
    return S(when), S(slot), mode


# ---------------------------------------------------------------- IST slots and holidays
def test_ist_slots():
    assert [(S(t), m) for t, m in k.slots_for_day(dt.date(2026, 11, 2))] == [
        ("2026-11-02 02:30", "morning"), ("2026-11-02 11:00", "close"), ("2026-11-02 13:00", "retry")]
    assert k.slots_for_day(dt.date(2026, 11, 7)) == [] and k.slots_for_day(dt.date(2026, 11, 8)) == []  # Sat, Sun
    # The cron strings in update.yml are exactly these slots.
    for cron, mode in k.CRON_MODE.items():
        fired = k.cron_fire_time(cron, T("2026-11-03 20:00"))
        assert (fired, mode) in k.slots_for_day(dt.date(2026, 11, 3))


def test_next_check_ist():
    # Mon Nov 2 2026 12:30 PM PT = 20:30 UTC = Tue 02:00 IST: next is Tue 08:00 IST, checked 02:40 UTC.
    assert nc("2026-11-02 20:30") == ("2026-11-03 02:40", "2026-11-03 02:30", "morning")
    assert nc("2026-11-03 02:40") == ("2026-11-03 11:10", "2026-11-03 11:00", "close")
    assert nc("2026-11-03 11:10") == ("2026-11-03 13:10", "2026-11-03 13:00", "retry")
    assert nc("2026-11-03 13:10") == ("2026-11-04 02:40", "2026-11-04 02:30", "morning")
    # Friday retry -> Monday morning.
    assert nc("2026-11-06 13:10") == ("2026-11-09 02:40", "2026-11-09 02:30", "morning")
    assert nc("2026-11-08 23:00") == ("2026-11-09 02:40", "2026-11-09 02:30", "morning")  # Sunday (Muhurat day) has no slots
    # The IST day starts at 18:30 UTC the day before: Mon 23:00 UTC is already Tue in India.
    assert nc("2026-11-02 23:00") == ("2026-11-03 02:40", "2026-11-03 02:30", "morning")


def test_nse_holidays_are_skipped():
    # Mon Nov 9 retry -> Tue Nov 10 is Diwali Balipratipada (closed) -> Wed Nov 11.
    assert nc("2026-11-09 13:10") == ("2026-11-11 02:40", "2026-11-11 02:30", "morning")
    # Mon Nov 23 -> Tue Nov 24 Guru Nanak Jayanti closed -> Wed Nov 25.
    assert nc("2026-11-23 13:10") == ("2026-11-25 02:40", "2026-11-25 02:30", "morning")
    # Thu Dec 24 -> Fri Dec 25 Christmas -> Mon Dec 28.
    assert nc("2026-12-24 13:10") == ("2026-12-28 02:40", "2026-12-28 02:30", "morning")
    assert k.market_slots_for_day(dt.date(2026, 11, 10)) == []
    assert len(k.market_slots_for_day(dt.date(2026, 11, 11))) == 3
    assert len(k.NSE_HOLIDAYS) == 16 and all(d.weekday() < 5 and d.year == 2026 for d in k.NSE_HOLIDAYS)
    assert dt.date(2026, 1, 15) in k.NSE_HOLIDAYS        # added by NSE/CMTR/72260
    # 2027 is not published yet: plain weekdays, and the log says so.
    assert nc("2026-12-31 13:10") == ("2027-01-01 02:40", "2027-01-01 02:30", "morning")
    assert "2027" in k.holiday_note(T("2027-01-01 02:30")) and k.holiday_note(T("2026-11-03 02:30")) == ""


def test_check_after_setting():
    assert nc("2026-11-02 20:30", lag=20) == ("2026-11-03 02:50", "2026-11-03 02:30", "morning")


def test_fmt_shows_ist_and_pt():
    assert k.fmt(T("2026-11-03 02:30")) == "Tue 03 Nov 08:00 IST / Mon 02 Nov 18:30 PT"
    assert k.fmt(T("2026-07-07 11:00")) == "Tue 07 Jul 16:30 IST / Tue 07 Jul 04:00 PT"   # PDT


# ---------------------------------------------------------------- sleep and hand-off math
def test_plan_and_sleep():
    now = T("2026-11-02 20:30")
    kind, when, slot, mode = k.plan(now, now + dt.timedelta(minutes=330), None, 10, 45)
    # 330 min from 20:30 is 02:00 UTC, before the 02:40 check: hand off first.
    assert kind == "handoff" and when == T("2026-11-03 02:00")
    now = T("2026-11-03 02:00")
    kind, when, slot, mode = k.plan(now, now + dt.timedelta(minutes=330), None, 10, 45)
    assert (kind, when, slot, mode) == ("check", T("2026-11-03 02:40"), T("2026-11-03 02:30"), "morning")
    assert k.sleep_seconds(now, when) == 40 * 60 and k.sleep_seconds(T("2026-11-03 03:00"), when) == 0


def test_next_event_with_verify():
    ev = lambda a: (lambda r: (r[0], S(r[1]), S(r[2]), r[3]))(k.next_event(T(a), 10, 45))
    assert ev("2026-11-03 02:00") == ("check", "2026-11-03 02:40", "2026-11-03 02:30", "morning")
    assert ev("2026-11-03 02:40") == ("verify", "2026-11-03 03:15", "2026-11-03 02:30", "morning")
    assert ev("2026-11-03 03:15") == ("check", "2026-11-03 11:10", "2026-11-03 11:00", "close")
    assert ev("2026-11-03 11:10") == ("verify", "2026-11-03 11:45", "2026-11-03 11:00", "close")
    assert ev("2026-11-03 11:45") == ("check", "2026-11-03 13:10", "2026-11-03 13:00", "retry")
    assert ev("2026-11-03 13:10") == ("verify", "2026-11-03 13:45", "2026-11-03 13:00", "retry")
    assert ev("2026-11-03 13:45") == ("check", "2026-11-04 02:40", "2026-11-04 02:30", "morning")
    assert ev("2026-11-09 13:45") == ("check", "2026-11-11 02:40", "2026-11-11 02:30", "morning")  # holiday
    assert k.next_slot_start(T("2026-11-03 11:00")) == T("2026-11-03 13:00")
    assert k.next_slot_start(T("2026-11-06 13:00")) == T("2026-11-09 02:30")


def test_plan_weekend_chunks():
    now, chunks = T("2026-11-06 13:45"), 0   # Fri after the retry verify
    while True:
        kind, when, _, _ = k.plan(now, now + dt.timedelta(minutes=330), now, 10, 45)
        assert k.sleep_seconds(now, when) <= 330 * 60
        if kind != "handoff":
            break
        chunks += 1
        now = when
    assert kind == "check" and when == T("2026-11-09 02:40") and chunks == 11   # ~60.9 h / 5.5 h


def test_plan_lookback_after_handoff():
    # The old keeper handed off at 11:05 because the 11:10 check was past its deadline. The new keeper
    # starts at 11:12 and looks back 15 minutes, so the 11:10 check still happens at once.
    start = T("2026-11-03 11:12")
    kind, when, slot, _ = k.plan(start, start + dt.timedelta(minutes=330), start - dt.timedelta(minutes=k.LOOKBACK_MIN), 10, 45)
    assert (kind, when, slot) == ("check", T("2026-11-03 11:10"), T("2026-11-03 11:00"))


def test_settings_are_clamped():
    s = k.keeper_settings({"keeper": {"chunk_min": 999, "check_after_min": 12, "max_tries": 9}})
    assert s["chunk_min"] == 340 and s["check_after_min"] == 12 and s["min_gap_min"] == 50 and s["max_tries"] == 2
    assert k.keeper_settings({"keeper": {"max_tries": 0}})["max_tries"] == 1
    assert k.keeper_settings({}) == k.KEEPER_DEFAULTS


# ---------------------------------------------------------------- the check
MORNING, CLOSE, RETRY = T("2026-11-03 02:30"), T("2026-11-03 11:00"), T("2026-11-03 13:00")


def test_slot_already_ran():
    assert k.slot_already_ran(CLOSE, [run(1, "2026-11-03 11:01", event="schedule")], did_work)[0]
    assert k.slot_already_ran(CLOSE, [run(1, "2026-11-03 11:04", "queued", None)], did_work)[0]
    assert k.slot_already_ran(CLOSE, [run(1, "2026-11-03 11:02", conclusion="failure")], did_work)[0]
    assert not k.slot_already_ran(CLOSE, [run(1, "2026-11-03 02:40")], did_work)[0]                 # morning only
    assert not k.slot_already_ran(CLOSE, [run(1, "2026-11-03 11:02", worked=False)], did_work)[0]   # guard-skipped
    assert not k.slot_already_ran(CLOSE, [run(1, "2026-11-03 11:02", conclusion="cancelled")], did_work)[0]


def test_keeper_decide():
    act, why = k.keeper_decide(T("2026-11-03 11:10"), CLOSE, "close", [run(1, "2026-11-03 02:40")], did_work)
    assert act == "dispatch" and "close" in why
    assert k.keeper_decide(T("2026-11-03 02:40"), MORNING, "morning", [run(1, "2026-11-02 11:10")], did_work)[0] == "dispatch"
    # A manual run 20 min ago: no extra run.
    assert k.keeper_decide(T("2026-11-03 11:10"), CLOSE, "close", [run(1, "2026-11-03 10:50")], did_work)[0] == "none"
    # Retry slot: only while the close has not brought that IST date's prices.
    stale = k.keeper_decide(T("2026-11-03 13:10"), RETRY, "retry", [run(1, "2026-11-03 11:10")], did_work, 50, "2026-11-02")
    assert stale[0] == "dispatch"
    fresh = k.keeper_decide(T("2026-11-03 13:10"), RETRY, "retry", [run(1, "2026-11-03 11:10")], did_work, 50, "2026-11-03")
    assert fresh[0] == "none" and "not needed" in fresh[1]
    assert k.keeper_decide(T("2026-11-03 13:10"), RETRY, "retry", [run(1, "2026-11-03 11:10")], did_work, 50, None)[0] == "dispatch"


# ---------------------------------------------------------------- verify: success, fresh data, one retry
def test_verify_decide():
    V = lambda slot, mode, runs, asof="2026-11-03", tries=2: k.verify_decide(
        slot, mode, runs, asof, did_work, tries, k.next_slot_start(slot))[0]
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:10")]) == "ok"
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:10")], asof="2026-11-02") == "stale"     # no retry for stale
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:10")], asof=None) == "ok"               # unreadable: no false alarm
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:10", conclusion="failure")]) == "retry"  # e.g. a test failed
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:10", conclusion="timed_out")]) == "retry"
    two_fails = [run(2, "2026-11-03 11:45", conclusion="failure"), run(1, "2026-11-03 11:10", conclusion="failure")]
    assert V(CLOSE, "close", two_fails) == "gave_up"
    assert V(CLOSE, "close", [run(2, "2026-11-03 11:45"), run(1, "2026-11-03 11:10", conclusion="failure")]) == "ok"
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:10", conclusion="failure")], tries=1) == "gave_up"
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:20", "in_progress", None)]) == "wait"
    assert V(CLOSE, "close", []) == "none" and V(CLOSE, "close", [run(1, "2026-11-03 02:40")]) == "none"
    assert V(CLOSE, "close", [run(3, "2026-11-03 13:10", conclusion="failure")]) == "none"   # the retry slot's run
    assert V(CLOSE, "close", [run(1, "2026-11-03 11:10", worked=False)]) == "none"           # guard-skipped late cron
    # Morning has no prices: success is enough even though price_as_of is yesterday's close.
    assert V(MORNING, "morning", [run(1, "2026-11-03 02:40")], asof="2026-11-02") == "ok"
    assert V(MORNING, "morning", [run(1, "2026-11-03 02:40", conclusion="failure")]) == "retry"
    # Retry slot is itself the retry: never retried again, stale is a warning.
    assert V(RETRY, "retry", [run(1, "2026-11-03 13:10", conclusion="failure")]) == "gave_up"
    assert V(RETRY, "retry", [run(1, "2026-11-03 13:10")], asof="2026-11-02") == "stale"
    assert V(RETRY, "retry", [run(1, "2026-11-03 13:10")]) == "ok"
    # Close on Mon Nov 2: 11:00 UTC is 16:30 IST, so price_as_of must be 2026-11-02.
    assert V(T("2026-11-02 11:00"), "close", [run(1, "2026-11-02 11:10")], asof="2026-11-02") == "ok"


# ---------------------------------------------------------------- guard: late crons collapse into the make-up
def test_guard_slot():
    slot, _ = k.guard_slot("schedule", "0 11 * * 1-5", "", "", T("2026-11-03 17:05"))   # 6 h late close cron
    assert slot == T("2026-11-03 11:00")
    slot, _ = k.guard_slot("schedule", "30 2 * * 1-5", "", "", T("2026-11-03 08:50"))
    assert slot == T("2026-11-03 02:30")
    slot, _ = k.guard_slot("workflow_dispatch", "", "keeper", "close", T("2026-11-03 11:10"))
    assert slot == T("2026-11-03 11:00")
    slot, _ = k.guard_slot("workflow_dispatch", "", "keeper", "morning", T("2026-11-03 11:50"))  # verify-time make-up
    assert slot == T("2026-11-03 02:30")
    assert k.guard_slot("workflow_dispatch", "", "keeper_retry", "close", T("2026-11-03 11:50"))[0] is None
    assert k.guard_slot("workflow_dispatch", "", "", "close", T("2026-11-03 11:50"))[0] is None   # manual / watchdog


def test_late_cron_is_skipped_after_make_up():
    makeup = run(10, "2026-11-03 11:10", "in_progress", None)
    late = run(11, "2026-11-03 17:05", "in_progress", None, event="schedule")
    slot, _ = k.guard_slot("schedule", "0 11 * * 1-5", "", "", T("2026-11-03 17:05"))
    assert k.duplicate(late, slot, [late, makeup], did_work)[0] is True
    # A failed make-up still covers the slot (the keeper's own retry handles failures).
    makeup = run(10, "2026-11-03 11:10", conclusion="failure")
    assert k.duplicate(late, slot, [late, makeup], did_work)[0] is True
    # Nothing ran since the slot (keeper off): the late cron runs as before.
    assert k.duplicate(late, slot, [late, run(9, "2026-11-03 02:40")], did_work)[0] is False
    # The make-up itself is never skipped by the late cron created after it.
    mslot, _ = k.guard_slot("workflow_dispatch", "", "keeper", "close", T("2026-11-03 11:10"))
    assert k.duplicate(run(10, "2026-11-03 11:10"), mslot, [late, run(10, "2026-11-03 11:10")], did_work)[0] is False
    # On-time cron first, then a keeper make-up would be skipped (the keeper does not send one, but if it did).
    cron = run(12, "2026-11-03 11:01", event="schedule")
    assert k.duplicate(run(13, "2026-11-03 11:10"), mslot, [cron, run(13, "2026-11-03 11:10")], did_work)[0] is True
    # A late morning cron skipped by the guard does not count as the close run.
    skipped = run(14, "2026-11-03 11:02", worked=False, event="schedule")
    assert k.duplicate(run(13, "2026-11-03 11:10"), mslot, [skipped, run(13, "2026-11-03 11:10")], did_work)[0] is False


def test_run_guard_fails_open():
    def boom():
        raise RuntimeError("no API")
    env = {"EVENT_NAME": "schedule", "SCHEDULE": "0 11 * * 1-5", "GITHUB_RUN_ID": "5"}
    assert k.run_guard(env, fetch=boom) is False


# ---------------------------------------------------------------- one keeper
def K(i, status):
    return {"id": i, "status": status}


def test_single_keeper_rules():
    assert k.should_start_keeper([], True)[0] is True
    assert k.should_start_keeper([K(1, "completed"), K(2, "cancelled")], True)[0] is True
    for st in ("in_progress", "queued", "pending", "waiting", "requested"):
        assert k.should_start_keeper([K(3, st)], True)[0] is False
    assert k.should_start_keeper([], False)[0] is False
    assert k.should_yield(5, [K(5, "in_progress"), K(6, "pending")])[0] is True
    assert k.should_yield(6, [K(5, "in_progress"), K(6, "in_progress")])[0] is False


def test_switch_settings_and_help_rows():
    cfg = json.load(open(os.path.join(ROOT, "config.json")))
    assert cfg["features"]["self_heal_keeper"] is True and k.keeper_on(cfg) is True
    assert k.keeper_on({"features": {"self_heal_keeper": False}}) is False and k.keeper_on({}) is True
    for key, value in k.KEEPER_DEFAULTS.items():
        assert cfg["keeper"][key] == value
    assert "self_heal_schedule" in cfg   # the watchdog's block is kept
    df = tables.settings_rows(cfg)
    rows = dict(zip(df["setting"], df["value"])) if hasattr(df, "columns") else {r["setting"]: r["value"] for r in df}
    assert rows["feature.self_heal_keeper"] is True and rows["keeper.chunk_min"] == 330 and rows["keeper.max_tries"] == 2
    assert "self_heal_keeper" in dict(tables.help_rows())["Update keeper"]


# ---------------------------------------------------------------- the loop, fake clock and fake API
class Fake:
    def __init__(self, start, update_runs, keeper_runs, cfgs=None, asof=None):
        self.t = start
        self.update_runs = update_runs
        self.keeper_runs = keeper_runs
        self.cfgs = list(cfgs or [])
        self.asof = asof
        self.dispatched = []
        self.records = []
        self.crons = []           # (time, conclusion) scheduled runs that appear when the clock passes them
        self.makeup_result = "success"
        self.makeup_asof = None   # price_as_of after a successful make-up

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += dt.timedelta(seconds=s)
        for c, concl in self.crons:
            stamp = T(c).strftime("%Y-%m-%dT%H:%M:%SZ")
            if T(c) <= self.t and all(r["created_at"] != stamp for r in self.update_runs):
                self.update_runs.insert(0, run(1000 + len(self.update_runs), c, conclusion=concl, event="schedule"))

    def config(self, path="config.json"):
        return self.cfgs.pop(0) if self.cfgs else {"features": {"self_heal_keeper": True}}

    def dispatch(self, wf, inputs, tries=3):
        self.dispatched.append((wf, dict(inputs), S(self.t)))
        if wf == k.WORKFLOW_FILE:
            self.update_runs.insert(0, run(500 + len(self.dispatched), S(self.t), conclusion=self.makeup_result))
            if self.makeup_result == "success" and self.makeup_asof and inputs.get("mode") != "morning":
                self.asof = self.makeup_asof
        return True


def with_fake(f, fn):
    saved = (k.live_config, k.fetch_keeper_runs, k.fetch_runs, k._dispatch, k.api_did_work, k.fetch_price_as_of, k.record)
    k.live_config = f.config
    k.fetch_price_as_of = lambda: f.asof
    k.record = lambda level, text: f.records.append((level, text))
    k.fetch_keeper_runs = lambda n=20: f.keeper_runs
    k.fetch_runs = lambda n=50: f.update_runs
    k._dispatch = f.dispatch
    k.api_did_work = did_work
    try:
        return fn()
    finally:
        (k.live_config, k.fetch_keeper_runs, k.fetch_runs, k._dispatch, k.api_did_work,
         k.fetch_price_as_of, k.record) = saved


def go(f, run_id="100"):
    return with_fake(f, lambda: k.run_keeper({"GITHUB_RUN_ID": run_id}, now=f.now, sleep=f.sleep))


def updates(f, reason=None):
    return [(i["mode"], i["reason"], t) for wf, i, t in f.dispatched
            if wf == k.WORKFLOW_FILE and (reason is None or i["reason"] == reason)]


def test_loop_makes_up_a_dead_cron_day_then_hands_off():
    # Keeper starts Tue 02:00 UTC (07:30 IST) with GitHub cron dead all day. Close brings fresh prices.
    f = Fake(T("2026-11-03 02:00"), [run(1, "2026-11-02 15:14")], [K(100, "in_progress")],
             asof="2026-11-02", cfgs=[{"features": {"self_heal_keeper": True}, "keeper": {"chunk_min": 340}}] * 50)
    f.makeup_asof = "2026-11-03"
    assert go(f) == "handoff"
    assert updates(f) == [("morning", "keeper", "2026-11-03 02:40")]   # morning made up once, verified ok
    assert f.records == []
    assert f.dispatched[-1][0] == k.KEEPER_FILE and f.dispatched[-1][2] == "2026-11-03 07:40"  # 340 min chunk
    # The next keeper makes up the close; it brings 2026-11-03, so the 18:30 IST retry slot is not needed.
    f.t, f.keeper_runs = T("2026-11-03 07:41"), [K(101, "in_progress")]
    assert go(f, "101") == "handoff"
    assert updates(f) == [("morning", "keeper", "2026-11-03 02:40"), ("close", "keeper", "2026-11-03 11:10")]
    assert f.records == [] and f.dispatched[-1][0] == k.KEEPER_FILE


def test_loop_full_day_with_handover_chain():
    # Three keepers in a row (chain hand-over) over a day where GitHub fires nothing; close data stays stale,
    # so the retry slot is made up too. Exactly one make-up per slot, never two.
    f = Fake(T("2026-11-02 20:30"), [run(1, "2026-11-02 15:14")], [], asof="2026-11-02")
    results, run_id = [], 100
    while S(f.t) < "2026-11-03 14:00":
        f.keeper_runs = [K(run_id, "in_progress")]
        results.append(go(f, str(run_id)))
        run_id += 1
    assert set(results) == {"handoff"}
    assert updates(f, "keeper") == [("morning", "keeper", "2026-11-03 02:40"), ("close", "keeper", "2026-11-03 11:10"),
                                    ("retry", "keeper", "2026-11-03 13:10")]
    assert updates(f, "keeper_retry") == []
    stale = [t for lvl, t in f.records if "price_as_of is 2026-11-02" in t]
    assert len(stale) == 2 and "18:30 IST retry slot looks again" in stale[0] and "no more retries" in stale[1]
    hand = [t for wf, _, t in f.dispatched if wf == k.KEEPER_FILE]
    assert hand == ["2026-11-03 02:00", "2026-11-03 07:30", "2026-11-03 13:00", "2026-11-03 18:30"]


def test_loop_does_nothing_when_crons_fire_on_time():
    f = Fake(T("2026-11-03 02:00"), [], [K(100, "in_progress")], asof="2026-11-02")
    f.crons = [("2026-11-03 02:31", "success"), ("2026-11-03 11:02", "success"), ("2026-11-03 13:01", "success")]
    f.cfgs = [{"features": {"self_heal_keeper": True}, "keeper": {"chunk_min": 340}}] * 50
    orig_sleep = f.sleep

    def sleep(s):
        orig_sleep(s)
        if f.t >= T("2026-11-03 11:05"):
            f.asof = "2026-11-03"
    f.sleep = sleep
    go(f)
    assert updates(f) == [] and f.records == []
    assert f.dispatched == [(k.KEEPER_FILE, {}, "2026-11-03 07:40")]


def test_loop_retries_a_failed_close_once_and_records():
    # The cron fires on time but every run fails (like the India desk failing a test on Oct 30 2026).
    f = Fake(T("2026-11-03 10:00"), [], [K(100, "in_progress")], asof="2026-11-02")
    f.crons = [("2026-11-03 11:01", "failure"), ("2026-11-03 13:01", "failure")]
    f.makeup_result = "failure"
    go(f)
    assert updates(f, "keeper") == []                                   # the crons ran, no make-ups
    assert updates(f, "keeper_retry") == [("close", "keeper_retry", "2026-11-03 11:45")]   # once; retry slot not retried
    gave_up = [t for _, t in f.records if "not retrying again" in t]
    assert len(gave_up) == 2 and "close slot" in gave_up[0] and "retry slot" in gave_up[1]


def test_restarted_keeper_does_not_retry_twice():
    # A keeper that starts at 12:30 after the close failed twice (cron + an earlier keeper's retry) only records.
    f = Fake(T("2026-11-03 11:40"), [run(2, "2026-11-03 11:46", conclusion="failure"),
                                     run(1, "2026-11-03 11:01", conclusion="failure", event="schedule")],
             [K(101, "in_progress")], asof="2026-11-02")
    f.cfgs = [{"features": {"self_heal_keeper": True}, "keeper": {"chunk_min": 30}}] * 10
    go(f, "101")
    assert updates(f, "keeper_retry") == [] and any("failed 2 time" in t for _, t in f.records)


def test_loop_records_stale_close_without_retry():
    f = Fake(T("2026-11-03 07:40"), [], [K(100, "in_progress")], asof="2026-11-02")
    f.crons = [("2026-11-03 11:01", "success")]
    f.cfgs = [{"features": {"self_heal_keeper": True}, "keeper": {"chunk_min": 340}}] * 20
    go(f)
    assert updates(f, "keeper_retry") == []
    assert any("close run" in t and "price_as_of is 2026-11-02" in t for _, t in f.records)
    assert updates(f, "keeper") == [("retry", "keeper", "2026-11-03 13:10")]   # the 18:30 IST slot, as scheduled


def test_loop_waits_for_a_long_run():
    f = Fake(T("2026-11-03 11:30"), [run(1, "2026-11-03 11:01", "in_progress", None, event="schedule")],
             [K(100, "in_progress")], asof="2026-11-02")
    f.cfgs = [{"features": {"self_heal_keeper": True}, "keeper": {"chunk_min": 60}}] * 20
    orig_sleep = f.sleep

    def sleep(s):
        orig_sleep(s)
        if f.t >= T("2026-11-03 12:10"):
            f.update_runs[0] = run(1, "2026-11-03 11:01", event="schedule")
            f.asof = "2026-11-03"
    f.sleep = sleep
    go(f)
    assert updates(f) == [] and f.records == []


def test_verify_time_second_chance():
    # At the 11:10 check a guard-skipping late morning cron looked live, so no make-up; at 11:45 the
    # verify finds no close run and makes it up once.
    f = Fake(T("2026-11-03 11:05"), [run(1, "2026-11-03 02:40"),
                                     run(2, "2026-11-03 11:08", "in_progress", None, event="schedule")],
             [K(100, "in_progress")], asof="2026-11-02")
    f.cfgs = [{"features": {"self_heal_keeper": True}, "keeper": {"chunk_min": 50}}] * 20
    orig_sleep = f.sleep

    def sleep(s):
        orig_sleep(s)
        if f.t >= T("2026-11-03 11:20"):
            f.update_runs[1] = run(2, "2026-11-03 11:08", worked=False, event="schedule")
    f.sleep = sleep
    go(f)
    assert updates(f) == [("close", "keeper", "2026-11-03 11:45")]


def test_loop_switch_off_stops_without_chaining():
    f = Fake(T("2026-11-03 02:00"), [], [K(100, "in_progress")],
             cfgs=[{"features": {"self_heal_keeper": True}}, {"features": {"self_heal_keeper": False}}])
    assert go(f) == "off" and f.dispatched == []
    f = Fake(T("2026-11-03 02:00"), [], [], cfgs=[{"features": {"self_heal_keeper": False}}])
    assert go(f) == "off" and f.dispatched == []


def test_loop_yields_to_newer_keeper_and_does_not_fork():
    f = Fake(T("2026-11-03 02:00"), [], [K(100, "in_progress"), K(101, "pending")])
    assert go(f) == "yield" and f.dispatched == []
    # At hand-off time another keeper is already queued: do not add one more.
    f = Fake(T("2026-11-03 13:50"), [run(1, "2026-11-03 13:01")], [K(100, "in_progress"), K(99, "queued")], asof="2026-11-03")
    assert go(f) == "yield" and f.dispatched == []


def test_ensure_keeper():
    f = Fake(T("2026-11-03 02:00"), [], [K(100, "in_progress")])
    assert with_fake(f, lambda: k.ensure_keeper({"features": {}})) is False and f.dispatched == []
    f = Fake(T("2026-11-03 02:00"), [], [K(100, "completed")])
    assert with_fake(f, lambda: k.ensure_keeper({"features": {}})) is True and f.dispatched[0][0] == k.KEEPER_FILE
    f = Fake(T("2026-11-03 02:00"), [], [])
    assert with_fake(f, lambda: k.ensure_keeper({"features": {}}, dry=True)) is False and f.dispatched == []
    assert with_fake(f, lambda: k.ensure_keeper({"features": {"self_heal_keeper": False}})) is False and f.dispatched == []


# ---------------------------------------------------------------- workflows
def test_workflows_wired():
    wf = lambda n: open(os.path.join(ROOT, ".github", "workflows", n)).read()
    keeper, update, dog = wf("keeper.yml"), wf("update.yml"), wf("watchdog.yml")
    assert "workflow_dispatch" in keeper and "schedule" not in keeper
    assert "group: india-update-keeper" in keeper and "actions: write" in keeper
    assert "timeout-minutes: 350" in keeper and "keeper.py keeper" in keeper
    # Crons unchanged; mode input defaults to close so manual and watchdog runs behave as before.
    for cron in k.CRON_MODE:
        assert 'cron: "%s"' % cron in update
    assert 'default: "close"' in update and 'options: ["close", "morning", "retry"]' in update
    assert "inputs.reason == 'keeper'" in update and "keeper.py ensure-keeper" in update
    guard_if = [l for l in update.splitlines() if "github.event_name == 'schedule'" in l][0]
    assert "keeper_retry" not in guard_if
    assert "python tests/test_keeper.py" in update and "actions: read" in update
    assert "keeper.py ensure-keeper" in dog and "keeper.py" in dog and "keepers_live" in dog


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("keeper ok")
