import os
import sys

import pandas as pd
import trino

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 70)

conn = trino.dbapi.connect(
    host="trino",
    port=8080,
    user=os.environ.get("TRINO_USER", os.environ["KUBERNETES_NAMESPACE"]),
    http_scheme="http",
    catalog="lakehouse",
)


def sql(statement):
    cur = conn.cursor()
    cur.execute(statement)
    rows = cur.fetchall()  # the query only completes when its results are fetched
    columns = [c[0] for c in cur.description] if cur.description else []
    return pd.DataFrame(rows, columns=columns)


def show(label, statement):
    print(f"\n>>> {label}")
    print(sql(statement).to_string(index=False))


def title(text):
    print(f"\n{'=' * 20} {text} {'=' * 20}")


def run(sections):
    names = sys.argv[1:] or list(sections)
    for name in names:
        sections[name]()
