# Plan D: retire the ad-hoc metadata fields

Part of [plan_tag_unification_overview.md](plan_tag_unification_overview.md).
Depends on PR B (namespaces for `av:` and `ip:`), PR C (cluster aggregation) and
PR E ([plan_e_inferred_tag_gate.md](plan_e_inferred_tag_gate.md): the
`inferred:` namespace and a gate that makes `inferred_tags` trustworthy). Ships
last.

Revised 2026-09-24 against `dev` at `5f7f243`.

## Where things stand

- **B is in.** `NAMESPACE_POLICY` has `av` (`family` axis, writers
  `import`/`analysis`) and `ip` (`ioc` axis, `aggregate=False`,
  `vocabulary=False`). `tag_taxonomy.av_tag` parses a vendor label into
  `av:<vendor>:<family>#<label>` and has a demo check.
- **C is mostly in.** `cluster_summary` is the one summary function,
  `tag_distribution` is written on every cluster path, and `inferred_tags` is
  indexed and filterable. Its gaps are PR E.
- **None of D has started.** `av_tag` is called only from its own demo. No
  writer mints `av:`, `ip:` or import-side `yara:` tags from the CSV columns, so
  `tag_distribution` has no `family` or `ioc` rows for any imported data today.
  The `family` axis is fed only by rulezet galaxies.

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

## Stages

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

Order, one commit each:

1. `routes/bin_cluster.py` and `scan_service.py` payloads: add the tag axes next
   to the legacy keys.
2. `bin_cluster_views.js`, `cluster_views.js`, `previews.js`
3. `views/file_view.js` inferred tab: from `inferred_*` to `inferred_tags` (gated
   by PR E)
4. `dashboard.js` filters and columns
5. `binary_similarity.js`, `similarity_graph.js`, `table_renderers.js`,
   `call_graph_view.js`
6. The LLM surfaces (`llm.py`, `llm_service.py`, `llm_tools.py`,
   `analysis_orchestrator.py`). This changes what the model sees. `inferred:`
   tags stay out of evidence entirely: `llm.py:332`'s `inferred_meta` section is
   the only place they appear, labelled as derived.

### D4 — filter aliases

In `search_file.py`'s filter map, `avtype` / `yara` / `cc_ip` / `inferred_*`
become aliases onto `tags` / `inferred_tags`. Prefix matching is one bucket
lookup because `tag_prefixes` indexes every ancestor. Swagger keeps the old
params, marked deprecated.

### D5 — delete

Remove the retired fields from `INDEX_CONFIG` (file and func),
`SUBSTRING_FIELDS`, `POOL_LOCAL_FIELDS`, `list_fields`, `processing_service`'s
`fields_to_copy`, `collect_member_values`, `DISTRIBUTION_FIELDS`, the cluster
meta writers (the four `*_distribution` keys and the legacy `inferred_mapping`
blocks in `bin_cluster_service` and `cluster_service`), the swagger model, and
the CLI parsers' field output. Clear the buckets with
`_clear_indexes_via_registry`, as `clear_clusters` does now.

Field values in stored file metas are left in place. They are inert once nothing
indexes or reads them, and removing them means rewriting every meta for no user
benefit.

The CSV columns keep their names. The upload format is a user contract.

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
