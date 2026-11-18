"""
Clean the timetable export and make it safe to publish.

Input : data/raw/jadwal_2627_1.xlsx   (export from the timetable system, not in the repo)
Output: data/schedule.csv, data/rooms_current.csv

What happens here:
- columns renamed to English, day names shortened (SENIN -> Mon, ...)
- lecturer codes replaced with anonymous IDs (L001, L002, ...)
- lecturer name, NIP and student count are dropped (empty or zero in the export)
- floor taken from the room code (KU3.03.xx -> floor 3, KU3.09.xx -> floor 9)

Run:  python scripts/prepare_data.py
"""

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "jadwal_2627_1.xlsx"

DAY_MAP = {"SENIN": "Mon", "SELASA": "Tue", "RABU": "Wed", "KAMIS": "Thu", "JUMAT": "Fri", "SABTU": "Sat"}
DAYS = list(DAY_MAP.values())


def main():
    raw = pd.read_excel(RAW, dtype=str)

    df = pd.DataFrame({
        "course_code": raw["KODE MATA KULIAH"].fillna("-"),
        "course_name": raw["MATA KULIAH"].str.strip(),
        "class_group": raw["KELAS"].str.strip(),
        "program": raw["PROGRAM STUDI"].str.strip(),
        "lecturer": raw["KODE DOSEN"].str.strip(),
        "day": raw["HARI"].str.strip().map(DAY_MAP),
        "start_time": raw["JAM MULAI"].str.strip(),
        "end_time": raw["JAM SELESAI"].str.strip(),
        "room_id": raw["RUANGAN"].str.strip(),
        "valid_from": raw["BERLAKU MULAI"].str[:10],
    })
    assert df["day"].notna().all(), "unknown day name in export"

    # anonymous lecturer IDs (shuffled so the order says nothing about the real codes)
    codes = sorted(df["lecturer"].unique())
    np.random.default_rng(7).shuffle(codes)
    df["lecturer_id"] = df["lecturer"].map({c: f"L{i:03d}" for i, c in enumerate(codes, 1)})
    df = df.drop(columns="lecturer")

    to_min = lambda t: int(t[:2]) * 60 + int(t[3:5])
    df["duration_hours"] = (df["end_time"].map(to_min) - df["start_time"].map(to_min)) / 60
    df["floor"] = df["room_id"].str.split(".").str[1].astype(int)

    df["day"] = pd.Categorical(df["day"], DAYS, ordered=True)
    df = df.sort_values(["day", "start_time", "room_id"]).reset_index(drop=True)
    df.insert(0, "session_id", [f"S{i:03d}" for i in range(1, len(df) + 1)])
    cols = ["session_id", "course_code", "course_name", "class_group", "program", "lecturer_id",
            "day", "start_time", "end_time", "duration_hours", "room_id", "floor", "valid_from"]
    df[cols].to_csv(ROOT / "data" / "schedule.csv", index=False)

    rooms = (df[["room_id", "floor"]].drop_duplicates().sort_values("room_id")
             .assign(room_type="classroom", capacity=40))
    rooms.to_csv(ROOT / "data" / "rooms_current.csv", index=False)

    print(f"classes: {len(df)} | rooms: {len(rooms)} | class groups: {df.class_group.nunique()} | lecturers: {df.lecturer_id.nunique()}")


if __name__ == "__main__":
    main()
