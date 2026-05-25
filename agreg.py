#!/usr/bin/env python3

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from dashboard import generate_dashboard


DEFAULT_DB = Path("agreg.db")


STATUS_NAMES = {
    1: "empty",
    2: "researching",
    3: "writing",
    4: "written-needs-work",
    5: "done",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lecons (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            status INTEGER NOT NULL DEFAULT 1 CHECK (status BETWEEN 1 AND 5),
            last_revisited TEXT
        );

        CREATE TABLE IF NOT EXISTS devs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status INTEGER NOT NULL DEFAULT 1 CHECK (status BETWEEN 1 AND 5),
            last_revisited TEXT
        );

        -- dev.lecon field:
        -- the leçons to which a given dev is associated.
        CREATE TABLE IF NOT EXISTS dev_lecons (
            dev_id INTEGER NOT NULL,
            lecon_id INTEGER NOT NULL,
            PRIMARY KEY (dev_id, lecon_id),
            FOREIGN KEY (dev_id) REFERENCES devs(id) ON DELETE CASCADE,
            FOREIGN KEY (lecon_id) REFERENCES lecons(id) ON DELETE CASCADE
        );

        -- lecon.dev field:
        -- the devs explicitly attached to a leçon.
        --
        -- The composite foreign key enforces:
        -- if (lecon_id, dev_id) is here, then (dev_id, lecon_id)
        -- must already exist in dev_lecons.
        CREATE TABLE IF NOT EXISTS lecon_devs (
            lecon_id INTEGER NOT NULL,
            dev_id INTEGER NOT NULL,
            PRIMARY KEY (lecon_id, dev_id),
            FOREIGN KEY (lecon_id) REFERENCES lecons(id) ON DELETE CASCADE,
            FOREIGN KEY (dev_id, lecon_id)
                REFERENCES dev_lecons(dev_id, lecon_id)
                ON DELETE CASCADE
        );
        """
    )
    conn.commit()


def validate_status(status: int) -> None:
    if status not in STATUS_NAMES:
        raise SystemExit("Status must be an integer between 1 and 5.")


def table_for_kind(kind: str) -> tuple[str, str]:
    if kind in {"lecon", "leçon"}:
        return "lecons", "id"
    if kind in {"dev", "plan"}:
        return "devs", "id"
    raise SystemExit("Kind must be 'lecon' or 'dev'.")


def add_lecon(conn: sqlite3.Connection, number: int, name: str, status: int) -> None:
    validate_status(status)
    conn.execute(
        """
        INSERT INTO lecons(id, name, status)
        VALUES (?, ?, ?)
        """,
        (number, name, status),
    )
    conn.commit()
    print(f"Added leçon {number}: {name}")


def add_dev(conn: sqlite3.Connection, name: str, status: int) -> None:
    validate_status(status)
    cur = conn.execute(
        """
        INSERT INTO devs(name, status)
        VALUES (?, ?)
        """,
        (name, status),
    )
    conn.commit()
    print(f"Added dev {cur.lastrowid}: {name}")


def set_status(conn: sqlite3.Connection, kind: str, item_id: int, status: int) -> None:
    validate_status(status)
    table, id_col = table_for_kind(kind)

    cur = conn.execute(
        f"""
        UPDATE {table}
        SET status = ?
        WHERE {id_col} = ?
        """,
        (status, item_id),
    )
    conn.commit()

    if cur.rowcount == 0:
        raise SystemExit(f"No such {kind}: {item_id}")

    print(f"Set {kind} {item_id} to status {status} ({STATUS_NAMES[status]}).")


def revisit(conn: sqlite3.Connection, kind: str, item_id: int) -> None:
    table, id_col = table_for_kind(kind)
    timestamp = now()

    cur = conn.execute(
        f"""
        UPDATE {table}
        SET last_revisited = ?
        WHERE {id_col} = ?
        """,
        (timestamp, item_id),
    )
    conn.commit()

    if cur.rowcount == 0:
        raise SystemExit(f"No such {kind}: {item_id}")

    print(f"Revisited {kind} {item_id} at {timestamp}.")


def toggle_star(conn: sqlite3.Connection, kind: str, item_id: int) -> None:
    table, id_col = table_for_kind(kind)
    row = conn.execute(
        f"""
        SELECT starred
        FROM {table}
        WHERE {id_col} = ?
        """,
        (item_id,),
    ).fetchone()

    if row is None:
        raise SystemExit(f"No such {kind}: {item_id}")

    starred = 0 if row["starred"] else 1

    conn.execute(
        f"""
        UPDATE {table}
        SET starred = ?
        WHERE {id_col} = ?
        """,
        (starred, item_id),
    )
    conn.commit()

    state = "starred" if starred else "unstarred"
    print(f"{kind} {item_id} is now {state}.")


def associate_dev_to_lecon(
    conn: sqlite3.Connection,
    dev_id: int,
    lecon_id: int,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO dev_lecons(dev_id, lecon_id)
        VALUES (?, ?)
        """,
        (dev_id, lecon_id),
    )
    conn.commit()
    print(f"Associated dev {dev_id} to leçon {lecon_id}.")


def select_dev_for_lecon(
    conn: sqlite3.Connection,
    lecon_id: int,
    dev_id: int,
) -> None:
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO lecon_devs(lecon_id, dev_id)
            VALUES (?, ?)
            """,
            (lecon_id, dev_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise SystemExit(
            f"Cannot select dev {dev_id} for leçon {lecon_id}: "
            f"first run `associate {dev_id} {lecon_id}`."
        )

    print(f"Selected dev {dev_id} for leçon {lecon_id}.")


def show_lecon(conn: sqlite3.Connection, lecon_id: int) -> None:
    lecon = conn.execute(
        """
        SELECT *
        FROM lecons
        WHERE id = ?
        """,
        (lecon_id,),
    ).fetchone()

    if lecon is None:
        raise SystemExit(f"No such leçon: {lecon_id}")

    devs = conn.execute(
        """
        SELECT d.id, d.name, d.status, d.last_revisited
        FROM devs d
        JOIN lecon_devs ld ON ld.dev_id = d.id
        WHERE ld.lecon_id = ?
        ORDER BY d.id
        """,
        (lecon_id,),
    ).fetchall()

    print(f"{lecon['id']} — {lecon['name']}")
    print(f"status: {lecon['status']} ({STATUS_NAMES[lecon['status']]})")
    print(f"last revisited: {lecon['last_revisited']}")
    print("selected devs:")

    for dev in devs:
        print(
            f"  {dev['id']} — {dev['name']} "
            f"[{dev['status']}: {STATUS_NAMES[dev['status']]}]"
        )


def show_dev(conn: sqlite3.Connection, dev_id: int) -> None:
    dev = conn.execute(
        """
        SELECT *
        FROM devs
        WHERE id = ?
        """,
        (dev_id,),
    ).fetchone()

    if dev is None:
        raise SystemExit(f"No such dev: {dev_id}")

    lecons = conn.execute(
        """
        SELECT l.id, l.name, l.status, l.last_revisited
        FROM lecons l
        JOIN dev_lecons dl ON dl.lecon_id = l.id
        WHERE dl.dev_id = ?
        ORDER BY l.id
        """,
        (dev_id,),
    ).fetchall()

    print(f"{dev['id']} — {dev['name']}")
    print(f"status: {dev['status']} ({STATUS_NAMES[dev['status']]})")
    print(f"last revisited: {dev['last_revisited']}")
    print("associated leçons:")

    for lecon in lecons:
        print(
            f"  {lecon['id']} — {lecon['name']} "
            f"[{lecon['status']}: {STATUS_NAMES[lecon['status']]}]"
        )


def main() -> None:
    parser = argparse.ArgumentParser(prog="agreg")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to SQLite database.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    p = sub.add_parser("add-lecon")
    p.add_argument("number", type=int)
    p.add_argument("name")
    p.add_argument("--status", type=int, default=1)

    p = sub.add_parser("add-dev")
    p.add_argument("name")
    p.add_argument("--status", type=int, default=1)

    p = sub.add_parser("status")
    p.add_argument("kind", choices=["lecon", "leçon", "dev", "plan"])
    p.add_argument("id", type=int)
    p.add_argument("status", type=int)

    p = sub.add_parser("revisit")
    p.add_argument("kind", choices=["lecon", "leçon", "dev", "plan"])
    p.add_argument("id", type=int)

    p = sub.add_parser("star")
    p.add_argument("kind", choices=["lecon", "leçon", "dev", "plan"])
    p.add_argument("id", type=int)

    p = sub.add_parser("associate")
    p.add_argument("dev_id", type=int)
    p.add_argument("lecon_id", type=int)

    p = sub.add_parser("select")
    p.add_argument("lecon_id", type=int)
    p.add_argument("dev_id", type=int)

    p = sub.add_parser("show-lecon")
    p.add_argument("lecon_id", type=int)

    p = sub.add_parser("show-dev")
    p.add_argument("dev_id", type=int)

    p = sub.add_parser("dashboard")
    p.add_argument("--template", type=Path, default=Path("template.html"))
    p.add_argument("--output", type=Path, default=Path("index.html"))

    args = parser.parse_args()

    conn = connect(args.db)

    match args.command:
        case "init":
            init_db(conn)
            print(f"Initialized database at {args.db}")

        case "add-lecon":
            add_lecon(conn, args.number, args.name, args.status)

        case "add-dev":
            add_dev(conn, args.name, args.status)

        case "status":
            set_status(conn, args.kind, args.id, args.status)

        case "revisit":
            revisit(conn, args.kind, args.id)

        case "star":
            toggle_star(conn, args.kind, args.id)

        case "associate":
            associate_dev_to_lecon(conn, args.dev_id, args.lecon_id)

        case "select":
            select_dev_for_lecon(conn, args.lecon_id, args.dev_id)

        case "show-lecon":
            show_lecon(conn, args.lecon_id)

        case "show-dev":
            show_dev(conn, args.dev_id)
        
        case "dashboard":
            output = generate_dashboard(db_path=args.db,template_path=args.template, output_path=args.output)
            print(f"Generated {output}")

if __name__ == "__main__":
    main()
