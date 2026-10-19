# Test data — example only

The CSV file(s) in this directory (e.g. `table-13_2026-02-25.csv`) are a
point-in-time **example** export of the Linux System definition, provided for
local testing of the package manager comparison scripts in this repo.

They are **not** an authoritative or current source. The Linux System
definition is updated as new tables are published, and any package manager
comparison work intended to reflect the real, current definition must always
pull a fresh export rather than rely on the file(s) checked in here.

The latest, correct, current version of the Linux System definition should
always be downloaded from the CSV export tool at:

https://definition.openinventionnetwork.com/export/

## Downloading the latest definition via curl

The export page is backed by a small JSON/CSV API. The currently published
("recent") table can be resolved via `/api/tables/recent`, and its data
exported via `/api/export/csv`.

Two-step approach — resolve the current table, then download it:

```bash
# 1. Find the logical name of the currently published table (e.g. "table-13")
TABLE=$(curl -sf https://definition.openinventionnetwork.com/api/tables/recent \
  | jq -r '.recent_table.file_name | sub("\\.json$"; "")')

# 2. Download the full export for that table, with all available fields,
#    saving it as table-name_yyyy-mm-dd.csv
curl -sf -o "${TABLE}_$(date +%F).csv" "https://definition.openinventionnetwork.com/api/export/csv?table=${TABLE}&fields=name,package_version,description,download_url,version_url,project_url,purl"
```

Notes:
- `-o "${TABLE}_$(date +%F).csv"` saves the response as e.g.
  `table-13_2026-08-18.csv` (table name + today's date), rather than using
  the server's default `Content-Disposition` filename (which also embeds a
  `_all_` filter tag).
- The `fields` parameter is required and must be a comma-separated list drawn
  from the fields returned by `/api/export/fields?table=<name>`; the set used
  above (`name,package_version,description,download_url,version_url,project_url,purl`)
  is the full set of fields currently offered by the export tool.
- `table-13` was the current Table at the time this README was written.
  Do not hard-code it — always resolve it dynamically via
  `/api/tables/recent` as shown above, since the "current" table changes as
  new tables are published.

## Unit tests

`test_package_nominations.py` runs `src/package_nominations.py` on small
listings and tables it writes itself (it does not use the example CSV):

```bash
python -m unittest discover -s test
```
