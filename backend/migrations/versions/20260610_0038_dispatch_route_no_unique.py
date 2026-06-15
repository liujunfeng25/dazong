"""make dispatch route numbers unique

Revision ID: 20260610_0038
Revises: 20260608_0037
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260610_0038"
down_revision = "20260608_0037"
branch_labels = None
depends_on = None


UNIQUE_NAME = "uq_dispatch_trip_route_no"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "delivery_dispatch_trips" not in set(inspector.get_table_names()):
        return

    rows = conn.execute(
        sa.text(
            "SELECT id, delivery_id, planning_date, route_no "
            "FROM delivery_dispatch_trips "
            "ORDER BY delivery_id, planning_date, id"
        )
    ).mappings()
    used: dict[tuple[int, object], set[str]] = {}
    for row in rows:
        key = (int(row["delivery_id"]), row["planning_date"])
        route_no = str(row["route_no"] or "")
        group = used.setdefault(key, set())
        if route_no not in group:
            group.add(route_no)
            continue
        suffix = f"-D{int(row['id'])}"
        candidate = f"{route_no[: max(1, 64 - len(suffix))]}{suffix}"
        while candidate in group:
            candidate = f"{candidate[:62]}-X"
        conn.execute(
            sa.text("UPDATE delivery_dispatch_trips SET route_no = :route_no WHERE id = :id"),
            {"route_no": candidate, "id": int(row["id"])},
        )
        group.add(candidate)

    inspector = sa.inspect(conn)
    unique_names = {c.get("name") for c in inspector.get_unique_constraints("delivery_dispatch_trips")}
    unique_index_names = {
        i.get("name")
        for i in inspector.get_indexes("delivery_dispatch_trips")
        if i.get("unique")
    }
    if UNIQUE_NAME not in unique_names | unique_index_names:
        op.create_unique_constraint(
            UNIQUE_NAME,
            "delivery_dispatch_trips",
            ["delivery_id", "planning_date", "route_no"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "delivery_dispatch_trips" not in set(inspector.get_table_names()):
        return
    unique_names = {c.get("name") for c in inspector.get_unique_constraints("delivery_dispatch_trips")}
    if UNIQUE_NAME in unique_names:
        op.drop_constraint(UNIQUE_NAME, "delivery_dispatch_trips", type_="unique")
