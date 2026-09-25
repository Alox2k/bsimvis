# Plan D: retire the ad-hoc metadata fields

Part of [plan_tag_unification_overview.md](plan_tag_unification_overview.md).
Depends on PR B (namespaces for `av:` and `ip:`), PR C (cluster aggregation) and
PR E ([plan_e_inferred_tag_gate.md](plan_e_inferred_tag_gate.md): the
`inferred:` namespace and a gate that makes `inferred_tags` trustworthy). Ships
last.

Revised 2026-09-25 against `dev` at `100bd72`. The 2026-09-24 revision is in
git history (`5d5c01c`).

**Retirement is complete as of this revision.** D1 through D5b have all
shipped. `avtype` / `yara` / `cc_ip` are no longer indexed, aggregated,
searchable through the UI, or returned by the API; only `av:` / `yara:` /
`ip:` tags carry that evidence now. Gate 0 was run against the real
collections by the user directly (not reproducible from this worktree, which
only has the confidential `data/kvrocks/` fixtures never read here) rather
than through the steps below; they are kept as the historical record of what
shipped and in what order.

## Where things stand

- **B, C and E are in.** `av` and `ip` namespaces exist, `tag_distribution` is
  written on every cluster path, and `inferred_tags` is gated on cohesion and
  coverage (`eb69ba7`, `100bd72`).
- **D1, D2 and D4 are in** (`56213af`). `import_tags` mints `av:` / `yara:` /
  `ip:` tags at the three merge points. `BACKFILL_IMPORT_TAGS` exists. The old
  file-level filter params resolve as a union of the tag glob and the legacy
  field index, permanently (Decision 7). Swagger marks them deprecated.
- **D3 is done.** Every cluster, dashboard, detail, diff, graph and LLM
  surface reads `tag_distribution` / `inferred_tags` / tag chips instead of
  the legacy fields. The dashboard's 7 legacy filter inputs are gone; an old
  permalink is rewritten into its tag form on load
  (`dashboard.js` `refreshData`, the `files` branch). The
  `dashboard.js:4021-4022` XSS gap (`yara_distribution[0].value` into HTML
  unescaped) is fixed as part of the flip -- the field no longer exists, and
  its tag-based replacement is escaped.
- **D5a and D5b are done.** `avtype` / `yara` / `cc_ip` / `inferred_yara` /
  `inferred_avtype` / `inferred_filetype` / `inferred_ccip` are out of
  `INDEX_CONFIG`, `SUBSTRING_FIELDS` and `POOL_LOCAL_FIELDS`; cluster meta no
  longer carries the four legacy `*_distribution` keys; function-level
  avtype/yara/cc_ip stopped propagating (Decision 6) and now 400 with
  `RETIRED_FILTER_PARAMS` (`index_config.py`); file-level `inferred_filetype`
  does the same. The six file-level aliases (`avtype`, `yara`, `cc_ip`,
  `inferred_avtype`, `inferred_yara`, `inferred_ccip`) keep resolving forever
  (Decision 7). Old buckets are cleared incidentally by the existing
  `clear_bin_cluster` / `clear_cluster` jobs (extended to also drop the
  avtype/yara/cc_ip buckets), not a new one-off job -- run either against a
  real collection/pool namespace to flush stale entries.
- Raw `avtype` / `yara` / `cc_ip` values remain stored on file metas
  (Decision 10) and the CSV importer still emits them; only indexing,
  aggregation and API output are gone.

## Context

| field | written by | becomes |
|:---|:---|:---|
| `avtype` | CSV import | `av:<vendor>:<family>#<label>` via `av_tag` |
| `yara` | CSV import | `yara:<category>:<family>#<rule>` via `yara_tag` |
| `cc_ip` | CSV import | `ip:<address>` |
| `filetype` | CSV import | stays metadata; see Decision 5 |
| `file_names` | upload and unpack | stays metadata (identity, not vocabulary) |
| `inferred_yara`, `inferred_avtype`, `inferred_filetype`, `inferred_ccip` | bin clustering, pool file clustering | `inferred_tags` |
| `inferred_filename`, `inferred_md5` | bin clustering | stay as they are |

The `yara` metadata field is not YARA scan output; scan output is already a
`yara:` tag (`ghidra_job.py`). The field carries imported analyst or VT data.
Only the imported one is retired.

`inferred_filename` and `inferred_md5` stay as fields. A filename and an md5 are
identity, and as tags they would mint one vocabulary entry per file.

### The write surface

CSV metadata reaches a file meta by three routes, and every one is a plain dict
merge:

1. **Upload with `--metadata`, API analysis.** `bsimvis_upload.py:719-750` parses
   the CSV, stages it (`metadata_service.stage_metadata`), and the worker merges
   it: `routes/file.py:775` into `file_metadata_extra`, then
   `ghidra_job.py:299` `file_meta.update(extra_meta)`. Programs inside a project
   pick up their own row at `ghidra_job.py:573`.
2. **Upload with `--metadata`, local analysis.** `bsimvis_upload.py:79` updates
   `data["file_metadata"]` before the JSON upload; `processing_service` stores it.
3. **`bsimvis metadata` (propagate).** `bsimvis_metadata.py:20-50` parses the same
   CSV (a copy of the upload parser), `metadata_service.propagate_metadata`
   merges it. `tags` is in `list_fields` there, so a `tags` key in the update
   **replaces** the file's tag list wholesale.

`processing_service.py:286` also copies `avtype` / `yara` / `cc_ip` / `filetype`
onto every function meta, and `INDEX_CONFIG` indexes them at `func` level.

### The read surface

Backend, by file:

| file | what reads the fields |
|:---|:---|
| `routes/search_file.py` | filter map (`:73-80`), projection (`:516-523`), inferred computation (`:684-733`), cohesion-gated cluster info (`:266`) |
| `routes/bin_cluster.py` | yara distribution search (`:361`, `:389`), cluster payload (`:547-550`), member rows (`:647-650`), file row (`:1010-1014`) |
| `routes/llm.py` | `inferred_meta` for the chat context (`:332-348`) |
| `services/llm_service.py` | prompt field labels (`:693-742`) |
| `services/llm_tools.py` | `get_file_info` payload (`:361-363`), tool descriptions (`:372`, `:647`) |
| `services/analysis_orchestrator.py` | prompt labels (`:1296-1298`) |
| `services/scan_service.py` | scan report cluster payload (`:876-881`) |
| `services/cluster_utils.py` | `collect_member_values`, `default_bin_cluster_name`, `DISTRIBUTION_FIELDS` |
| `services/cluster_service.py` | pool file clusters (`:3060-3170`) |
| `services/bin_cluster_service.py` | both persist paths and the incremental retire |
| `services/metadata_service.py` | `list_fields`, the cluster recompute (`:414-432`) |
| `services/index_config.py` | `INDEX_CONFIG`, `SUBSTRING_FIELDS`, `POOL_LOCAL_FIELDS` |

JS, by reference count: `dashboard.js` 22, `bin_cluster_views.js` 21,
`views/file_view.js` 7, `previews.js` 6, `binary_similarity.js` 6,
`table_renderers.js` 4, `similarity_graph.js` 4, `cluster_views.js` 2,
`views/cluster_detail_view.js` 1, `views/call_graph_view.js` 1.

Tests and scripts: `scripts/test_cluster_meta_freq.py`,
`scripts/test_default_bin_cluster_name.py`, `scripts/test_api_endpoints.py`.

## Decisions

1. **Mint tags server-side, in one function.**
   `tag_taxonomy.import_tags(meta) -> list[str]` reads `avtype`, `yara`, `cc_ip`
   and returns canonical `av:` / `yara:` / `ip:` tags, filtered through
   `filter_tags(..., "import")`. It is called at the three merge points above,
   never in the CLI, so re-running an old CLI against a new server still produces
   tags. The two copies of the CSV parser are left as they are; they emit fields,
   and the server turns fields into tags.
2. **Merge, never replace.** Import tags are unioned into `tags`. The import
   path must never send a `tags` key through `propagate_metadata`'s
   list-field replace. That would wipe every analysis tag (FID, capa, YARA scan)
   on the file.
3. **Dual write for one release.** The fields keep being written next to the
   tags. Nothing that reads a field breaks while readers migrate.
4. **Flip reads per view, not all at once.** Each view is its own commit and can
   be reverted alone.
5. **`filetype` stays metadata.** `cluster_dimensions` already derives
   `executable_format` and `architecture` from Ghidra's own program info, which
   is ground truth. The imported `filetype` is an analyst string next to it. It
   is kept as a plain field, and its `inferred_filetype` is replaced by the
   existing `executable_format_distribution`, not by a tag.
6. **Function level: drop, do not replace.** `av` and `ip` have
   `propagate_func=False`, so function metas get no tag. The function-level
   `avtype` / `yara` / `cc_ip` copies and indexes go away at D5. Function search
   already filters by file tag through the file join. Check that before D5 and
   add the join if it is missing. Do not propagate.
7. **Old filter params keep working by alias.** `?avtype=mirai` becomes a tag
   filter on the `av:*:mirai` family bucket. Old permalinks and saved searches
   keep resolving.
8. **Cluster naming moves to tags.** `default_bin_cluster_name` prefers the top
   `family` row of `tag_distribution`, then the top `yara` row, then the filename.
   The order is the same as today; only the source changes.
9. **A retired param never silently widens or empties a result.** Removing a
   field from `INDEX_CONFIG` changes two search paths without an error:
   - Function search builds its filters from `INDEX_CONFIG`
     (`search_function.py:297-310`). `?avtype=` / `?yara=` / `?cc_ip=` then stop
     being read, and the search returns every function.
   - File search's `?inferred_filetype=` has no tag alias. Its bucket is cleared,
     so it matches nothing.

   One constant, `RETIRED_FILTER_PARAMS`, lists every retired name. Both routes
   return 400 on a retired name that has no alias, with the replacement in the
   message (`file_tag=av:*<x>*`, `executable_format`). The six aliased file
   params stay as aliases for good, because they cost one dict. Nothing in the
   UI sends the retired names after D3.
10. **Raw file fields stay stored.** `import_tags` reads `avtype` / `yara` /
    `cc_ip` off the file meta, and they are the provenance of the tag. D5 stops
    indexing, aggregating and returning them. It does not stop storing them at
    file level. The function-level copies do stop (Decision 6).

## Stages

Every stage below (D1 through D5b) is done. Their text is kept as the
historical record of what shipped and in what order.

### Gate 0 — confirm the backfill

On every real collection, and after it every pool:

1. Run `bsimvis metadata backfill-tags` (D2) if it has not run.
2. Re-cluster so `tag_distribution` has `family` and `ioc` rows.
3. Sample 50 files that carry `avtype` / `yara` / `cc_ip`. Each must carry the
   matching `av:` / `yara:` / `ip:` tag.
4. For 10 real filter values, compare the old field search to the tag search:
   `?avtype=x` against `?tag=av:*x*`. Same result set, or a difference you can
   explain.

A view flipped before this gate shows empty cluster cards.

### D1 — mint on write

`import_tags` in `tag_taxonomy`, with a demo check on a ClamAV label, a YARA
rule, an IP, `-` and empty values. Call sites: `ghidra_job.py:299`,
`processing_service` where file meta is first stored, and
`propagate_metadata`. Index the new tags through the normal tag field indexing
(`tag_prefixes` buckets). Recompute affected clusters the way
`propagate_metadata` already does.

`av_tag`'s vendor argument: the CSV carries no vendor column. Use `unknown`
unless the label shape identifies one (ClamAV's `Platform.Type.Family-N-N`).
Record this in the function docstring. It decides which bucket a family lands
in.

### D2 — backfill existing collections

`JobType.BACKFILL_IMPORT_TAGS`, on the normal queue. It walks each collection's
files through the file registry (not `KEYS`), calls `import_tags`, unions and
indexes, and chunks as a continuation so it interleaves with other work. It is
idempotent and deletes no fields. A re-cluster afterwards fills `tag_distribution`.

### D3 — flip the reads

Row shape changes: a legacy distribution row is `{value, count, percent}`, a
`tag_distribution` node is `{tag_id, count, coverage, score, children}`. Views
read the axis (`family`, `yara`, `ioc`) and render the top of the tree. Extract
one small JS renderer for a `tag_distribution` axis, shared by the views, before
flipping them. `cluster_detail_view.js:507` already walks the shape and is the
starting point.

Order, one commit each. Line numbers are as of `100bd72`.

1. **Done.** `routes/bin_cluster.py` and `scan_service.py` payloads carry
   `tag_distribution` next to the legacy keys.
2. **Cluster views.** Extract the axis renderer first, from
   `cluster_detail_view.js:507`. Then flip `bin_cluster_views.js` (31
   references), `cluster_views.js` (2), `previews.js:629-654` and the dashboard
   cluster cards (`dashboard.js:3980-3981` naming, `:4021-4022` summary). The
   cards at `:4021-4022` put `yara_distribution[0].value` into HTML without
   `escapeHtml`. That value comes off a sample, so the flip must escape the tag
   id. Also check why `scripts/test_xss_escaping.js` does not flag these lines.
3. **Done.** `views/file_view.js` inferred tab reads `inferred_tags`.
4. **Dashboard file search.** This is the step that stops the fields being
   searchable in the UI.
   - Delete the seven inputs `flt-file-yara`, `flt-file-avtype`, `flt-file-ccip`,
     `flt-file-inf-yara`, `flt-file-inf-avtype`, `flt-file-inf-type`,
     `flt-file-inf-ccip` (`dashboard.js:1838-1848`), their `syncInput` calls
     (`:2130`, `:2132`) and their `params.set` lines (`:2571-2603`).
   - The replacement already exists: the tag filter cards (`tag` param) and
     the `flt-file-inf-tags` input.
   - Old permalinks: when the view loads, rewrite each legacy param into its
     tag form and drop it from the URL. `avtype=x` becomes `tag=av:*x*`,
     `yara=x` becomes `tag=yara:*x*`, and `cc_ip=x` becomes `tag=ip:*x*`. This is
     the same glob the server alias uses (`search_file.py:537`). `inferred_*=x`
     moves into `inferred_tags` only when that param is empty. Otherwise it stays
     in the URL and the server alias resolves it. Without the rewrite, a
     permalink applies a filter that no input shows.
   - `attachAutocomplete(..., 'yara' | 'avtype' | 'cc_ip')` goes with the
     inputs. The autocomplete route has nothing to change.
5. **Detail, diff and graph views.** `views/file_view.js` (the "CC IP" row at
   `:462` and the other raw-field rows), `binary_similarity.js:3356` (the diff
   row), `similarity_graph.js:174-177`, `:437`, `table_renderers.js:434` (the
   `cc_ip` column) and `views/call_graph_view.js`. Delete the rows. The tag
   chips already show the same values. Before deleting the diff row, check that
   `binary_similarity.js` shows a tag diff. If it does not, one row that
   compares the `ip:` / `av:` / `yara:` tag sets replaces it.
6. **LLM surfaces.** `llm.py:332-348`, `llm_service.py:693-742`,
   `llm_tools.py:361-372`, `:647`, `analysis_orchestrator.py:1296-1298`. This
   changes what the model sees. `inferred:` tags stay out of evidence entirely:
   `llm.py`'s `inferred_meta` section is the only place they appear, labelled as
   derived. The MCP server re-exports `llm_tools`, so check its tool
   descriptions too.

After step 6, grep the JS and the LLM files for the field names. Only the
permalink rewrite in step 4 may still name them.

### D4 — filter aliases

In `search_file.py`'s filter map, `avtype` / `yara` / `cc_ip` / `inferred_*`
become aliases onto `tags` / `inferred_tags`. Prefix matching is one bucket
lookup because `tag_prefixes` indexes every ancestor. Swagger keeps the old
params, marked deprecated.

### D5 — delete

D5 is split so the API stops exposing the fields before anything is dropped
from storage. D5a is code only and reverts with `git revert`. D5b is the
one-way step.

#### D5a — the API stops returning and reading the fields

Start after D3 step 6. No UI reads these keys by then.

- **Responses.** Drop the legacy keys from `bin_cluster.py:558-561` (the four
  `*_distribution` keys), `:661` (member `cc_ip`), `:1024-1025` (`yara_matches`,
  `ips`) and `scan_service.py:877-882`. Drop them from `search_file.py`'s
  projection and inferred computation (`:266-277`, `:712-765`). Keep
  `executable_format`, `filename` and `md5` there. Drop them from the swagger
  response model (`swagger.py:782-813`).
- **Cluster search.** `bin_cluster.py:360-400` matches keywords against both
  `yara_distribution` and `tag_distribution`. Keep only the tag half.
- **Filters.** Add `RETIRED_FILTER_PARAMS` (Decision 9). It is checked in
  `search_file.py` before the filter map at `:62-87` and in
  `search_function.py` before its `INDEX_CONFIG` loop at `:297`. The
  function-level `avtype` / `yara` / `cc_ip` params return 400 from this
  point, not at D5b, so nothing depends on them when D5b removes them. Swagger
  lists the aliased params as deprecated and drops the others.
- **Tests.** `scripts/test_api_endpoints.py:871` asserts `avtype_distribution`;
  change it to assert `tag_distribution`. `:2705` and `:2742` propagate
  `avtype`; add an assert that the `av:` tag appears. Add one check per retired
  function param that returns 400. `scripts/test_cluster_meta_freq.py` and
  `scripts/test_default_bin_cluster_name.py` move with Decision 8.

#### D5b — stop writing and unindex

Start after D5a has run on a real collection for a while with no complaints.

- Remove `avtype` / `yara` / `cc_ip` and `inferred_yara` / `inferred_avtype` /
  `inferred_filetype` / `inferred_ccip` from `INDEX_CONFIG`
  (`index_config.py:52-59`, file and func), `SUBSTRING_FIELDS` (`:206-217`)
  and `POOL_LOCAL_FIELDS` (`:378-381`).
- Remove them from `metadata_service.list_fields` (`:203-208`),
  `processing_service`'s function-level copy (`:286-298`),
  `cluster_utils.collect_member_values` / `DISTRIBUTION_FIELDS` (`:80`,
  `:108-110`), and `default_bin_cluster_name`'s fallback.
- Remove the cluster meta writers: the four `*_distribution` keys and the
  `inferred_mapping` blocks in `bin_cluster_service.py:680`, `:1719`, `:2028`
  and `cluster_service.py:3186`. `inferred_filename` and `inferred_md5` stay.
- In `search_file.py`, the alias drops its legacy half (`:538-540`) and becomes
  a tag glob only. `inferred_filetype` moves into `RETIRED_FILTER_PARAMS`.
- Clear the buckets with `_clear_indexes_via_registry` (already used for the
  inferred fields at `bin_cluster_service.py:2203-2206`). It walks the registry,
  never `KEYS`. Run it once per collection and once per pool namespace
  `global:pool:{id}` through a clear job on `jobs:pending:high`. Add no new
  `JobType` if an existing maintenance action can take a field list.
- The CLI parsers (`bsimvis_metadata.py:40`, `bsimvis_upload.py:741`) keep
  emitting the fields. The server stores them and mints tags from them
  (Decision 10).

Field values in stored file metas are left in place. They are inert once nothing
indexes or reads them, and removing them means rewriting every meta for no user
benefit.

The CSV columns keep their names. The upload format is a user contract.

#### Not retired

- `filetype` (Decision 5), `file_names`, `inferred_filename`, `inferred_md5`.
- The `yara:` tags that YARA scans write. Only the imported `yara` field is
  retired.
- Free-text `q` loses its substring hits on the raw fields. It still searches
  the `tags` field, so `q=mirai` still finds `av:unknown:mirai`.

## Risk

D5 is the one-way step. Everything before it is additive and revertible. Start D5
only after D3 has run on a real collection and the tag path gives the same
answers the fields gave.

D1 is the other risk: the import path sits next to a list-field replace. Test the
propagate path on a file that already carries analysis tags.

## Verification

- `tag_taxonomy` demo: `import_tags` cases.
- After D1, `bsimvis metadata` on a file that has FID and capa tags: those tags
  survive, and the `av:` / `ip:` tags appear.
- After D2, on a real collection, sample files: the `av:` tag set matches
  `avtype`. The same check for `yara` and `cc_ip`.
- `./scripts/wt-test.sh --only <area>` at each stage, `Failed : 0` required.
  Compare failure labels to the diff, not to a remembered count.
- UI stages: `node --check` on each changed file and
  `node scripts/test_xss_escaping.js`. Tag ids come off uploaded samples.
- `scripts/test_cluster_meta_freq.py` and `scripts/test_default_bin_cluster_name.py`
  move in step with D3 and Decision 8.
