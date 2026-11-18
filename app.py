"""
Classroom occupancy dashboard for the international classrooms (ICAO, Telkom University).
Run:  streamlit run app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import occupancy as oc

# ------------------------------------------------------------------ look
NAVY, BLUE, RED, INK, MUTED, LINE = "#14213D", "#2A78D6", "#D03B3B", "#14213D", "#5B6475", "#E3E8F0"
FREE, BUSY = "#EEF2F8", "#2A78D6"
SEQ = [[0, "#F4F8FD"], [0.2, "#CDE2FB"], [0.4, "#86B6EF"], [0.6, "#3987E5"], [0.8, "#1C5CAB"], [1, "#0D366B"]]
FAC_COLORS = {"FEB": "#2A78D6", "FKS": "#EB6834", "FRI": "#1BAF7A", "FTE": "#EDA100", "FIF": "#E87BA4", "FIK": "#008300",
              "Reserve": "#9AA5B8"}
PLOT_CONFIG = {"displayModeBar": False}

st.set_page_config(page_title="Classroom Occupancy · ICAO", layout="wide")

st.markdown(f"""
<style>
  #MainMenu, footer, header [data-testid="stToolbar"] {{visibility: hidden;}}
  .block-container {{padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px;}}
  .hero {{background: {NAVY}; border-radius: 12px; padding: 22px 28px; margin-bottom: 18px;
          border-left: 6px solid {BLUE};}}
  .hero h1 {{color: #fff; font-size: 26px; margin: 0; padding: 0; font-weight: 600;}}
  .hero p {{color: #AFC2E0; margin: 4px 0 0; font-size: 14px;}}
  .kpi {{background: #fff; border: 1px solid {LINE}; border-radius: 10px; padding: 14px 18px; height: 100%;}}
  .kpi .label {{color: {MUTED}; font-size: 13px; margin-bottom: 4px;}}
  .kpi .value {{color: {INK}; font-size: 28px; font-weight: 600; line-height: 1.1;}}
  .kpi .note {{color: {MUTED}; font-size: 12px; margin-top: 4px;}}
  .section {{color: {INK}; font-size: 17px; font-weight: 600; margin: 18px 0 2px;}}
  .hint {{color: {MUTED}; font-size: 13px; margin: 0 0 8px;}}
  .chip {{display: inline-block; background: #E8F1FC; color: {NAVY}; border: 1px solid #CDE2FB;
          border-radius: 6px; padding: 3px 9px; margin: 0 6px 6px 0; font-size: 13px; font-weight: 500;}}
  .result {{color: {INK}; font-size: 15px; margin: 6px 0 8px;}}
  .warn {{color: #8A4B00; background: #FFF4E0; border-radius: 6px; padding: 6px 10px; font-size: 13px; margin-bottom: 8px;}}
  .source {{color: {MUTED}; font-size: 12px; margin-top: 28px; border-top: 1px solid {LINE}; padding-top: 10px;}}
  button[data-baseweb="tab"] p {{font-size: 15px;}}
</style>
""", unsafe_allow_html=True)


def kpi(col, label, value, note=""):
    col.markdown(f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div>'
                 f'<div class="note">{note}</div></div>', unsafe_allow_html=True)


def section(title, hint=""):
    st.markdown(f'<div class="section">{title}</div>' + (f'<div class="hint">{hint}</div>' if hint else ""),
                unsafe_allow_html=True)


def styled(fig, height):
    fig.update_layout(height=height, margin={"l": 8, "r": 8, "t": 8, "b": 8},
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"family": "Inter, Segoe UI, sans-serif", "size": 12, "color": INK},
                      hoverlabel={"bgcolor": "#fff", "font_size": 12})
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont={"color": MUTED})
    fig.update_yaxes(gridcolor=LINE, zeroline=False, tickfont={"color": MUTED})
    return fig


def show(fig):
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)


# ------------------------------------------------------------------ data
@st.cache_data
def load():
    schedule, rooms = oc.load()
    reg = oc.regular(schedule)
    return schedule, rooms, reg, oc.concurrency(reg, until=oc.CLOSE + 60), oc.room_utilization(reg, rooms)


@st.cache_data
def overtime(max_shift):
    schedule, rooms = oc.load()
    return oc.overtime_options(schedule, rooms, max_shift_hours=max_shift)


@st.cache_data
def allocation():
    schedule, _ = oc.load()
    return oc.faculty_allocation(schedule)


@st.cache_data
def issues():
    schedule, _ = oc.load()
    return oc.data_issues(schedule)


schedule, rooms, reg, grid, util = load()
NOW, AFTER = len(rooms), oc.ROOMS_AFTER_TOTAL
TIMES = [oc.to_hhmm(m) for m in range(oc.OPEN, oc.CLOSE, oc.SLOT)]
SLOTS = list(range(oc.OPEN, oc.CLOSE + 60, oc.SLOT))
short = lambda r: r.replace("KU3.", "")
wk = grid.loc[oc.WEEKDAYS]
PEAK = int(wk.max().max())

# ------------------------------------------------------------------ header
st.markdown(f"""<div class="hero"><h1>International Classroom Occupancy</h1>
<p>ICAO · Telkom University · Gedung Tokong Nanas · odd semester 2026/2027 · {len(schedule)} classes a week</p></div>""",
            unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
kpi(c1, "Average room use", f"{util.utilization.mean():.0%}", "Mon to Fri, 06:30 to 17:30")
kpi(c2, "Rooms under 30% use", f"{(util.utilization < .30).sum()} of {NOW}", "no room reaches 75%")
kpi(c3, "Most rooms in use at once", f"{PEAK}", "Wednesday 14:30")
kpi(c4, "Classrooms after renovation", f"{AFTER}", f"{AFTER - PEAK} still free at the busiest moment")
st.write("")

tabs = st.tabs(["Overview", "Faculty rooms", "Find a free room", "Replacement class", "Overtime", "Timetable checks"])

# ------------------------------------------------------------------ overview
with tabs[0]:
    section("Rooms in use every 30 minutes", "Darker means busier. The dashed line is the 17:30 closing time.")
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=grid.columns, y=grid.index, colorscale=SEQ, zmin=0, zmax=NOW,
        text=grid.values, texttemplate="%{text}", textfont={"size": 11},
        hovertemplate="%{y} %{x}<br>%{z} rooms in use<extra></extra>", showscale=False, xgap=2, ygap=2))
    fig.add_vline(x=list(grid.columns).index("17:30") - .5, line_dash="dash", line_color=RED, line_width=1.5)
    show(styled(fig, 300).update_yaxes(autorange="reversed", showgrid=False))

    section("Use per room", f"Hours booked ÷ 55 hours a week. Gray bars are under 30%. Average {util.utilization.mean():.0%}.")
    fl = st.segmented_control("Floor", ["All", "Floor 3", "Floor 9"], default="All", key="util_floor")
    u = util if fl in (None, "All") else util[util.floor == int(fl[-1])]
    fig = go.Figure(go.Bar(
        x=u.room_id.map(short).tolist(), y=u.utilization * 100,
        marker={"color": ["#B9C3D3" if x < .30 else BLUE for x in u.utilization], "cornerradius": 4},
        text=[f"{x:.0%}" for x in u.utilization], textposition="outside", textfont={"size": 10, "color": MUTED},
        customdata=u.booked_hours, hovertemplate="%{x}<br>%{y:.0f}% used<br>%{customdata:.0f} of 55 hours<extra></extra>"))
    fig.add_hline(y=75, line_dash="dot", line_color=RED, annotation_text="75% target",
                  annotation_position="top right", annotation_font={"color": RED, "size": 11})
    show(styled(fig, 340).update_layout(yaxis_range=[0, 100], xaxis={"type": "category"}))

# ------------------------------------------------------------------ faculty rooms
with tabs[1]:
    plan, plan_rooms, not_placed = allocation()
    n_res = AFTER - sum(oc.ALLOCATION.values())
    res = plan[plan.uses_reserve]
    res_peak = oc.concurrency(res).loc[oc.DAYS].max().max() if len(res) else 0
    lac = reg[reg.program == "LAC"]
    total_peak = oc.concurrency(pd.concat([plan, lac])).loc[oc.DAYS].max().max()

    st.markdown('<div class="hint" style="margin-top:8px">Scenario: each faculty has its own rooms and class times stay '
                'as they are. A class uses a shared reserve room only when its faculty\'s rooms are all busy. '
                'LAC is added in week 3. Room codes are the planned ones after the renovation.</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "Faculty rooms + reserve", f"{sum(oc.ALLOCATION.values())} + {n_res}", "KU3.03.01 multimedia not included")
    kpi(c2, "Classes that fit", f"{len(plan) - len(not_placed)} of {len(plan)}", "no class time moved")
    kpi(c3, "Classes in a reserve room", f"{len(res)}", "per week")
    kpi(c4, "Reserve rooms always free", f"{n_res - res_peak} of {n_res}", f"with LAC: {total_peak} of {AFTER} rooms at peak")

    pr = plan_rooms.copy()
    order = pr.room.tolist()
    label_of = dict(zip(pr.room, pr.label))
    by_fac = (plan.groupby("faculty").agg(classes=("session_id", "count"), in_reserve=("uses_reserve", "sum"))
              .join(plan_rooms[plan_rooms.group != "Reserve"].groupby("group")
                    .agg(rooms=("room", "count"), avg_use=("utilization", "mean"), free_hours=("free_hours", "sum")))
              .loc[[g for g in oc.ROOM_PLAN if g != "Reserve"]].reset_index())
    by_fac["codes"] = [f"{short(oc.ROOM_PLAN[f][0])} – {short(oc.ROOM_PLAN[f][-1])}" for f in by_fac.faculty]

    left, right = st.columns([1.1, 1])
    with left:
        section("Average use per faculty")
        fig = go.Figure(go.Bar(
            y=by_fac.faculty, x=by_fac.avg_use * 100, orientation="h",
            marker={"color": [FAC_COLORS[f] for f in by_fac.faculty], "cornerradius": 5},
            text=[f"{u:.0%}" for u in by_fac.avg_use], textposition="outside", textfont={"color": MUTED},
            customdata=by_fac[["rooms", "codes", "classes", "free_hours"]].values,
            hovertemplate="%{y} · %{customdata[0]} rooms (%{customdata[1]})<br>%{x:.0f}% average use"
                          "<br>%{customdata[2]} classes a week<br>%{customdata[3]:.0f} free hours a week<extra></extra>"))
        fig.add_vline(x=75, line_dash="dot", line_color=RED, annotation_text="75% target", annotation_position="top",
                      annotation_font={"color": RED, "size": 11})
        show(styled(fig, 290).update_layout(xaxis_range=[0, 100], margin={"t": 24})
             .update_yaxes(autorange="reversed", showgrid=False))
    with right:
        section("Rooms per faculty", "FRI, FTE and FIF still teach part of their classes in other buildings.")
        st.dataframe(by_fac[["faculty", "codes", "classes", "in_reserve", "avg_use"]]
                     .rename(columns={"faculty": "Faculty", "codes": "Rooms", "classes": "Classes / week",
                                      "in_reserve": "In reserve", "avg_use": "Avg use"})
                     .style.format({"Avg use": "{:.0%}"}), width="stretch", hide_index=True)

    section("Use per room", "Color shows the faculty, gray is the shared reserve.")
    fig = go.Figure(go.Bar(
        x=[short(r) for r in pr.room], y=pr.utilization * 100,
        marker={"color": [FAC_COLORS[g] for g in pr.group], "cornerradius": 4},
        text=[f"{u:.0%}" if u > 0 else "" for u in pr.utilization], textposition="outside",
        textfont={"size": 10, "color": MUTED}, customdata=pr[["group", "free_hours"]].values,
        hovertemplate="%{x} · %{customdata[0]}<br>%{y:.0f}% used<br>%{customdata[1]:.0f} free hours a week<extra></extra>"))
    fig.add_hline(y=75, line_dash="dot", line_color=RED)
    pos = 0
    for g, rs in oc.ROOM_PLAN.items():
        fig.add_annotation(x=pos + (len(rs) - 1) / 2, y=100, text="Reserve" if g == "Reserve" else g, showarrow=False,
                           font={"color": MUTED, "size": 12})
        if pos:
            fig.add_vline(x=pos - .5, line_color=LINE, line_width=1)
        pos += len(rs)
    show(styled(fig, 340).update_layout(yaxis_range=[0, 106], xaxis={"type": "category"}))

    section("Room timetable", "Hover a block to see the class.")
    pick = st.segmented_control("Day", oc.WEEKDAYS, default="Mon", key="scenario_day") or "Mon"
    groups = list(FAC_COLORS)
    day_plan = plan[plan.day == pick]
    z, txt = [], []
    for room in order:
        rz, rt = [], []
        here = day_plan[day_plan.new_room == room]
        for t in SLOTS:
            hit = here[(here.start_min <= t) & (here.end_min > t)]
            if len(hit):
                h = hit.iloc[0]
                rz.append(groups.index(h.faculty) + 1)
                rt.append(f"{h.course_name}<br>{h.class_group}<br>{h.start_time}-{h.end_time}")
            else:
                rz.append(0)
                rt.append("free")
        z.append(rz)
        txt.append(rt)
    n = len(groups)
    scale = [[0, FREE], [1 / (n + 1), FREE]]
    for i, g in enumerate(groups, start=1):
        scale += [[i / (n + 1), FAC_COLORS[g]], [(i + 1) / (n + 1), FAC_COLORS[g]]]
    fig = go.Figure(go.Heatmap(
        z=z, x=[oc.to_hhmm(t) for t in SLOTS], y=[label_of[r] for r in order], customdata=txt,
        colorscale=scale, zmin=0, zmax=n + 1, showscale=False, xgap=1, ygap=2,
        hovertemplate="%{y} · %{x}<br>%{customdata}<extra></extra>"))
    show(styled(fig, 24 * len(order) + 40).update_layout(xaxis={"type": "category"})
         .update_yaxes(autorange="reversed", type="category", showgrid=False))

    with st.expander("Room plan as a table"):
        fac = st.selectbox("Faculty", list(oc.ROOM_PLAN))
        sel = plan[plan.new_room.isin(oc.ROOM_PLAN[fac])]
        st.dataframe(sel.assign(room=sel.new_room.map(short), day=sel.day.astype(str),
                                time=sel.start_time + "-" + sel.end_time, current_room=sel.room_id.map(short))
                     [["room", "day", "time", "course_name", "class_group", "current_room"]]
                     .sort_values(["room", "day", "time"])
                     .rename(columns={"room": "Room", "day": "Day", "time": "Time", "course_name": "Course",
                                      "class_group": "Class", "current_room": "Room now"}),
                     width="stretch", hide_index=True)

# ------------------------------------------------------------------ find a free room
with tabs[2]:
    st.markdown('<div class="hint" style="margin-top:8px">For bookings and quick replacement classes. '
                'Lists rooms with nothing scheduled for the whole time.</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns([1, 1, 1, 2])
    day = a.selectbox("Day", oc.DAYS, index=0)
    start = b.selectbox("Start", TIMES, index=TIMES.index("13:30"))
    hours = c.selectbox("Duration", [1, 1.5, 2, 2.5, 3, 4], index=2, format_func=lambda h: f"{h:g} h")
    floors = d.multiselect("Floor", sorted(rooms.floor.unique()), default=sorted(rooms.floor.unique()),
                           format_func=lambda f: f"Floor {f}")

    s = oc.to_min(start)
    e = int(s + hours * 60)
    free = oc.free_rooms(schedule, rooms, day, s, e, floors)
    if e > oc.CLOSE:
        st.markdown(f'<div class="warn">Ends at {oc.to_hhmm(e)}, after the 17:30 closing time.</div>', unsafe_allow_html=True)
    if day == "Fri" and oc.overlaps(s, e, *oc.FRIDAY_PRAYER):
        st.markdown('<div class="warn">Overlaps Friday prayer (11:30 to 12:30).</div>', unsafe_allow_html=True)
    if free:
        st.markdown(f'<div class="result"><b>{len(free)} rooms free</b> on {day}, {start} to {oc.to_hhmm(e)}</div>'
                    + "".join(f'<span class="chip">{short(r)}</span>' for r in free), unsafe_allow_html=True)
    else:
        st.markdown('<div class="result">No room is free for the whole time. Try a shorter slot or another time.</div>',
                    unsafe_allow_html=True)

    section(f"Room timeline, {day}", "Blue is booked, light is free. Hover a block to see the class.")
    rlist = rooms[rooms.floor.isin(floors)].room_id.tolist()
    dsched = schedule[schedule.day == day]
    z, txt = [], []
    for r in rlist:
        rz, rt = [], []
        for t in SLOTS:
            hit = dsched[(dsched.room_id == r) & (dsched.start_min <= t) & (dsched.end_min > t)]
            rz.append(1 if len(hit) else 0)
            rt.append(f"{hit.iloc[0].course_name}<br>{hit.iloc[0].class_group}<br>{hit.iloc[0].start_time}-{hit.iloc[0].end_time}"
                      if len(hit) else "free")
        z.append(rz)
        txt.append(rt)
    fig = go.Figure(go.Heatmap(
        z=z, x=[oc.to_hhmm(t) for t in SLOTS], y=[short(r) for r in rlist], customdata=txt,
        colorscale=[[0, FREE], [1, BUSY]], zmin=0, zmax=1, showscale=False, xgap=1, ygap=2,
        hovertemplate="%{y} · %{x}<br>%{customdata}<extra></extra>"))
    show(styled(fig, max(300, 22 * len(rlist) + 40)).update_layout(xaxis={"type": "category"})
         .update_yaxes(autorange="reversed", type="category", showgrid=False))

# ------------------------------------------------------------------ replacement class
with tabs[3]:
    st.markdown('<div class="hint" style="margin-top:8px">Finds times when a room, the class and the lecturer are all free '
                'in this timetable. Classes in other buildings are not in the data, so confirm with the lecturer first.</div>',
                unsafe_allow_html=True)
    a, b = st.columns(2)
    groups_list = sorted(g for g in schedule.class_group.unique() if g not in oc.SHARED_GROUP_LABELS)
    group = a.selectbox("Class", groups_list)
    courses = schedule[schedule.class_group == group].drop_duplicates("course_name")
    course = b.selectbox("Course", courses.course_name)
    row = courses[courses.course_name == course].iloc[0]

    a, b, c = st.columns([1, 2, 2])
    length = a.selectbox("Duration", [1, 2, 3, 4], index=[1, 2, 3, 4].index(int(min(max(row.duration_hours, 1), 4))),
                         format_func=lambda h: f"{h} h")
    days = b.multiselect("Days", oc.DAYS, default=oc.WEEKDAYS)
    rfloors = c.multiselect("Floor ", sorted(rooms.floor.unique()), default=sorted(rooms.floor.unique()),
                            format_func=lambda f: f"Floor {f}")
    st.markdown(f'<div class="hint">Lecturer {row.lecturer_id} · usually {row.day} {row.start_time}-{row.end_time} '
                f'in {short(row.room_id)}</div>', unsafe_allow_html=True)

    options = oc.find_slots(schedule, rooms, length * 60, group, row.lecturer_id, days=days, floors=rfloors, step=60)
    if options.empty:
        st.markdown('<div class="result">No slot inside operating hours. Try a shorter class or more days.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="result"><b>{len(options)} possible slots</b> for {length} hours</div>',
                    unsafe_allow_html=True)
        st.dataframe(options.assign(rooms=options.rooms.map(lambda r: ", ".join(short(x) for x in r)))
                     .rename(columns={"day": "Day", "start": "Start", "end": "End", "free_rooms": "Free rooms",
                                      "rooms": "Rooms"}), width="stretch", hide_index=True)

# ------------------------------------------------------------------ overtime
with tabs[4]:
    max_shift = st.segmented_control("Start up to", [1, 2], default=2, key="shift",
                                     format_func=lambda h: f"{h} hour{'s' if h > 1 else ''} earlier") or 2
    opt = overtime(max_shift)
    has = (opt.alternatives > 0).sum()
    st.markdown(f'<div class="result"><b>{len(opt)} weekday classes</b> end after 17:30. '
                f'<b>{has}</b> have a free earlier slot in this timetable, {len(opt) - has} have none.</div>'
                '<div class="hint">These are options to discuss with the lecturer and study program, not changes. '
                'Lecturers may teach in other buildings at those times.</div>', unsafe_allow_html=True)
    st.dataframe(opt.assign(day=opt.day.astype(str), current_room=opt.current_room.map(short))
                 [["course_name", "class_group", "lecturer_id", "day", "current_time", "current_room", "alternatives", "options"]]
                 .rename(columns={"course_name": "Course", "class_group": "Class", "lecturer_id": "Lecturer", "day": "Day",
                                  "current_time": "Time now", "current_room": "Room", "alternatives": "Options",
                                  "options": "Earlier slots (free rooms)"}),
                 width="stretch", hide_index=True)

# ------------------------------------------------------------------ timetable checks
with tabs[5]:
    iss = issues()
    st.markdown(f'<div class="result"><b>{len(iss)} entries</b> to check before the timetable is final.</div>'
                '<div class="hint">LAC classes are not checked: LAC runs its own packages with parallel groups.</div>',
                unsafe_allow_html=True)
    st.dataframe(iss.assign(day=iss.day.astype(str)).rename(columns={"issue": "Issue", "day": "Day", "sessions": "Sessions",
                                                                     "detail": "Detail"}),
                 width="stretch", hide_index=True)

st.markdown('<div class="source">Source: ICAO timetable export, odd semester 2026/2027. Lecturer codes are anonymized. '
            'Operating hours 06:30 to 17:30.</div>', unsafe_allow_html=True)
