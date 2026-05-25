#!/usr/bin/env python3

import argparse
import html
import sqlite3
from datetime import datetime
from pathlib import Path


LECONS_TOTAL = 68
DEV_CASES_TOTAL = 2 * LECONS_TOTAL

STATUS_LABELS = {
    1: "vide",
    2: "en réflexion",
    3: "rédaction",
    4: "écrit",
    5: "maîtrisé",
}


STATUS_CLASSES = {
    1: "status-1",
    2: "status-2",
    3: "status-3",
    4: "status-4",
    5: "status-5",
}


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def scalar(conn: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    return conn.execute(query, params).fetchone()[0]


def percent(value: int | float, total: int | float) -> str:
    if total == 0:
        return "0.0"
    return f"{100 * value / total:.1f}"


def build_status_bars(status_counts: dict[int, int]) -> str:
    rows = []

    for status in range(1, 6):
        count = status_counts.get(status, 0)
        width = 100 * count / LECONS_TOTAL
        label = html.escape(STATUS_LABELS[status])
        css_class = STATUS_CLASSES[status]

        rows.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">
                <span class="status-dot {css_class}"></span>
                <span>{status}. {label}</span>
              </div>
              <div class="bar-track">
                <div class="bar-fill {css_class}" style="width: {width:.2f}%"></div>
              </div>
              <div class="bar-count">{count}</div>
            </div>
            """
        )

    return "\n".join(rows)


def collect_data(conn: sqlite3.Connection) -> dict[str, str]:
    lecons_written = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM lecons
        WHERE status >= 4
        """,
    )

    status_rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM lecons
        GROUP BY status
        """
    ).fetchall()

    status_counts = {
        int(row["status"]): int(row["count"])
        for row in status_rows
    }

    dev_cases_filled = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM lecon_devs
        """,
    )

    dev_total = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM devs
        """,
    )

    average_recasage = (
        dev_cases_filled / dev_total
        if dev_total > 0
        else 0
    )

    return {
        "LECONS_WRITTEN": str(lecons_written),
        "LECONS_TOTAL": str(LECONS_TOTAL),
        "LECONS_PERCENT": percent(lecons_written, LECONS_TOTAL),
        "STATUS_BARS": build_status_bars(status_counts),
        "DEV_CASES_FILLED": str(dev_cases_filled),
        "DEV_CASES_TOTAL": str(DEV_CASES_TOTAL),
        "DEV_PERCENT": percent(dev_cases_filled, DEV_CASES_TOTAL),
        "DEV_AVERAGE_RECASAGE": f"{average_recasage:.2f}",
        "DEV_TOTAL": str(dev_total),
        "GENERATED_AT": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def render_template(template: str, data: dict[str, str]) -> str:
    rendered = template

    for key, value in data.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)

    return rendered


def generate_dashboard(
    db_path: Path = Path("agreg.db"),
    template_path: Path = Path("template.html"),
    output_path: Path = Path("index.html"),
) -> Path:
    conn = connect(db_path)
    data = collect_data(conn)

    template = template_path.read_text(encoding="utf-8")
    rendered = render_template(template, data)

    output_path.write_text(rendered, encoding="utf-8")

    return output_path