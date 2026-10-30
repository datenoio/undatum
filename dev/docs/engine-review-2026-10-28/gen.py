"""Write a synthetic CSV for the engine benchmark. Usage: python gen.py ROWS OUT.csv"""

import sys

import duckdb

rows = int(sys.argv[1])
out = sys.argv[2]
duckdb.connect().execute(f"""
COPY (
  SELECT i AS id,
         DATE '2020-01-01' + CAST(i % 2000 AS INTEGER) AS dt,
         ['retail','wholesale','online','partner','gov'][CAST(1 + (hash(i) % 5) AS BIGINT)] AS channel,
         'city_' || CAST(hash(i*7) % 5000 AS VARCHAR) AS city,
         round((hash(i*13) % 1000000) / 100.0, 2) AS amount,
         CAST(hash(i*17) % 100 AS INTEGER) AS qty,
         CASE WHEN i % 10 = 0 THEN NULL
              ELSE 'user' || CAST(hash(i*19) % 200000 AS VARCHAR) || '@example.org' END AS email,
         md5(CAST(i AS VARCHAR)) AS token,
         'Lorem ipsum ' || CAST(hash(i*23) % 1000 AS VARCHAR) || ', "dolor" sit amet' AS note
  FROM range({rows}) t(i)
) TO '{out}' (HEADER, DELIMITER ',')
""")
