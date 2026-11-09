"""Lab 10.3 - Star schema with Trino. Usage: uv run python lab_trino/lab3.py <section>"""
from common import run, show, sql, title


def star():
    title("1. DIMENSIONS AND FACT TABLE")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.dim_user AS
        SELECT row_number() OVER (ORDER BY user_id) AS user_key,
               user_id, username, name, sex, birthdate, city, state, zip_code
        FROM lakehouse.silver.users""")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.dim_product AS
        SELECT row_number() OVER (ORDER BY product) AS product_key, product
        FROM (SELECT DISTINCT product FROM lakehouse.silver.orders)""")
    first_day, last_day = sql("""
        SELECT CAST(min(ordered_at) AS date), CAST(max(ordered_at) AS date)
        FROM lakehouse.silver.orders""").iloc[0]
    print(f"dim_date from {first_day} to {last_day}")
    sql(f"""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.dim_date AS
        SELECT
            CAST(date_format(CAST(d AS timestamp), '%Y%m%d') AS integer) AS date_key,
            d AS full_date, year(d) AS year, quarter(d) AS quarter, month(d) AS month,
            date_format(CAST(d AS timestamp), '%M') AS month_name,
            day_of_week(d) AS day_of_week, day_of_week(d) IN (6, 7) AS is_weekend
        FROM UNNEST(sequence(DATE '{first_day}', DATE '{last_day}', INTERVAL '1' DAY)) AS t(d)""")
    sql("""
        CREATE TABLE IF NOT EXISTS lakehouse.gold.fact_orders AS
        SELECT o.order_id, u.user_key, p.product_key,
               CAST(date_format(o.ordered_at, '%Y%m%d') AS integer) AS date_key,
               o.ordered_at, o.quantity
        FROM lakehouse.silver.orders AS o
        LEFT JOIN lakehouse.gold.dim_user    AS u ON u.user_id = o.user_id
        LEFT JOIN lakehouse.gold.dim_product AS p ON p.product = o.product""")
    show("row counts", """
        SELECT 'dim_user' AS table_name, count(*) AS row_count FROM lakehouse.gold.dim_user
        UNION ALL SELECT 'dim_product', count(*) FROM lakehouse.gold.dim_product
        UNION ALL SELECT 'dim_date', count(*) FROM lakehouse.gold.dim_date
        UNION ALL SELECT 'fact_orders', count(*) FROM lakehouse.gold.fact_orders""")
    show("dim_product", "SELECT * FROM lakehouse.gold.dim_product ORDER BY product_key")
    show("dim_date (first rows)", "SELECT * FROM lakehouse.gold.dim_date ORDER BY date_key LIMIT 5")
    show("fact_orders (first rows)", "SELECT * FROM lakehouse.gold.fact_orders ORDER BY ordered_at LIMIT 5")


def query():
    title("2. QUERY THE STAR")
    show("year x state x product (top 10)", """
        SELECT d.year, u.state, p.product, count(*) AS orders, sum(f.quantity) AS units
        FROM lakehouse.gold.fact_orders AS f
        JOIN lakehouse.gold.dim_date    AS d ON d.date_key    = f.date_key
        JOIN lakehouse.gold.dim_user    AS u ON u.user_key    = f.user_key
        JOIN lakehouse.gold.dim_product AS p ON p.product_key = f.product_key
        GROUP BY d.year, u.state, p.product ORDER BY units DESC LIMIT 10""")
    show("orders_by_state_month rebuilt from the star", """
        SELECT u.state, d.year, d.month, count(*) AS orders, sum(f.quantity) AS units,
               count(DISTINCT f.user_key) AS buyers
        FROM lakehouse.gold.fact_orders AS f
        JOIN lakehouse.gold.dim_date AS d ON d.date_key = f.date_key
        JOIN lakehouse.gold.dim_user AS u ON u.user_key = f.user_key
        GROUP BY u.state, d.year, d.month ORDER BY d.year, d.month, u.state LIMIT 10""")
    show("gold.orders_by_state_month (for comparison)", """
        SELECT state, year(month) AS year, month(month) AS month, orders, units, buyers
        FROM lakehouse.gold.orders_by_state_month ORDER BY month, state LIMIT 10""")
    show("full comparison: rows that differ (expected: none)", """
        WITH star AS (
            SELECT u.state, d.year, d.month, count(*) AS orders, sum(f.quantity) AS units
            FROM lakehouse.gold.fact_orders f
            JOIN lakehouse.gold.dim_date d ON d.date_key = f.date_key
            JOIN lakehouse.gold.dim_user u ON u.user_key = f.user_key
            GROUP BY 1, 2, 3),
        agg AS (
            SELECT state, year(month) AS year, month(month) AS month, orders, units
            FROM lakehouse.gold.orders_by_state_month)
        SELECT count(*) AS differing_rows FROM (
            (SELECT * FROM star EXCEPT SELECT * FROM agg)
            UNION ALL
            (SELECT * FROM agg EXCEPT SELECT * FROM star))""")


def validation():
    title("3. VALIDATION")
    v = lambda q: sql(q).iloc[0, 0]
    silver_orders = v("SELECT count(*) FROM lakehouse.silver.orders")
    fact_orders = v("SELECT count(*) FROM lakehouse.gold.fact_orders")
    silver_units = v("SELECT sum(quantity) FROM lakehouse.silver.orders")
    fact_units = v("SELECT sum(quantity) FROM lakehouse.gold.fact_orders")
    unmatched = v("""
        SELECT count(*) FROM lakehouse.gold.fact_orders AS f
        LEFT JOIN lakehouse.gold.dim_user    AS u ON u.user_key    = f.user_key
        LEFT JOIN lakehouse.gold.dim_product AS p ON p.product_key = f.product_key
        LEFT JOIN lakehouse.gold.dim_date    AS d ON d.date_key    = f.date_key
        WHERE u.user_key IS NULL OR p.product_key IS NULL OR d.date_key IS NULL""")
    print(f"orders: silver={silver_orders} | fact={fact_orders}")
    print(f"units : silver={silver_units} | fact={fact_units}")
    print(f"orders without a complete dimension row: {unmatched}")
    assert silver_orders == fact_orders, f"{silver_orders} != {fact_orders}"
    assert silver_units == fact_units, f"{silver_units} != {fact_units}"
    assert unmatched == 0, f"{unmatched} orders without a complete dimension row"
    print("ALL ASSERTIONS PASSED")


run({"star": star, "query": query, "validation": validation})
