# Plan E: gate inferred tags on cohesion and coverage

Part of [plan_tag_unification_overview.md](plan_tag_unification_overview.md).
Follow-up to PR C, and a prerequisite for PR D: D3 moves the UI from the
`inferred_*` fields to `inferred_tags`, so `inferred_tags` must be at least as
trustworthy as the fields it replaces before anything reads it.

## Context

PR C writes `inferred:<tag>` values onto every member file of a binary cluster
(`bin_cluster_service._store_inferred_tags`, fed by
`cluster_utils.inferred_tag_values`). As built on `dev` it has no gate of any
kind:

1. **No cohesion gate.** Both writers — the threshold path
   (`bin_cluster_service.py:636`) and the hierarchical path (`:1955`) — call
   `_store_inferred_tags` for every cluster. `cohesion_score` is computed on both
   paths but only stamped onto the distribution nodes
   (`set_tag_distribution_score`). The legacy `inferred_*` fields are gated on the
   hierarchical path (`:1961`) and on the pool file-cluster path
   (`cluster_service.py:3162`), not on the threshold path (comment at `:514`).
   `threshold_uf` is the default `bin_engine`, so the ungated path is the one most
   collections run.
2. **No coverage floor.** `inferred_tag_values` takes `distribution[:1]`, the
   top root per axis, whatever its `coverage`. One member out of a hundred with an
   `av:` tag labels the other ninety-nine.
3. **Hierarchical ancestors stack.** `hierarchical_membership` maps each leaf to
   every cluster it survives into, so `cluster_members` lists a file under each
   ancestor and the loop over `write_nodes` hands it every ancestor's labels. The
   broad, low-cohesion clusters near the root are the ones that label the most
   files.
4. **Values never leave.** `_store_inferred_tags` writes
   `sorted(old | new)` (`:33`). `clear_clusters` drops the index buckets (`:2106`)
   but not the `inferred_tags` list in each file's meta, so the next run unions the
   stale list straight back into the index. The incremental retire path
   (`:1677-1725`) unindexes the legacy `inferred_*` buckets but not
   `inferred_tags`.
5. **The namespace is not registered.** `inferred` has no `NAMESPACE_POLICY` entry.
   It falls through to `DEFAULT_POLICY`, whose flags happen to be right
   (`aggregate=False`, `propagate_func=False`), but `filter_tags` only enforces
   writers on registered namespaces, so any import, user or analysis writer can
   put `inferred:av:...` into plain `tags`.
6. **Pool file clusters write no `inferred_tags`.** `cluster_service.py:3060`
   builds `tag_distribution` but only indexes the legacy fields.

Read-time `min_cohesion` (`search_file.py:264`, `:727`) hides low-cohesion
cluster info in the file view, but the `inferred_tags` index is already written,
so `?inferred_tags=` filtering returns the ungated set.

## Decisions

1. **One gate function, called by every writer.** `inferred_tag_values` takes the
   cluster's cohesion and the two floors and returns `[]` or the gated list. The
   threshold, hierarchical and pool paths all call it; none re-implements the
   test.
2. **Two floors, both in config.**
   - `clustering.inferred_min_cohesion` — cohesion floor for writing inferred
     tags. Default: fall back to `clustering.min_cohesion` (0.5).
   - `clustering.inferred_min_coverage` — share of members that must carry the
     tag. Default 0.5 (a majority).

   Separate keys from `min_cohesion` because `min_cohesion` already gates display
   and the legacy fields; changing its meaning would move other behaviour.
3. **Coverage is applied per node, walking down.** For each axis, emit the deepest
   node on the top root's chain whose `coverage` clears the floor. `av:clamav` at
   100% with `av:clamav:mirai` at 94% yields `inferred:av:clamav:mirai`; with
   mirai at 30% it yields `inferred:av:clamav`. The label never claims more
   specificity than the members support.
4. **Hierarchical: most specific passing cluster wins.** For each file, walk from
   its home cluster (`leaf_home`) up through its ancestors and take the tags of the
   first cluster that passes the gate. Files get one cluster's labels, not the
   union of the tree.
5. **Replace, never union.** Inferred tags are resolved per file once per run and
   written as a replacement. `clear_clusters` and the incremental retire path strip
   the meta field, not just the buckets.
6. **Store the gated list on the cluster meta.** Each cluster's `:meta` carries
   `inferred_tags: [...]` (empty when gated out). The incremental hierarchical
   path needs this: it rewrites only `only_nodes`, but a file's resolution in
   Decision 4 can land on an untouched ancestor, whose gated list is then read back
   from its meta instead of recomputed.
7. **Register the namespace.**
   `"inferred": Policy("inferred", vocabulary=False, aggregate=False, writers=())`.
   Empty `writers` means every `filter_tags` boundary drops it. The clustering
   writer never goes through `filter_tags`, so it is unaffected.

## Open question: the threshold-path default

The comment at `bin_cluster_service.py:514` says a `threshold_uf` cut at
`bin_uf_threshold = 0.1` has an average pair "well under" 0.5, so a 0.5 floor
would blank almost everything on the default engine. That claim has never been
measured on a real collection. E0 measures it before a default is picked.
If it holds, the options are a per-engine default
(`clustering.inferred_min_cohesion_threshold_uf`) or a coverage-only gate on that
engine. Blanking is not an acceptable outcome, and neither is leaving it ungated.

## Changes

### E0 — measure (no code change)

On a real collection per engine, read the `cohesion_score` and
`tag_distribution` coverage of every bin cluster through the API
(`/api/bin_cluster/...` listing; no direct Kvrocks reads) and record:

- cohesion histogram per engine
- how many clusters, and how many member files, would keep inferred tags at
  cohesion floors 0.3 / 0.5 / 0.7 crossed with coverage floors 0.3 / 0.5 / 0.7

Result goes into this file as a table and picks the defaults.

### E1 — gate function and namespace policy

- `cluster_utils.inferred_tag_values(summary, cohesion, min_cohesion,
  min_coverage)` with Decision 3's walk.
- `NAMESPACE_POLICY["inferred"]` per Decision 7.
- `cluster_utils.demo()` covers: gated out below cohesion, gated out below
  coverage, deepest passing node chosen, one member per prefix counted once.
  `tag_taxonomy` demo: `filter_tags(["inferred:av:x"], w) == []` for every writer.

### E2 — threshold path

Every file is in exactly one cluster, so the per-cluster call is also the
per-file resolution. Call the gate, store the list on cluster meta, write
`meta["inferred_tags"]` as a replacement. Delete the `:514` comment.

### E3 — hierarchical path

Split `_store_inferred_tags` into "compute per cluster" (inside the existing
loop, stored on cluster meta) and "resolve per file" (after the loop, Decision 4).
The incremental branch reads untouched ancestors' lists from their meta and
unindexes `inferred_tags` for members of retired and rewritten nodes.

### E4 — pool file clusters

`cluster_service.py:3060` path calls the same gate and writes `inferred_tags`
into the pool namespace. `inferred_tags` is already in `POOL_LOCAL_FIELDS`, so
nothing crosses back into the origin collection.

### E5 — clear

`clear_clusters` walks each `inferred_tags` bucket's members before deleting the
buckets (the registry already lists them) and drops the field from those metas.
Pipeline in batches of 500, the way `propagate_metadata` does.

### E6 — read side

`search_file.py`'s read-time `min_cohesion` stays. It is now a second, stricter
filter on top of a sane write, not the only one.

## What is deliberately not done

- **No gate on the stored distributions.** `tag_distribution` keeps every row and
  its score; PR C's "report, do not blank" still holds. The gate is only on what
  gets written onto member files.
- **No backfill job.** A re-cluster rewrites every inferred tag under the new
  rules, and E5 makes the clear clean. Collections are re-clustered often enough.

## Verification

- `uv run python -m bsimvis.app.services.cluster_utils` and the `tag_taxonomy`
  demo.
- `./scripts/wt-test.sh --only cluster`, `Failed : 0` required, not just
  `RESULT: PASS`. The fixture never forms clusters, so this proves the endpoints
  answer, not that the gate works.
- Manual run on a real collection per engine: re-cluster twice with different
  thresholds and confirm a file that changed cluster, or fell to noise, holds no
  labels from its old cluster.
