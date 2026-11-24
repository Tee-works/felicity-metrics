# Dialect notes: DuckDB locally, Postgres in production

The SQL in `sql/` runs unchanged on both. `scripts/postgres_check.sh` loads the same CSVs into Postgres 18
with `\copy`, runs every file, and prints the headline tables. On the seeded data the results match the
DuckDB run row for row (13,721 conversations, 828 timezone corrections, 144 client-report rows).

Choices made to keep it portable:

| Topic | What the SQL does | Why |
|---|---|---|
| Rounding | `ROUND(CAST(x AS NUMERIC), n)` | Postgres has no `ROUND(double precision, int)`. |
| Durations | `EXTRACT(EPOCH FROM (a - b))` | Works in both. DuckDB's `date_diff` does not exist in Postgres. |
| Percentiles | `percentile_cont(p) WITHIN GROUP (ORDER BY x)` | Ordered-set syntax, supported by both. |
| Regex | `regexp_replace(s, pattern, repl, 'g')`, `[0-9]` not `\d`, no `\b` | Postgres regex treats `\b` as backspace; DuckDB uses RE2 where it is a word boundary. |
| Hashing | `md5(...)` | Both have it. In production use a keyed hash (HMAC with a secret) so contact keys cannot be reversed by hashing a list of known emails. |
| Timezones | UTC in `TIMESTAMP` columns plus `ref.uk_clock_changes` | Avoids DuckDB's ICU extension. On Postgres, `AT TIME ZONE 'Europe/London'` is the simpler option and should replace the lookup. |
| Booleans in aggregates | `MAX(CASE WHEN ... THEN 1 ELSE 0 END)` | Avoids differences in `bool_or` and boolean-to-int casts. |
| Loading | `COPY t FROM 'file' (FORMAT csv, HEADER true)` | DuckDB reads a local path. On Postgres, use `\copy` from psql (as the script does) or a server-side path. |
| Rebuilds | `DROP TABLE IF EXISTS` then `CREATE TABLE AS` | Fine at this scale. In production these would be dbt models (incremental for messages) or materialised views. |

Not portable on purpose: nothing. If a model needs a DuckDB-only function it should live in Python, not SQL.
