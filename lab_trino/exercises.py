"""Lab 10.3 exercises. Usage: uv run python lab_trino/exercises.py <ex1|ex2|ex4|ex3>"""
from common import run, show, sql, title


def explain_input(query):
    plan = sql("EXPLAIN ANALYZE " + query).iloc[0, 0]
    keep = [l.strip() for l in plan.splitlines()
            if "Input:" in l and ("Physical input" in l or "Splits" in l)]
    print("\n".join(keep) or plan)


def ex1():
    title("EXERCISE 1 - PARTITIONED TABLE")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.orders_by_state_month_part
        WITH (partitioning = ARRAY['month(month)']) AS
        SELECT * FROM lakehouse.gold.orders_by_state_month""")
    for table in ["orders_by_state_month", "orders_by_state_month_part"]:
        show(f'"{table}$files"', f"""
            SELECT regexp_extract(file_path, '[^/]+/[^/]+$') AS file, record_count, file_size_in_bytes
            FROM lakehouse.gold."{table}$files" ORDER BY file""")
    query = "SELECT sum(units) AS units FROM lakehouse.gold.{t} WHERE month = TIMESTAMP '2020-02-01 00:00:00 UTC'"
    for table in ["orders_by_state_month", "orders_by_state_month_part"]:
        show(f"February units in {table}", query.format(t=table))
        print(f"--- EXPLAIN ANALYZE on {table}:")
        explain_input(query.format(t=table))


def ex2():
    title("EXERCISE 2 - COHORTS BY DECADE OF BIRTH")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.cohorts AS
        SELECT (year(u.birthdate) / 10) * 10           AS birth_decade,
               count(DISTINCT u.user_id)               AS users,
               count(o.order_id)                       AS orders,
               round(avg(CAST(o.quantity AS double)), 2) AS avg_units_per_order
        FROM lakehouse.silver.users AS u
        LEFT JOIN lakehouse.silver.orders AS o ON o.user_id = u.user_id
        GROUP BY 1""")
    show("gold.cohorts", "SELECT * FROM lakehouse.gold.cohorts ORDER BY birth_decade")
    show("check", "SELECT sum(users) AS users, sum(orders) AS orders FROM lakehouse.gold.cohorts")


def ex4():
    title("EXERCISE 4 - OPTIMIZE")
    snaps = 'SELECT snapshot_id, committed_at, operation FROM lakehouse.gold."top_products$snapshots" ORDER BY committed_at'
    files = """SELECT regexp_extract(file_path, '[^/]+$') AS file, record_count, file_size_in_bytes
               FROM lakehouse.gold."top_products$files" """
    show("snapshots BEFORE", snaps)
    show("files BEFORE", files)
    sql("ALTER TABLE lakehouse.gold.top_products EXECUTE optimize")
    show("snapshots AFTER", snaps)
    show("files AFTER", files)


def ex3():
    title("EXERCISE 3 - INSERT + MERGE + TIME TRAVEL")
    marker = "TIMESTAMP '2020-05-01 10:00:00 UTC'"
    if sql(f"SELECT count(*) FROM lakehouse.silver.orders WHERE ordered_at = {marker}").iloc[0, 0] == 0:
        sql(f"""
            INSERT INTO lakehouse.silver.orders
            SELECT CAST(uuid() AS varchar), user_id, {marker}, 2, 'cookie'
            FROM lakehouse.silver.users ORDER BY user_id LIMIT 1""")
    show("new silver order", f"""
        SELECT o.*, u.state FROM lakehouse.silver.orders o
        JOIN lakehouse.silver.users u ON u.user_id = o.user_id WHERE ordered_at = {marker}""")
    before = sql("""SELECT snapshot_id FROM lakehouse.gold."orders_by_state_month$snapshots"
                    ORDER BY committed_at DESC LIMIT 1""").iloc[0, 0]
    sql("""
        MERGE INTO lakehouse.gold.orders_by_state_month AS t
        USING (
            SELECT u.state, date_trunc('month', o.ordered_at) AS month,
                   count(*) AS orders, sum(o.quantity) AS units, count(DISTINCT o.user_id) AS buyers
            FROM lakehouse.silver.orders AS o
            JOIN lakehouse.silver.users  AS u ON u.user_id = o.user_id
            GROUP BY 1, 2) AS s
        ON t.state = s.state AND t.month = s.month
        WHEN MATCHED AND (t.orders <> s.orders OR t.units <> s.units OR t.buyers <> s.buyers)
            THEN UPDATE SET orders = s.orders, units = s.units, buyers = s.buyers
        WHEN NOT MATCHED
            THEN INSERT (state, month, orders, units, buyers) VALUES (s.state, s.month, s.orders, s.units, s.buyers)""")
    show("gold snapshots", """SELECT snapshot_id, committed_at, operation
        FROM lakehouse.gold."orders_by_state_month$snapshots" ORDER BY committed_at""")
    show(f"BEFORE the merge (FOR VERSION AS OF {before})", f"""
        SELECT count(*) AS rows, sum(orders) AS orders, sum(units) AS units
        FROM lakehouse.gold.orders_by_state_month FOR VERSION AS OF {before}""")
    show("AFTER the merge", """
        SELECT count(*) AS rows, sum(orders) AS orders, sum(units) AS units
        FROM lakehouse.gold.orders_by_state_month""")
    show("new row (May 2020)", """
        SELECT * FROM lakehouse.gold.orders_by_state_month
        WHERE month = TIMESTAMP '2020-05-01 00:00:00 UTC'""")


run({"ex1": ex1, "ex2": ex2, "ex4": ex4, "ex3": ex3})
