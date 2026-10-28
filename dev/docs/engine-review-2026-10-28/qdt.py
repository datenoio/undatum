"""Time one qddate match per kind of value (dates are cheap, other text with digits is not)."""

import time

import pyparsing
from qddate import DateParser

VALUES = [
    'Lorem ipsum 90, "dolor" sit amet',
    "user105666@example.org",
    "city_3146",
    "2020-01-02",
    "c4ca4238a0b923820dcc509a6f75849b",
    "ul. Lenina 15, kv. 3",
]
ROUNDS = 20

parser = DateParser(generate=True)
print("pyparsing", pyparsing.__version__)
for value in VALUES:
    parser.match(value)  # warm-up
    start = time.perf_counter()
    for _ in range(ROUNDS):
        result = parser.match(value)
    elapsed = (time.perf_counter() - start) / ROUNDS * 1000
    print(f"{elapsed:8.2f} ms  {value!r:40} -> {bool(result)}")
