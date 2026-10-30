"""Write the three messy CSV files of the review. Usage: python messy.py OUT_DIR"""

import os
import sys

out = sys.argv[1]
rows = ["inn;name;amount"] + [f"00{7700000000 + i};Компания {i};{i}" for i in range(3000)]
late_type = list(rows)
late_type[2500] = "007700002499;Компания X;н/д"  # text in a numeric column after row 100
ragged = list(rows)
ragged[1500] = "007700001499;Компания Y;15;лишнее"  # one extra field

with open(os.path.join(out, "cp1251.csv"), "w", encoding="cp1251") as fh:
    fh.write("\n".join(rows) + "\n")
with open(os.path.join(out, "utf8_late_type.csv"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(r.replace(";", ",") for r in late_type) + "\n")
with open(os.path.join(out, "ragged.csv"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(ragged) + "\n")
