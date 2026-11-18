"""
Export a star-schema data model for Power BI (or any BI tool).

Output folder: powerbi/data/
  dim_room.csv        one row per room
  dim_day.csv         Mon..Sat with sort order
  dim_slot.csv        30-minute slots 06:30..18:00, with an operating-hours flag
  dim_class.csv       class groups and their study program
  fact_class.csv      one row per weekly class (the cleaned timetable)
  fact_room_slot.csv  one row per room x day x 30-minute slot: occupied or free
  overtime_options.csv, timetable_issues.csv   results from the analysis

Run:  python scripts/export_powerbi.py
"""

from pathlib import Path
import pandas as pd
import occupancy as oc

OUT = oc.ROOT / "powerbi" / "data"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    schedule, rooms = oc.load()
    reg = oc.regular(schedule)

    rooms[["room_id", "floor", "room_type", "capacity"]].to_csv(OUT / "dim_room.csv", index=False)

    names = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday"}
    pd.DataFrame({"day": oc.DAYS, "day_name": [names[d] for d in oc.DAYS], "day_order": range(1, 7),
                  "is_weekday": [d in oc.WEEKDAYS for d in oc.DAYS]}).to_csv(OUT / "dim_day.csv", index=False)

    slots = list(range(oc.OPEN, oc.CLOSE + 60, oc.SLOT))
    pd.DataFrame({"slot": [oc.to_hhmm(m) for m in slots], "slot_order": range(1, len(slots) + 1),
                  "in_operating_hours": [m < oc.CLOSE for m in slots]}).to_csv(OUT / "dim_slot.csv", index=False)

    # one program per class group: a few classes are tagged with a second program on a single row,
    # so the most common program wins (keeps the relationship one-to-many)
    dim_class = (schedule.groupby("class_group")["program"]
                 .agg(lambda x: x.value_counts().index[0]).reset_index())
    dim_class["faculty"] = dim_class.program.map(oc.FACULTY).fillna("LAC")
    dim_class.to_csv(OUT / "dim_class.csv", index=False)

    # whole numbers only, so the CSVs read the same under any regional setting
    fact = schedule.drop(columns=["start_min", "end_min"]).copy()
    fact["duration_hours"] = fact["duration_hours"].astype(int)
    fact["is_overtime"] = (schedule.end_min > oc.CLOSE) & (schedule.start_min < oc.LATE_NIGHT) & schedule.day.isin(oc.WEEKDAYS)
    fact["likely_input_error"] = schedule.start_min >= oc.LATE_NIGHT
    fact.to_csv(OUT / "fact_class.csv", index=False)

    rows = []
    for day in oc.DAYS:
        d = reg[reg.day == day]
        for room in rooms.room_id:
            dr = d[d.room_id == room]
            for m in slots:
                hit = dr[(dr.start_min <= m) & (dr.end_min > m)]
                rows.append({"room_id": room, "day": day, "slot": oc.to_hhmm(m), "occupied": int(len(hit) > 0),
                             "session_id": hit.iloc[0].session_id if len(hit) else "",
                             "course_name": hit.iloc[0].course_name if len(hit) else "",
                             "class_group": hit.iloc[0].class_group if len(hit) else ""})
    pd.DataFrame(rows).to_csv(OUT / "fact_room_slot.csv", index=False)

    opts = oc.overtime_options(schedule, rooms)
    opts["smallest_shift_h"] = opts["smallest_shift_h"].astype("Int64")
    opts.to_csv(OUT / "overtime_options.csv", index=False)
    oc.data_issues(schedule).to_csv(OUT / "timetable_issues.csv", index=False)

    # scenario: each faculty gets its own rooms, class times unchanged
    plan, plan_rooms, _ = oc.faculty_allocation(schedule)
    plan[["session_id", "faculty", "class_group", "course_name", "day", "start_time", "end_time", "room_id", "new_room", "uses_reserve"]] \
        .assign(day=lambda d: d.day.astype(str)).to_csv(OUT / "scenario_plan.csv", index=False)
    # whole numbers only (regional settings read "0.67" differently)
    pd.DataFrame({"room_order": range(1, len(plan_rooms) + 1), "room": plan_rooms.room, "label": plan_rooms.label.str.replace(" · ", " - "), "group": plan_rooms.group, "floor": plan_rooms.floor,
                  "booked_hours": plan_rooms.booked_hours.round().astype(int),
                  "free_hours": plan_rooms.free_hours.round().astype(int),
                  "utilization_pct": (plan_rooms.utilization * 100).round().astype(int),
                  "color": plan_rooms.group.map({"FEB": "#2A78D6", "FKS": "#EB6834", "FRI": "#1BAF7A", "FTE": "#EDA100",
                                                 "FIF": "#E87BA4", "FIK": "#008300", "Reserve": "#9AA5B8"})}
                 ).to_csv(OUT / "scenario_rooms.csv", index=False)

    for f in sorted(OUT.glob("*.csv")):
        print(f"{f.name:24s} {sum(1 for _ in open(f)) - 1:>6} rows")


if __name__ == "__main__":
    main()
