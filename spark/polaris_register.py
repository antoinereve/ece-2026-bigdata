"""Lab 09-2 - Register the silver Iceberg tables of the Spark lab in the Polaris catalog."""
import os

from pyspark.sql import SparkSession

BUCKET = os.environ["LAB_BUCKET_NAME"]
PRINCIPAL = os.environ.get("POLARIS_PRINCIPAL", "dev")
CREDENTIAL = os.environ[f"POLARIS_{PRINCIPAL.upper()}_CREDENTIAL"]

spark = (
    SparkSession.builder
    .appName("lab-polaris")
    .master("local[*]")
    .config("spark.hadoop.fs.s3a.endpoint", f"https://{os.environ['AWS_S3_ENDPOINT']}")
    .config("spark.hadoop.fs.s3a.access.key", os.environ["AWS_ACCESS_KEY_ID"])
    .config("spark.hadoop.fs.s3a.secret.key", os.environ["AWS_SECRET_ACCESS_KEY"])
    .config("spark.hadoop.fs.s3a.session.token", os.environ.get("AWS_SESSION_TOKEN", ""))
    .config("spark.hadoop.fs.s3a.endpoint.region", os.environ.get("AWS_REGION", "us-east-1"))
    .config("spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.TemporaryAWSCredentialsProvider")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    # Hadoop catalog of the Spark lab
    .config("spark.sql.catalog.lab", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.lab.type", "hadoop")
    .config("spark.sql.catalog.lab.warehouse", f"s3a://{BUCKET}/warehouse")
    # Polaris REST catalog
    .config("spark.sql.catalog.polaris", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.polaris.type", "rest")
    .config("spark.sql.catalog.polaris.uri", f"{os.environ['POLARIS_URI']}/api/catalog")
    .config("spark.sql.catalog.polaris.warehouse", os.environ["POLARIS_CATALOG"])
    .config("spark.sql.catalog.polaris.credential", CREDENTIAL)
    .config("spark.sql.catalog.polaris.scope", "PRINCIPAL_ROLE:ALL")
    .config("spark.sql.catalog.polaris.io-impl", "org.apache.iceberg.hadoop.HadoopFileIO")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")
print("Polaris principal:", PRINCIPAL)

print("\n===== NAMESPACES =====")
spark.sql("SHOW NAMESPACES IN lab").show()
spark.sql("SHOW NAMESPACES IN polaris").show()

if PRINCIPAL == "dev":
    print("\n===== REGISTER =====")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS polaris.silver")
    existing = {r.tableName for r in spark.sql("SHOW TABLES IN polaris.silver").collect()}
    for table in ["orders", "users"]:
        if table in existing:
            print(f"silver.{table} already registered")
            continue
        version = spark.sparkContext.textFile(
            f"s3a://{BUCKET}/warehouse/silver/{table}/metadata/version-hint.text").first().strip()
        metadata = f"s3a://{BUCKET}/warehouse/silver/{table}/metadata/v{version}.metadata.json"
        print("Registering", metadata)
        spark.sql(f"CALL polaris.system.register_table(table => 'silver.{table}', metadata_file => '{metadata}')").show()

print("\n===== READ THROUGH POLARIS =====")
spark.sql("SHOW TABLES IN polaris.silver").show()
spark.sql("SELECT count(*) AS orders FROM polaris.silver.orders").show()
spark.sql("SELECT count(*) AS users FROM polaris.silver.users").show()
spark.stop()
