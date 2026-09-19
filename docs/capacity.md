# What was measured, and on what

Spec 11.2 asks for capacity evidence and insists that dataset limits and the
test environment are stated with every result. So here they are first.

This is a developer's laptop, not the reference deployment in spec 11.2. No
number below is a capacity claim. What is claimed is the shape: whether the
work grows with the invoice, and how.

## The machine

Apple silicon laptop, macOS. MariaDB, Redis and the app all on it. Frappe
v16.22.0, ERPNext v16.26.2, Python 3.14.5. No provider latency included,
because nothing here leaves the machine.

The reference fixture spec 11.2 describes is 4 vCPU and 8 GiB with local
database and Redis. That has not been run. Anyone repeating this on that
machine should expect different numbers and the same shape.

## Checking an invoice

Every line is the same item, the same unit and the same tax account, which
is the worst case for repeated master lookups and the normal case for a
real invoice.

| Rows | Fast check | Full check | Queries |
| --- | --- | --- | --- |
| 1 | 11 ms | 15 ms | 49 |
| 20 | 11 ms | 20 ms | 49 |
| 100 | 14 ms | 47 ms | 49 |
| 1000 | 30 ms | 437 ms | 49 |

Full includes building the canonical document, writing the XML, and running
it through the schema and both official rule layers.

Against the targets in spec 11.2, which are for the reference host and not
this one: Fast under 400 ms for 20 rows, measured at 11. Full under 2
seconds for 20 rows, measured at 20 ms. Full under 10 seconds for 1,000
rows, measured at 437 ms.

## The query count is the part that matters

It is the one measurement that does not depend on the machine, and it is
the one that was wrong.

Queries grew by four per row. A five hundred line invoice asked the
database two thousand and fifty questions, most of them the same question
about the same item. Spec 11.2 says plainly that master queries must not
grow by one per row.

| Rows | Before | After |
| --- | --- | --- |
| 1 | 54 | 49 |
| 20 | 130 | 49 |
| 100 | 450 | 49 |
| 500 | 2050 | 49 |

Five things were being asked per line: the item, its group, the unit, the
tax mapping, and underneath those, the timestamp of every record as it was
recorded for the fingerprint.

It asks once now and remembers, for the length of one extraction only. A
test edits an item after a check and proves the fingerprint still moves, so
remembering an answer does not mean missing a change.

## Not measured

Stated rather than glossed over.

- The reference host in spec 11.2. This is a laptop.
- A site holding 100,000 stored invoices. The due-work queries are indexed
  and bounded by design, and that has not been proven under that volume.
- Concurrent sessions. One at a time here.
- A multi-company site under load, and separate sites on one host.
- Worker throughput against a real provider, which waits on P10.

Each of these belongs to the reference deployment, and none can be
honestly answered from this machine.
