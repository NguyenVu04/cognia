from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.awareness import rules
from src.domain.awareness.awareness_service import AwarenessService
from src.domain.awareness.models import DeskTime
from src.domain.events.models import Event, EventKind
from src.domain.ports import PresenceSample

ZONE = timezone(timedelta(hours=7))
MORNING = datetime(2026, 11, 6, 9, 0, tzinfo=ZONE)


def sample(idle=0, locked=False, presenting=False, app="code.exe") -> PresenceSample:
    return PresenceSample(idle, locked, presenting, app)


def presence(seq, minutes, at_desk, *, idle=0, first=False, base=MORNING) -> Event:
    payload = {"at_desk": at_desk, "locked": False, "presenting": False,
               "idle_seconds": idle, "first": first}
    return Event(seq, base + timedelta(minutes=minutes), 420, EventKind.PRESENCE,
                 payload, None)


def app(seq, minutes, name, base=MORNING) -> Event:
    return Event(seq, base + timedelta(minutes=minutes), 420,
                 EventKind.FOREGROUND_APP, {"app": name}, None)


def gap(seq, minutes, seconds, base=MORNING) -> Event:
    return Event(seq, base + timedelta(minutes=minutes), 420, EventKind.CLOCK_GAP,
                 {"seconds": seconds}, None)


def switched_off(seq, minutes, base=MORNING) -> Event:
    return Event(seq, base + timedelta(minutes=minutes), 420,
                 EventKind.SETTING_CHANGED, {"name": "awareness_on", "value": False},
                 None)


# ── the sample ───────────────────────────────────────────────────────────


def test_sample_has_exactly_four_fields() -> None:
    assert [f.name for f in fields(PresenceSample)] == [
        "idle_seconds", "locked", "presenting", "foreground_app",
    ]


@pytest.mark.parametrize(
    ("taken", "here"),
    [(sample(idle=299), True), (sample(idle=300), False), (sample(locked=True), False)],
)
def test_at_desk(taken: PresenceSample, here: bool) -> None:
    assert rules.at_desk(taken) is here


# ── changes only ─────────────────────────────────────────────────────────


def test_first_sample_reports_everything() -> None:
    changes = rules.presence_events(None, sample())

    kinds = [kind for kind, _ in changes]
    assert kinds == [EventKind.PRESENCE, EventKind.FOREGROUND_APP]
    assert changes[0][1]["first"] is True
    assert changes[1][1] == {"app": "code.exe"}


def test_same_sample_reports_nothing() -> None:
    assert rules.presence_events(sample(idle=3), sample(idle=40)) == ()


def test_going_away_is_reported_with_idle_seconds() -> None:
    ((kind, payload),) = rules.presence_events(sample(), sample(idle=300))

    assert kind is EventKind.PRESENCE
    assert payload["at_desk"] is False
    assert payload["idle_seconds"] == 300


def test_new_application_reported() -> None:
    assert rules.presence_events(sample(), sample(app="firefox.exe")) == (
        (EventKind.FOREGROUND_APP, {"app": "firefox.exe"}),
    )


# ── the day ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hour", "day"), [(9, 6), (4, 6), (3, 5), (23, 6)]
)
def test_day_starts_at_four(hour: int, day: int) -> None:
    moment = datetime(2026, 11, 6, hour, 30, tzinfo=ZONE)

    assert rules.day_start(moment) == datetime(2026, 11, day, 4, 0, tzinfo=ZONE)


# ── time at the machine ──────────────────────────────────────────────────


def test_desk_time_now() -> None:
    events = [presence(1, 0, True, first=True)]

    assert rules.desk_time(events, MORNING + timedelta(minutes=95)) == DeskTime(
        95, 95, True
    )


def test_away_counts_from_the_last_input() -> None:
    # Away noticed at 09:35 after 300 s idle: the user left at 09:30.
    events = [presence(1, 0, True, first=True), presence(2, 35, False, idle=300)]

    assert rules.desk_time(events, MORNING + timedelta(minutes=60)) == DeskTime(
        30, None, False
    )


def test_short_absence_keeps_the_run() -> None:
    events = [
        presence(1, 0, True, first=True),
        presence(2, 30, False, idle=0),
        presence(3, 33, True),
    ]

    desk = rules.desk_time(events, MORNING + timedelta(minutes=60))

    assert desk.today_minutes == 57
    assert desk.since_break_minutes == 60


def test_real_break_starts_a_new_run() -> None:
    events = [
        presence(1, 0, True, first=True),
        presence(2, 30, False, idle=0),
        presence(3, 40, True),
    ]

    desk = rules.desk_time(events, MORNING + timedelta(minutes=60))

    assert desk.today_minutes == 50
    assert desk.since_break_minutes == 20


def test_clock_gap_ends_the_run() -> None:
    events = [presence(1, 0, True, first=True), gap(2, 70, 3600)]

    desk = rules.desk_time(events, MORNING + timedelta(minutes=80))

    assert desk == DeskTime(10, None, False)


def test_restart_does_not_count_unobserved_time() -> None:
    events = [
        presence(1, 0, True, first=True),
        app(2, 20, "code.exe"),
        presence(3, 120, True, first=True),
    ]

    desk = rules.desk_time(events, MORNING + timedelta(minutes=130))

    assert desk.today_minutes == 30


def test_switching_off_ends_the_run() -> None:
    events = [presence(1, 0, True, first=True), switched_off(2, 25)]

    assert rules.desk_time(events, MORNING + timedelta(minutes=90)).today_minutes == 25


def test_the_day_splits_at_four() -> None:
    night = datetime(2026, 11, 6, 3, 0, tzinfo=ZONE)
    events = [presence(1, 0, True, first=True, base=night)]

    desk = rules.desk_time(events, night + timedelta(hours=2))

    assert desk.today_minutes == 60
    assert desk.since_break_minutes == 120


# ── applications ─────────────────────────────────────────────────────────


def test_app_minutes_only_at_desk() -> None:
    events = [
        presence(1, 0, True, first=True),
        app(2, 0, "code.exe"),
        app(3, 40, "firefox.exe"),
        presence(4, 50, False, idle=0),
    ]

    minutes = rules.app_minutes(events, MORNING, MORNING + timedelta(hours=2))

    assert minutes == {"code.exe": 40, "firefox.exe": 10}


def test_app_minutes_split_across_hours() -> None:
    events = [presence(1, 0, True, first=True), app(2, 0, "code.exe")]
    ten = MORNING + timedelta(hours=1)

    assert rules.app_minutes(events, MORNING, ten) == {"code.exe": 60}
    assert rules.app_minutes(events, ten, ten + timedelta(minutes=15)) == {
        "code.exe": 15
    }


# ── what the model is told ───────────────────────────────────────────────


def test_desk_time_text() -> None:
    assert rules.desk_time_text(DeskTime(192, 47, True)) == (
        "At the machine today: 3 h 12 min. Since the last break: 47 min."
    )
    assert rules.desk_time_text(DeskTime(30, None, False)) == (
        "At the machine today: 30 min."
    )
    assert rules.desk_time_text(DeskTime(0, None, False)) == rules.NOT_SEEN
    assert rules.desk_time_text(None) == rules.AWARENESS_OFF_TIME


def test_app_usage_text() -> None:
    assert rules.app_usage_text({"firefox.exe": 40, "code.exe": 125, "x.exe": 0}) == (
        "Today: code.exe 2 h 5 min; firefox.exe 40 min."
    )
    assert rules.app_usage_text({}) == rules.NO_APPS
    assert rules.app_usage_text(None) == rules.AWARENESS_OFF_APPS


# ── the service ──────────────────────────────────────────────────────────


class FakeLog:
    def __init__(self, events) -> None:
        self.events = events
        self.since: list[datetime] = []

    def read_since(self, moment):
        self.since.append(moment)
        return iter([e for e in self.events if e.occurred_at >= moment])


def test_service_reads_a_day_before_the_day() -> None:
    log = FakeLog([presence(1, 0, True, first=True)])

    desk = AwarenessService(log).desk_time(MORNING + timedelta(minutes=10))

    assert desk.today_minutes == 10
    assert log.since == [datetime(2026, 11, 5, 4, 0, tzinfo=ZONE)]
