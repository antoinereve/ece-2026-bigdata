"""Lab 10.3 exercise 5 - orders_by_state_month computed by Spark through Polaris, compared with Trino's table."""
import os

from pyspark.sql import SparkSession

spark = (
    SparkSession.builder.appName("lab-trino-ex5").master("local[*]")
    .config("spark.hadoop.fs.s3a.endpoint", f"https://{os.environ['AWS_S3_ENDPOINT']}")
    .config("spark.hadoop.fs.s3a.access.key", os.environ["AWS_ACCESS_KEY_ID"])
    .config("spark.hadoop.fs.s3a.secret.key", os.environ["AWS_SECRET_ACCESS_KEY"])
    .config("spark.hadoop.fs.s3a.session.token", os.environ.get("AWS_SESSION_TOKEN", ""))
    .config("spark.hadoop.fs.s3a.endpoint.region", "us-east-1")
    .config("spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.TemporaryAWSCredentialsProvider")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    .config("spark.sql.catalog.polaris", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.polaris.type", "rest")
    .config("spark.sql.catalog.polaris.uri", f"{os.environ['POLARIS_URI']}/api/catalog")
    .config("spark.sql.catalog.polaris.warehouse", os.environ["POLARIS_CATALOG"])
    .config("spark.sql.catalog.polaris.credential", os.environ["POLARIS_DEV_CREDENTIAL"])
    .config("spark.sql.catalog.polaris.scope", "PRINCIPAL_ROLE:ALL")
    .config("spark.sql.catalog.polaris.io-impl", "org.apache.iceberg.hadoop.HadoopFileIO")
    .config("spark.sql.session.timeZone", "UTC")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")

print("\n===== EXERCISE 5 - SPARK vs TRINO =====")
spark_agg = spark.sql("""
    SELECT u.state, date_trunc('month', o.ordered_at) AS month,
           count(*) AS orders, sum(o.quantity) AS units, count(DISTINCT o.user_id) AS buyers
    FROM polaris.silver.orders AS o
    JOIN polaris.silver.users  AS u ON u.user_id = o.user_id
    GROUP BY 1, 2
""")
trino_gold = spark.table("polaris.gold.orders_by_state_month")

print(">>> computed by Spark from polaris.silver")
spark_agg.orderBy("month", "state").show(5, truncate=False)
print(">>> polaris.gold.orders_by_state_month (written by Trino)")
trino_gold.orderBy("month", "state").show(5, truncate=False)

s = spark_agg.selectExpr("count(*) AS rows", "sum(orders) AS orders", "sum(units) AS units").first()
t = trino_gold.selectExpr("count(*) AS rows", "sum(orders) AS orders", "sum(units) AS units").first()
print(f"Spark : rows={s.rows} | orders={s.orders} | units={s.units}")
print(f"Trino : rows={t.rows} | orders={t.orders} | units={t.units}")
diff = (spark_agg.selectExpr("state", "CAST(month AS timestamp) AS month", "orders", "units", "buyers")
        .exceptAll(trino_gold.selectExpr("state", "CAST(month AS timestamp) AS month", "orders", "units", "buyers"))
        .count())
print(f"Rows computed by Spark that differ from Trino's table: {diff}")
spark.stop()
