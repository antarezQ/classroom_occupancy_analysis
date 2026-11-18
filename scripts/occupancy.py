"""
Shared logic for the classroom occupancy analysis.
Used by both the notebook and the Streamlit dashboard so the numbers always match.
"""

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
WEEKDAYS = DAYS[:5]
OPEN, CLOSE = 6 * 60 + 30, 17 * 60 + 30          # operating hours 06:30 - 17:30
SLOT = 30                                        # minutes
FRIDAY_PRAYER = (11 * 60 + 30, 12 * 60 + 30)
LATE_NIGHT = 18 * 60                             # a class starting this late is treated as a likely input error

# after renovation: floor 3 keeps 20 classrooms, floor 9 (16 rooms) is replaced by floor 2 (12 rooms)
ROOMS_AFTER = {3: 20, 2: 12}
ROOMS_AFTER_TOTAL = sum(ROOMS_AFTER.values())

# LAC language classes all carry the same group label, so they are separate groups in practice.
# Their timetable is set by LAC in fixed packages, so LAC rows are not flagged as issues.
SHARED_GROUP_LABELS = {"ESyP"}
LAC_PROGRAM = "LAC"


def to_min(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


def to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def load():
    schedule = pd.read_csv(DATA_DIR / "schedule.csv", dtype={"room_id": str})
    rooms = pd.read_csv(DATA_DIR / "rooms_current.csv", dtype={"room_id": str})
    schedule["day"] = pd.Categorical(schedule["day"], DAYS, ordered=True)
    schedule["start_min"] = schedule["start_time"].map(to_min)
    schedule["end_min"] = schedule["end_time"].map(to_min)
    return schedule, rooms


def overlaps(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def regular(schedule):
    """Classes used for capacity and overtime analysis (drops the likely input error)."""
    return schedule[schedule.start_min < LATE_NIGHT]


# ------------------------------------------------------------------ demand

def concurrency(schedule, until=CLOSE + 60):
    """Rooms in use for every day x 30-minute slot."""
    cols = list(range(OPEN, until, SLOT))
    grid = pd.DataFrame(0, index=DAYS, columns=[to_hhmm(c) for c in cols])
    for day, g in schedule.groupby("day", observed=True):
        for c in cols:
            grid.loc[day, to_hhmm(c)] = int(((g.start_min <= c) & (g.end_min > c)).sum())
    return grid


def room_utilization(schedule, rooms):
    """Share of Mon-Fri operating hours (55 h) each room is booked."""
    available = (CLOSE - OPEN) / 60 * len(WEEKDAYS)
    wk = schedule[schedule.day.isin(WEEKDAYS)].copy()
    wk["hours_in_ops"] = (wk.end_min.clip(upper=CLOSE) - wk.start_min.clip(lower=OPEN)).clip(lower=0) / 60
    used = wk.groupby("room_id")["hours_in_ops"].sum()
    out = rooms.set_index("room_id").join(used.rename("booked_hours")).fillna({"booked_hours": 0})
    out["utilization"] = out["booked_hours"] / available
    return out.reset_index().sort_values("utilization", ascending=False)


# ------------------------------------------------------------------ data issues

def _pairs(schedule, key, skip=()):
    rows = []
    for (day, k), g in schedule.groupby(["day", key], observed=True):
        if k in skip:
            continue
        g = g.sort_values("start_min").reset_index(drop=True)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if g.start_min[j] < g.end_min[i]:
                    rows.append((g.loc[i], g.loc[j]))
    return rows


def data_issues(schedule):
    """Things in the timetable worth checking with the office (LAC classes are left out)."""
    schedule = schedule[schedule.program != LAC_PROGRAM]
    out = []
    for a, b in _pairs(schedule, "room_id"):
        out.append({"issue": "room double-booked", "day": a.day, "sessions": f"{a.session_id}, {b.session_id}",
                    "detail": f"{a.room_id}: {a.course_name} {a.start_time}-{a.end_time} and {b.course_name} {b.start_time}-{b.end_time}"})
    for a, b in _pairs(schedule, "class_group", skip=SHARED_GROUP_LABELS):
        out.append({"issue": "class group in two places", "day": a.day, "sessions": f"{a.session_id}, {b.session_id}",
                    "detail": f"{a.class_group}: {a.course_name} {a.start_time}-{a.end_time} ({a.room_id}) and "
                              f"{b.course_name} {b.start_time}-{b.end_time} ({b.room_id})"})
    for a, b in _pairs(schedule, "lecturer_id"):
        out.append({"issue": "lecturer in two rooms", "day": a.day, "sessions": f"{a.session_id}, {b.session_id}",
                    "detail": f"{a.lecturer_id}: {a.course_name} in {a.room_id} and {b.course_name} in {b.room_id}, "
                              f"{a.start_time}-{a.end_time}"})
    fri = schedule[(schedule.day == "Fri") & (schedule.start_min < FRIDAY_PRAYER[1]) & (schedule.end_min > FRIDAY_PRAYER[0])]
    for _, r in fri.iterrows():
        out.append({"issue": "class during Friday prayer", "day": r.day, "sessions": r.session_id,
                    "detail": f"{r.course_name} ({r.class_group}) {r.start_time}-{r.end_time}"})
    late = schedule[schedule.start_min >= LATE_NIGHT]
    for _, r in late.iterrows():
        out.append({"issue": "likely input error (late night)", "day": r.day, "sessions": r.session_id,
                    "detail": f"{r.course_name} ({r.class_group}) {r.start_time}-{r.end_time}"})
    return pd.DataFrame(out, columns=["issue", "day", "sessions", "detail"])


# ------------------------------------------------------------------ free rooms and slots

def free_rooms(schedule, rooms, day, start_min, end_min, floors=None, ignore=()):
    """Rooms with nothing booked between start and end on that day."""
    d = schedule[(schedule.day == day) & ~schedule.session_id.isin(ignore)]
    busy = set(d[(d.start_min < end_min) & (d.end_min > start_min)].room_id)
    r = rooms if floors is None else rooms[rooms.floor.isin(floors)]
    return [x for x in r.room_id if x not in busy]


def _is_free(schedule, day, start_min, end_min, column, value, ignore=()):
    d = schedule[(schedule.day == day) & (schedule[column] == value) & ~schedule.session_id.isin(ignore)]
    return not ((d.start_min < end_min) & (d.end_min > start_min)).any()


def find_slots(schedule, rooms, length_min, class_group=None, lecturer_id=None, days=WEEKDAYS,
               floors=None, ignore=(), step=SLOT):
    """
    Every time a class of this length could run: inside operating hours, not during Friday prayer,
    class group and lecturer both free, and at least one room free for the whole slot.
    """
    rows = []
    for day in days:
        for s in range(OPEN, CLOSE - length_min + 1, step):
            e = s + length_min
            if day == "Fri" and overlaps(s, e, *FRIDAY_PRAYER):
                continue
            if class_group and class_group not in SHARED_GROUP_LABELS and \
                    not _is_free(schedule, day, s, e, "class_group", class_group, ignore):
                continue
            if lecturer_id and not _is_free(schedule, day, s, e, "lecturer_id", lecturer_id, ignore):
                continue
            free = free_rooms(schedule, rooms, day, s, e, floors, ignore)
            if free:
                rows.append({"day": day, "start": to_hhmm(s), "end": to_hhmm(e), "free_rooms": len(free), "rooms": free})
    return pd.DataFrame(rows, columns=["day", "start", "end", "free_rooms", "rooms"])


# ------------------------------------------------------------------ overtime alternatives

def overtime_options(schedule, rooms, max_shift_hours=2):
    """
    For each weekday class that ends after 17:30, list earlier slots on the same day that end by 17:30
    and start at most `max_shift_hours` earlier, where the class group, the lecturer and at least one room
    are free in this timetable.

    These are candidates, not a new timetable. This data only covers these rooms, so a lecturer or
    class group may still be busy elsewhere (another building, meetings, labs). Each class is checked
    on its own against the current timetable.
    """
    reg = regular(schedule)
    todo = reg[(reg.end_min > CLOSE) & reg.day.isin(WEEKDAYS)].sort_values(["day", "start_min"])
    rows = []
    for _, r in todo.iterrows():
        length = r.end_min - r.start_min
        slots = find_slots(schedule, rooms, length, r.class_group, r.lecturer_id, days=[r.day], ignore=[r.session_id])
        if not slots.empty:
            shift = (r.start_min - slots.start.map(to_min)) / 60
            slots = slots[(shift > 0) & (shift <= max_shift_hours)]
        best_shift = None if slots.empty else min((r.start_min - to_min(x)) / 60 for x in slots.start)
        own_room = (not slots.empty) and any(r.room_id in rr for rr in slots.rooms)
        rows.append({
            "session_id": r.session_id, "course_name": r.course_name, "class_group": r.class_group,
            "lecturer_id": r.lecturer_id, "day": r.day, "current_time": f"{r.start_time}-{r.end_time}",
            "current_room": r.room_id, "alternatives": len(slots),
            "options": "; ".join(f"{a}-{b} ({n} rooms)" for a, b, n in zip(slots.start, slots.end, slots.free_rooms)) or "none",
            "smallest_shift_h": best_shift, "own_room_free": own_room,
        })
    return pd.DataFrame(rows)


def shift_together(schedule, rooms, session_ids, hours=1):
    """
    Move the given classes `hours` earlier all at once and check the result as a whole.
    Moved classes keep their room when it is free, otherwise they take the first free room.
    Returns the new timetable and how many classes had to change room (None if any could not fit).
    """
    t = schedule.copy()
    moved = t.session_id.isin(session_ids)
    t.loc[moved, ["start_min", "end_min"]] -= int(hours * 60)
    room_changes = 0
    for idx, row in t[moved].iterrows():
        others = t[(t.day == row.day) & (t.index != idx)]
        busy = set(others[(others.start_min < row.end_min) & (others.end_min > row.start_min)].room_id)
        if row.room_id in busy:
            free = [x for x in rooms.room_id if x not in busy]
            if not free:
                return t, None
            t.loc[idx, "room_id"] = free[0]
            room_changes += 1
    t["start_time"] = t.start_min.map(to_hhmm)
    t["end_time"] = t.end_min.map(to_hhmm)
    return t, room_changes


# ------------------------------------------------------------------ floor move

def floor_move(schedule):
    """
    Floor 9 (16 rooms) is replaced by floor 2 (12 rooms). For every slot: how many floor-9 classes run,
    how many fit on floor 2, and whether the rest fit in the free classrooms on floor 3 (20 rooms).
    """
    reg = regular(schedule)
    f9 = concurrency(reg[reg.floor == 9], until=CLOSE + 60)
    f3 = concurrency(reg[reg.floor == 3], until=CLOSE + 60)
    overflow = (f9 - ROOMS_AFTER[2]).clip(lower=0)
    spare3 = ROOMS_AFTER[3] - f3
    return f9, f3, overflow, spare3


# ------------------------------------------------------------------ faculty room allocation

FACULTY = {
    "S1 International ICT Business": "FEB",
    "S1 Akuntansi": "FEB",
    "S1 Administrasi Bisnis ( International Class )": "FKS",
    "S1 Ilmu Komunikasi": "FKS",
    "S1 Sistem Informasi": "FRI",
    "S1 Teknik Industri": "FRI",
    "S1 Teknik Elektro": "FTE",
    "S1 Teknik Telekomunikasi": "FTE",
    "S1 Informatika": "FIF",
    "S1 Teknologi Informasi": "FIF",
    "S1 DKV International": "FIK",
}

# home rooms per faculty, set by ICAO. FRI, FTE and FIF still have international classes in other
# buildings, so their share is larger than this timetable alone would need.
ALLOCATION = {"FEB": 6, "FKS": 5, "FRI": 4, "FTE": 4, "FIF": 4, "FIK": 2}
TOTAL_AFTER = ROOMS_AFTER_TOTAL           # 32 classrooms after renovation

# planned room codes after the renovation (KU3.03.01 is the multimedia room, booking only, so not listed).
# Each faculty gets neighbouring rooms on one floor; the rest is the shared reserve.
_f3 = [f"KU3.03.{i:02d}" for i in range(2, 22)]                                   # floor 3: 03.02-03.21
_f2 = [f"KU3.02.{i:02d}" for i in list(range(6, 12)) + list(range(14, 20))]      # floor 2: 02.06-02.11, 02.14-02.19
ROOM_PLAN = {
    "FEB": _f3[0:6],                      # 03.02-03.07
    "FKS": _f3[6:11],                     # 03.08-03.12
    "FRI": _f3[11:15],                    # 03.13-03.16
    "FIK": _f3[15:17],                    # 03.17-03.18
    "FTE": _f2[0:4],                      # 02.06-02.09
    "FIF": _f2[6:10],                     # 02.14-02.17
    "Reserve": _f3[17:20] + _f2[4:6] + _f2[10:12],   # 03.19-03.21, 02.10-02.11, 02.18-02.19
}
assert sum(len(v) for v in ROOM_PLAN.values()) == TOTAL_AFTER
assert all(len(ROOM_PLAN[f]) == k for f, k in ALLOCATION.items())


def room_label(code, group):
    """'KU3.03.06' + 'FEB' -> '03.06 · FEB'"""
    return f"{code.replace('KU3.', '')} · {'Reserve' if group == 'Reserve' else group}"


def _best_fit(classes, rooms):
    """
    Place classes into the given room labels without changing any time.
    Each day, classes go in order of end time to the room that became free most recently.
    Returns {index: room label} and the list of indexes that did not fit.
    """
    placed, left = {}, []
    for _, d in classes.groupby("day", observed=True):
        free_at = {r: 0 for r in rooms}
        for idx, row in d.sort_values(["end_min", "start_min"]).iterrows():
            fits = [r for r, t in free_at.items() if t <= row.start_min]
            if fits:
                best = max(fits, key=lambda r: free_at[r])
                free_at[best] = row.end_min
                placed[idx] = best
            else:
                left.append(idx)
    return placed, left


def faculty_allocation(schedule, room_plan=ROOM_PLAN):
    """
    Scenario: every faculty gets its own rooms; class times stay exactly as they are.
    A class goes to its faculty's rooms first, and only when they are all busy to a shared
    reserve room. LAC is left out: its classes are scheduled in week 3, into whatever is free.

    Returns the plan (one row per class with its new room), a per-room summary, and any class that did not fit.
    """
    reg = regular(schedule)
    classes = reg[reg.program.isin(FACULTY)].copy()
    classes["faculty"] = classes.program.map(FACULTY)

    plan, overflow = {}, []
    for fac, rooms in room_plan.items():
        if fac == "Reserve":
            continue
        placed, left = _best_fit(classes[classes.faculty == fac], rooms)
        plan.update(placed)
        overflow += left

    placed, not_placed = _best_fit(classes.loc[overflow], room_plan["Reserve"])
    plan.update(placed)

    classes["new_room"] = pd.Series(plan)
    reserve = set(room_plan["Reserve"])
    classes["uses_reserve"] = classes.new_room.isin(reserve)

    available = (CLOSE - OPEN) / 60 * len(WEEKDAYS)
    wk = classes[classes.day.isin(WEEKDAYS)].copy()
    wk["hours_in_ops"] = (wk.end_min.clip(upper=CLOSE) - wk.start_min.clip(lower=OPEN)).clip(lower=0) / 60
    rooms = pd.DataFrame([{"room": r, "group": g} for g, rs in room_plan.items() for r in rs])
    rooms["floor"] = rooms.room.str.split(".").str[1].astype(int)
    rooms["label"] = [room_label(r, g) for r, g in zip(rooms.room, rooms.group)]
    rooms = rooms.merge(wk.groupby("new_room").hours_in_ops.sum().rename("booked_hours"),
                        left_on="room", right_index=True, how="left").fillna({"booked_hours": 0})
    rooms["utilization"] = rooms.booked_hours / available
    rooms["free_hours"] = available - rooms.booked_hours
    return classes, rooms, not_placed
