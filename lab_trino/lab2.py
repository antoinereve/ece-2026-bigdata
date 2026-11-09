"""Lab 10.2 - Silver to gold with Trino. Usage: uv run python lab_trino/lab2.py <section>"""
from common import run, show, sql, title


def connect():
    title("1. CONNECTION")
    show('SELECT version()', "SELECT version() AS version")
    show("SELECT current_catalog, current_schema",
         "SELECT current_catalog AS catalog, current_schema AS schema")


def catalogs():
    title("2. CATALOGS, SCHEMAS AND TABLES")
    show("SHOW CATALOGS", "SHOW CATALOGS")
    show("SHOW SCHEMAS FROM lakehouse", "SHOW SCHEMAS FROM lakehouse")
    show("SHOW TABLES FROM lakehouse.silver", "SHOW TABLES FROM lakehouse.silver")
    show("DESCRIBE lakehouse.silver.orders", "DESCRIBE lakehouse.silver.orders")
    show("DESCRIBE lakehouse.silver.users", "DESCRIBE lakehouse.silver.users")


def silver():
    title("3. QUERY THE SILVER LAYER")
    show("orders", "SELECT count(*) AS orders FROM lakehouse.silver.orders")
    show("users", "SELECT count(*) AS users FROM lakehouse.silver.users")
    show("users per state", """
        SELECT state, count(*) AS users, count_if(city IS NULL) AS missing_city
        FROM lakehouse.silver.users GROUP BY state ORDER BY users DESC LIMIT 10""")
    show("orphan orders", """
        SELECT count(*) AS orphan_orders
        FROM lakehouse.silver.orders AS o
        LEFT JOIN lakehouse.silver.users AS u ON u.user_id = o.user_id
        WHERE u.user_id IS NULL""")


def metadata():
    title("4. ICEBERG METADATA")
    show('"orders$snapshots"', """
        SELECT snapshot_id, committed_at, operation
        FROM lakehouse.silver."orders$snapshots" ORDER BY committed_at""")
    show('"orders$files"', """
        SELECT file_path, file_format, record_count, file_size_in_bytes
        FROM lakehouse.silver."orders$files" """)
    show('"orders$history"', 'SELECT * FROM lakehouse.silver."orders$history"')


def plan():
    title("5a. EXPLAIN (TYPE DISTRIBUTED)")
    query = """
        SELECT u.state, count(*) AS orders
        FROM lakehouse.silver.orders AS o
        JOIN lakehouse.silver.users  AS u ON u.user_id = o.user_id
        GROUP BY u.state"""
    print(sql("EXPLAIN (TYPE DISTRIBUTED)" + query).iloc[0, 0])
    title("5b. EXPLAIN ANALYZE")
    print(sql("EXPLAIN ANALYZE" + query).iloc[0, 0])
    title("5c. QUERY HISTORY")
    try:
        show("system.runtime.queries", """
            SELECT query_id, state,
                   date_diff('millisecond', created, coalesce("end", current_timestamp)) AS elapsed_ms,
                   substr(query, 1, 60) AS query
            FROM system.runtime.queries ORDER BY created DESC LIMIT 5""")
    except Exception as error:
        print("system.runtime.queries denied:", error)


def gold():
    title("6. GOLD LAYER")
    sql("CREATE SCHEMA IF NOT EXISTS lakehouse.gold")
    show("SHOW SCHEMAS FROM lakehouse", "SHOW SCHEMAS FROM lakehouse")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.orders_by_state_month AS
        SELECT u.state, date_trunc('month', o.ordered_at) AS month,
               count(*) AS orders, sum(o.quantity) AS units, count(DISTINCT o.user_id) AS buyers
        FROM lakehouse.silver.orders AS o
        JOIN lakehouse.silver.users  AS u ON u.user_id = o.user_id
        GROUP BY 1, 2""")
    show("gold.orders_by_state_month",
         "SELECT * FROM lakehouse.gold.orders_by_state_month ORDER BY month, state LIMIT 10")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.top_products AS
        SELECT product, count(*) AS orders, sum(quantity) AS units,
               rank() OVER (ORDER BY sum(quantity) DESC) AS units_rank
        FROM lakehouse.silver.orders GROUP BY product""")
    show("gold.top_products", "SELECT * FROM lakehouse.gold.top_products ORDER BY units_rank LIMIT 10")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.user_activity AS
        SELECT u.user_id, u.state, date_diff('year', u.birthdate, current_date) AS age,
               count(o.order_id) AS orders, coalesce(sum(o.quantity), 0) AS units,
               min(o.ordered_at) AS first_order_at, max(o.ordered_at) AS last_order_at
        FROM lakehouse.silver.users AS u
        LEFT JOIN lakehouse.silver.orders AS o ON o.user_id = u.user_id
        GROUP BY u.user_id, u.state, u.birthdate""")
    show("gold.user_activity", "SELECT * FROM lakehouse.gold.user_activity ORDER BY orders DESC LIMIT 10")
    show("SHOW TABLES FROM lakehouse.gold", "SHOW TABLES FROM lakehouse.gold")
    show('"top_products$files"', """
        SELECT file_path, record_count, file_size_in_bytes
        FROM lakehouse.gold."top_products$files" """)


def validation():
    title("7. VALIDATION")
    v = lambda q: sql(q).iloc[0, 0]
    silver_units = v("SELECT sum(quantity) FROM lakehouse.silver.orders")
    gold_units = v("SELECT sum(units) FROM lakehouse.gold.orders_by_state_month")
    product_units = v("SELECT sum(units) FROM lakehouse.gold.top_products")
    silver_users = v("SELECT count(*) FROM lakehouse.silver.users")
    gold_users = v("SELECT count(*) FROM lakehouse.gold.user_activity")
    silver_orders = v("SELECT count(*) FROM lakehouse.silver.orders")
    gold_orders = v("SELECT sum(orders) FROM lakehouse.gold.user_activity")
    print(f"units : silver={silver_units} | orders_by_state_month={gold_units} | top_products={product_units}")
    print(f"users : silver={silver_users} | user_activity={gold_users}")
    print(f"orders: silver={silver_orders} | user_activity={gold_orders}")
    assert silver_units == gold_units
    assert silver_units == product_units
    assert silver_users == gold_users
    assert silver_orders == gold_orders
    print("ALL ASSERTIONS PASSED")


def refresh():
    title("8. REFRESH A GOLD TABLE")
    sql("DELETE FROM lakehouse.gold.top_products")
    sql("""
        INSERT INTO lakehouse.gold.top_products
        SELECT product, count(*), sum(quantity), rank() OVER (ORDER BY sum(quantity) DESC)
        FROM lakehouse.silver.orders GROUP BY product""")
    show('"top_products$snapshots"', """
        SELECT snapshot_id, committed_at, operation
        FROM lakehouse.gold."top_products$snapshots" ORDER BY committed_at""")
    first = sql("""SELECT snapshot_id FROM lakehouse.gold."top_products$snapshots"
                   ORDER BY committed_at LIMIT 1""").iloc[0, 0]
    show(f"FOR VERSION AS OF {first} (after creation)",
         f"SELECT count(*) AS products FROM lakehouse.gold.top_products FOR VERSION AS OF {first}")
    show("current version", "SELECT count(*) AS products FROM lakehouse.gold.top_products")


run({"connect": connect, "catalogs": catalogs, "silver": silver, "metadata": metadata,
     "plan": plan, "gold": gold, "validation": validation, "refresh": refresh})
