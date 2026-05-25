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


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def build_assoc_html(
    entries: list[tuple[str, bool]],
    selected_label: str,
    unselected_label: str,
) -> str:
    if not entries:
        return ""

    chips: list[str] = []
    for label, is_selected in entries:
        safe_label = html.escape(label)
        if is_selected:
            chips.append(f"<strong>{safe_label}</strong>")
        else:
            chips.append(safe_label)

    return (
        f"<div style=\"margin-top: 0.25rem; font-size: 0.9em; color: #0006; font-weight: 100;\">"
        f"{', '.join(chips)}"
        f"</div>"
    )


def build_detail_rows(
    items: list[sqlite3.Row],
    folder: str,
    id_key: str = "id",
    assoc_by_item: dict[int, list[tuple[str, bool]]] | None = None,
    assoc_selected_label: str = "sélectionné",
    assoc_unselected_label: str = "possible",
) -> str:
    rows: list[str] = []
    pdf_icon = (
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"16\" height=\"16\" fill=\"currentColor\" "
        "class=\"bi bi-eye\" viewBox=\"0 0 16 16\">"
        "<path d=\"M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8M1.173 8a13 13 0 0 1 1.66-2.043C4.12 "
        "4.668 5.88 3.5 8 3.5s3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8q-.086.13-.195.288c-.335.48-.83 "
        "1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5s-3.879-1.168-5.168-2.457A13 13 0 0 1 1.172 8z\"/>"
        "<path d=\"M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0\"/>"
        "</svg>"
    )
    tex_icon = (
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"16\" height=\"16\" fill=\"currentColor\" "
        "class=\"bi bi-pencil\" viewBox=\"0 0 16 16\">"
        "<path d=\"M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 "
        "0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 "
        "3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 "
        "3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325\"/>"
        "</svg>"
    )

    for row in items:
        item_id = int(row[id_key])
        status = int(row["status"])
        status_dot = (
            f"<span class=\"status-dot {STATUS_CLASSES[status]}\" "
            f"title=\"{html.escape(STATUS_LABELS[status])}\"></span>"
        )

        if status >= 3:
            pdf_href = f"{item_id}.pdf"
            tex_path = f"/home/constance/Documents/agreg_tex/{folder}/{item_id}.tex"
            tex_href = f"vscodium://file{tex_path}"
            actions = (
                f"<div class=\"status-actions\">{status_dot}"
                f"<a class=\"action-icon\" href=\"{pdf_href}\" target=\"_blank\" rel=\"noopener\" title=\"Ouvrir le PDF\">{pdf_icon}</a>"
                f"<a class=\"action-icon\" href=\"{tex_href}\" title=\"Ouvrir le TEX\">{tex_icon}</a>"
                f"</div>"
            )
        else:
            actions = f"<div class=\"status-actions\">{status_dot}</div>"

        assoc_html = ""
        if assoc_by_item is not None:
            assoc_html = build_assoc_html(
                assoc_by_item.get(item_id, []),
                assoc_selected_label,
                assoc_unselected_label,
            )

        rows.append(
            f"<tr><td>{item_id}</td><td>{html.escape(str(row['name']))}{assoc_html}</td><td>{actions}</td></tr>"
        )

    return "\n".join(rows)


def generate_lecons_page(conn: sqlite3.Connection, template_path: Path, output_path: Path) -> Path:
    has_starred = has_column(conn, "lecons", "starred")
    select_starred = "starred" if has_starred else "0 AS starred"
    lecons = conn.execute(
        f"""
        SELECT id, name, status, {select_starred}
        FROM lecons
        ORDER BY starred DESC, id
        """
    ).fetchall()

    starred_lecons = [row for row in lecons if int(row["starred"]) == 1]
    regular_lecons = [row for row in lecons if int(row["starred"]) == 0]

    assoc_rows = conn.execute(
        """
        SELECT
            l.id AS lecon_id,
            d.id AS dev_id,
            d.name AS dev_name,
            CASE WHEN ld.dev_id IS NULL THEN 0 ELSE 1 END AS selected
        FROM lecons l
        LEFT JOIN dev_lecons dl ON dl.lecon_id = l.id
        LEFT JOIN devs d ON d.id = dl.dev_id
        LEFT JOIN lecon_devs ld
            ON ld.lecon_id = l.id
           AND ld.dev_id = d.id
        WHERE d.id IS NOT NULL
        ORDER BY l.id, d.id
        """
    ).fetchall()
    assoc_by_lecon: dict[int, list[tuple[str, bool]]] = {}
    for row in assoc_rows:
        lecon_id = int(row["lecon_id"])
        assoc_by_lecon.setdefault(lecon_id, []).append(
            (f"{int(row['dev_id'])}: {str(row['dev_name'])}", int(row["selected"]) == 1)
        )

    starred_rows = build_detail_rows(
        starred_lecons,
        "lecons",
        assoc_by_item=assoc_by_lecon,
        assoc_selected_label="sélectionné",
        assoc_unselected_label="non sélectionné",
    )
    rows = build_detail_rows(
        regular_lecons,
        "lecons",
        assoc_by_item=assoc_by_lecon,
        assoc_selected_label="sélectionné",
        assoc_unselected_label="non sélectionné",
    )

    data = {
        "PAGE_TITLE": "Leçons",
        "HEADER_1": "Numéro",
        "HEADER_2": "Titre",
        "HEADER_3": "Statut",
        "STARRED_ROWS": starred_rows,
        "TABLE_ROWS": rows,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    template = template_path.read_text(encoding="utf-8")
    output_path.write_text(render_template(template, data), encoding="utf-8")
    return output_path


def generate_devs_page(conn: sqlite3.Connection, template_path: Path, output_path: Path) -> Path:
    has_starred = has_column(conn, "devs", "starred")
    select_starred = "starred" if has_starred else "0 AS starred"
    devs = conn.execute(
        f"""
        SELECT id, name, status, {select_starred}
        FROM devs
        ORDER BY starred DESC, id
        """
    ).fetchall()

    starred_devs = [row for row in devs if int(row["starred"]) == 1]
    regular_devs = [row for row in devs if int(row["starred"]) == 0]

    assoc_rows = conn.execute(
        """
        SELECT
            d.id AS dev_id,
            l.id AS lecon_id,
            l.name AS lecon_name,
            CASE WHEN ld.dev_id IS NULL THEN 0 ELSE 1 END AS selected
        FROM devs d
        LEFT JOIN dev_lecons dl ON dl.dev_id = d.id
        LEFT JOIN lecons l ON l.id = dl.lecon_id
        LEFT JOIN lecon_devs ld
            ON ld.lecon_id = l.id
           AND ld.dev_id = d.id
        WHERE l.id IS NOT NULL
        ORDER BY d.id, l.id
        """
    ).fetchall()
    assoc_by_dev: dict[int, list[tuple[str, bool]]] = {}
    for row in assoc_rows:
        dev_id = int(row["dev_id"])
        assoc_by_dev.setdefault(dev_id, []).append(
            (f"{int(row['lecon_id'])}", int(row["selected"]) == 1)
        )

    starred_rows = build_detail_rows(
        starred_devs,
        "dev",
        assoc_by_item=assoc_by_dev,
        assoc_selected_label="sélectionnée",
        assoc_unselected_label="non sélectionnée",
    )
    rows = build_detail_rows(
        regular_devs,
        "dev",
        assoc_by_item=assoc_by_dev,
        assoc_selected_label="sélectionnée",
        assoc_unselected_label="non sélectionnée",
    )

    data = {
        "PAGE_TITLE": "Développements",
        "HEADER_1": "ID",
        "HEADER_2": "Titre",
        "HEADER_3": "Statut",
        "STARRED_ROWS": starred_rows,
        "TABLE_ROWS": rows,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    template = template_path.read_text(encoding="utf-8")
    output_path.write_text(render_template(template, data), encoding="utf-8")
    return output_path


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
    generate_lecons_page(conn, Path("lecons/template.html"), Path("lecons/index.html"))
    generate_devs_page(conn, Path("dev/template.html"), Path("dev/index.html"))

    return output_path
