#!/usr/bin/env python3
"""
Parse Levi's sleep log markdown files into structured JSON data.

Uses File 1 (Levi's Sleep Logs) for January 2025,
and File 2 (2025) for February-December 2025.
"""

import re
import json
from datetime import datetime, timedelta
from pathlib import Path

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

def parse_time(time_str):
    """Parse a time string like '9:35pm' or '8am' into (hour, minute) in 24h format."""
    time_str = time_str.strip().lower().replace(".", "").replace(" ", "")
    m = re.match(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", time_str)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = m.group(3)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return (hour, minute)


def time_to_decimal(hour, minute):
    """Convert hour/minute to decimal hours."""
    return hour + minute / 60.0


def parse_date_cell(date_str):
    """Parse date like 'Jan 1 (Thu) night' or 'Mar 1 (Sat)' into (month, day)."""
    date_str = date_str.strip()
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})", date_str)
    if not m:
        return None
    month_str = m.group(1).lower()
    day = int(m.group(2))
    month = MONTH_MAP.get(month_str)
    if month is None:
        return None
    return (month, day)


def extract_times_from_text(text):
    """
    Extract all time references from a line of sleep text.
    Returns a list of (event_type, hour, minute) tuples.
    event_type is 'sleep' or 'wake'.
    """
    events = []
    text_lower = text.lower()

    skip_patterns = [
        "no events found",
        "no record",
        "no sleep activity",
        "did not sleep",
        "cannot determine",
    ]
    for pat in skip_patterns:
        if pat in text_lower:
            best_est = re.search(r"best estimate is (?:around |after |before )?(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)", text_lower)
            if best_est:
                t = parse_time(best_est.group(1))
                if t:
                    events.append(("sleep", t[0], t[1]))
            return events

    sleep_patterns = [
        r"(?:fell |feel |f)asleep at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m|\d{1,2}:\d{2})",
        r"asleep at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"slept (?:from |at )(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"went back to sleep at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"(?:went |go )back to sleep at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"slept again at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"fell back asleep at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
    ]

    wake_patterns = [
        r"woke\.?\s*up (?:at |again at )(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"awake (?:at |from )(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"is awake at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        r"was awake (?:from |at )(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
    ]

    for pat in sleep_patterns:
        for m in re.finditer(pat, text_lower):
            t = parse_time(m.group(1))
            if t:
                events.append(("sleep", t[0], t[1]))

    for pat in wake_patterns:
        for m in re.finditer(pat, text_lower):
            t = parse_time(m.group(1))
            if t:
                events.append(("wake", t[0], t[1]))

    awake_range = re.findall(
        r"awake (?:at |from |between )?(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)\s*[-–]\s*(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        text_lower
    )
    for start_str, end_str in awake_range:
        t_start = parse_time(start_str)
        t_end = parse_time(end_str)
        if t_start:
            events.append(("wake", t_start[0], t_start[1]))
        if t_end:
            events.append(("sleep", t_end[0], t_end[1]))

    semicolon_parts = text_lower.split(";")
    if len(semicolon_parts) > 1:
        for part in semicolon_parts[1:]:
            for pat in sleep_patterns:
                for m in re.finditer(pat, part):
                    t = parse_time(m.group(1))
                    if t:
                        events.append(("sleep", t[0], t[1]))

    and_sleep = re.findall(
        r"and (?:woke\.?\s*up|awake) at (\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m)",
        text_lower
    )
    for time_str in and_sleep:
        t = parse_time(time_str)
        if t:
            events.append(("wake", t[0], t[1]))

    seen = set()
    deduped = []
    for e in events:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    return deduped


def parse_markdown_table(filepath):
    """Parse a markdown file with sleep log table. Returns dict of {(month, day): [lines]}."""
    nights = {}
    current_date = None

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue

            cols = line.split("|")
            if len(cols) < 4:
                continue

            date_cell = cols[1].strip()
            activity = cols[2].strip() if len(cols) > 2 else ""

            if date_cell in ("Date", "---", ""):
                pass
            else:
                parsed = parse_date_cell(date_cell)
                if parsed:
                    current_date = parsed
                    if current_date not in nights:
                        nights[current_date] = []

            if date_cell in ("Date", "---"):
                continue

            if current_date and activity:
                nights[current_date].append(activity)

    return nights


def process_night(date_tuple, lines):
    """
    Process a single night's data into structured format.
    Returns a dict with bedtime, wake_time, total_sleep_hours, night_wakings, etc.
    """
    year, month, day = date_tuple
    date_str = f"{year}-{month:02d}-{day:02d}"

    all_events = []
    is_nap = False
    for line in lines:
        if "nap" in line.lower():
            is_nap = True
            continue
        events = extract_times_from_text(line)
        all_events.extend(events)

    seen = set()
    deduped = []
    for e in all_events:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    all_events = deduped

    if not all_events:
        return {
            "date": date_str,
            "bedtime": None,
            "wake_time": None,
            "total_sleep_hours": None,
            "total_awake_hours": None,
            "night_wakings": 0,
            "waking_details": [],
            "slept_through": None,
            "raw_notes": " | ".join(lines),
        }

    sleep_events = [(e[1], e[2]) for e in all_events if e[0] == "sleep"]
    wake_events = [(e[1], e[2]) for e in all_events if e[0] == "wake"]

    bedtime = sleep_events[0] if sleep_events else None
    final_wake = wake_events[-1] if wake_events else None

    bedtime_decimal = None
    if bedtime:
        h, m = bedtime
        bedtime_decimal = time_to_decimal(h, m)
        if bedtime_decimal < 12:
            bedtime_decimal += 24

    wake_decimal = None
    if final_wake:
        h, m = final_wake
        wake_decimal = time_to_decimal(h, m)
        if wake_decimal < 12:
            wake_decimal += 24

    waking_details = []

    ordered_events = []
    for e in all_events:
        h, m = e[1], e[2]
        dec = time_to_decimal(h, m)
        if dec < 12:
            dec += 24
        ordered_events.append((dec, e[0], h, m))

    ordered_events.sort(key=lambda x: x[0])

    total_sleep = 0
    last_sleep_time = None

    for dec, etype, h, m in ordered_events:
        if etype == "sleep":
            last_sleep_time = dec
        elif etype == "wake":
            if last_sleep_time is not None:
                total_sleep += dec - last_sleep_time
                last_sleep_time = None

    if last_sleep_time is not None and wake_decimal is not None:
        pass

    if total_sleep == 0 and bedtime_decimal and wake_decimal:
        total_sleep = wake_decimal - bedtime_decimal

    night_waking_count = 0
    if len(ordered_events) > 2:
        for i, (dec, etype, h, m) in enumerate(ordered_events):
            if etype == "wake" and i > 0 and i < len(ordered_events) - 1:
                night_waking_count += 1
                next_sleep = None
                for j in range(i + 1, len(ordered_events)):
                    if ordered_events[j][1] == "sleep":
                        next_sleep = ordered_events[j]
                        break
                duration = None
                if next_sleep:
                    duration = round(next_sleep[0] - dec, 2)
                waking_details.append({
                    "wake_time": f"{h}:{m:02d}",
                    "duration_hours": duration,
                })
            elif etype == "wake" and i == len(ordered_events) - 1 and i > 1:
                pass

    if len(wake_events) == 1 and len(sleep_events) == 1:
        night_waking_count = 0
        waking_details = []

    total_awake = sum(
        w["duration_hours"] for w in waking_details
        if w["duration_hours"] is not None
    )

    bedtime_str = None
    if bedtime:
        h, m = bedtime
        ampm = "am" if h < 12 else "pm"
        display_h = h % 12
        if display_h == 0:
            display_h = 12
        bedtime_str = f"{display_h}:{m:02d}{ampm}"

    wake_str = None
    if final_wake:
        h, m = final_wake
        ampm = "am" if h < 12 else "pm"
        display_h = h % 12
        if display_h == 0:
            display_h = 12
        wake_str = f"{display_h}:{m:02d}{ampm}"

    return {
        "date": date_str,
        "bedtime": bedtime_str,
        "bedtime_decimal": round(bedtime_decimal, 2) if bedtime_decimal else None,
        "wake_time": wake_str,
        "wake_time_decimal": round(wake_decimal, 2) if wake_decimal else None,
        "total_sleep_hours": round(total_sleep, 2) if total_sleep > 0 else None,
        "total_awake_hours": round(total_awake, 2) if total_awake > 0 else None,
        "night_wakings": night_waking_count,
        "waking_details": waking_details,
        "slept_through": night_waking_count == 0 and bedtime is not None,
        "raw_notes": " | ".join(lines),
    }


def main():
    base_dir = Path(__file__).parent / "Raw data"

    file1 = None
    file2 = None
    for f in base_dir.iterdir():
        if f.name.startswith("Levi") and f.suffix == ".md":
            file1 = f
        elif f.name.startswith("2025") and f.suffix == ".md":
            file2 = f

    if not file1 or not file2:
        print("Could not find both data files in Raw data/")
        return

    nights1 = parse_markdown_table(file1)  # "Levi's Sleep Logs" = Jan-Mar 2026
    nights2 = parse_markdown_table(file2)  # "2025" = Feb-Dec 2025

    merged = {}

    for (month, day), lines in nights2.items():
        key = (2025, month, day)
        merged[key] = lines

    for (month, day), lines in nights1.items():
        key = (2026, month, day)
        merged[key] = lines

    results = []
    for date_tuple in sorted(merged.keys()):
        result = process_night(date_tuple, merged[date_tuple])
        results.append(result)

    json_path = Path(__file__).parent / "sleep_data.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    js_path = Path(__file__).parent / "sleep_data.js"
    with open(js_path, "w") as f:
        f.write("const SLEEP_DATA = ")
        json.dump(results, f, indent=2)
        f.write(";\n")

    valid = [r for r in results if r["total_sleep_hours"] is not None]
    print(f"Parsed {len(results)} nights ({len(valid)} with calculable sleep data)")
    print(f"Date range: {results[0]['date']} to {results[-1]['date']}")
    print(f"Output: {json_path}")
    print(f"Output: {js_path}")

    print("\nSample entries:")
    for r in results[:5]:
        print(f"  {r['date']}: bed={r['bedtime']}, wake={r['wake_time']}, "
              f"sleep={r['total_sleep_hours']}h, wakings={r['night_wakings']}")


if __name__ == "__main__":
    main()
