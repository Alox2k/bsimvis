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

Measured on a fresh worktree stack (`scripts/wt-setup.sh`) against a real
corpus: 60 binaries from `~/data/versioned_c/bin` (v01-v10 across arm, linux
x64, ppc, riscv, win32, win64 -- the same small C program cross-compiled and
recompiled 10 times, so the corpus has genuine version drift but only one
program family). Uploaded via `bsimvis upload ... --enable boilerplate` so
member files carry a real tag axis (`boilerplate:runtime`, the cheap
symbol-name tagger) instead of an empty `tag_distribution`. Binary similarity
and clustering ran through the normal upload -> lane pipeline
(BUILD_SIM -> CLUSTER_FUNCTIONS -> BUILD_BIN_SIM -> CLUSTER_BINARIES), default
config (`bin_engine = "threshold_uf"`, `bin_uf_threshold = 0.1`).

**Only `threshold_uf` was measured.** Getting one engine through a full
Ghidra-analyze-then-cluster cycle on this stack took the whole time budget;
`hierarchical_uf`/`hierarchical_snn` were not run. Everything below is
threshold_uf only -- no numbers are given for the hierarchical engines.

**A storage bug blocked reading `tag_distribution` from the listing API
directly.** `/api/bin_cluster/list` and `/api/bin_cluster/members` returned
the right `cohesion_score` and member counts, but every other field
(`tag_distribution`, `yara_distribution`, `filename_distribution`,
`function_count_stats`, `sample_members` names) came back empty for both
clusters. Root cause, traced by reading the code (not by direct Kvrocks
access): `BinClusterService._incremental_cluster_binaries` gets its file list
from `_batch_files`, which reads `{collection}:batch:{batch_uuid}:files` --
already-full file ids (`{collection}:file:{md5}`). Those ids flow unchanged
into the union-find and become the `members` set persisted per cluster.
`_enrich_and_persist_binary_clusters` then fetches member metadata with
`f"{collection}:file:{file_id}:meta"`, i.e. it expects a bare md5 and
double-prefixes every full id it's actually given
(`e0v2:file:e0v2:file:<md5>:meta`, which never exists). `cohesion_score` is
unaffected because `_node_cohesion` reads bin-sim score keys directly, not
member metas. This is a real, independent bug in the threshold_uf path (not
part of plan E, not fixed here per E0's "no code change" scope) and should be
filed separately -- it means **every threshold_uf collection on this branch
has blank distributions in its stored bin_cluster meta today**, regardless of
the inferred-tag gate.

To still get a faithful coverage measurement, this file's numbers were
recomputed with the real, unmodified `cluster_utils.cluster_summary` /
`inferred_tag_values` functions, fed with: real member id lists from
`/api/bin_cluster/members`, real per-file `tags` from `/api/file/search`, and
the real `cohesion_score` from `/api/bin_cluster/list` -- every input is API
data, only the aggregation step (which the server already runs, just can't
currently read back) was replayed locally instead of read pre-stored.

**Cohesion histogram (threshold_uf, 2 clusters, 60 members, all real):**

| Bucket | Clusters | Members |
|---|---|---|
| 0.4-0.5 | 1 | 40 |
| 0.5-0.6 | 1 | 20 |

Cluster 1 (0.4207 cohesion, 40 members: every arm/linux/ppc/riscv build across
all 10 versions) and cluster 2 (0.5755 cohesion, 20 members: both win32 and
win64 builds). This directly confirms the claim at `bin_cluster_service.py:514`
on real data: the larger, still-legitimate threshold_uf cluster sits at 0.42,
"well under" a 0.5 floor, even on a clean corpus with no adversarial or
unrelated files forced together.

`tag_distribution` (`boilerplate:runtime`, the only axis this corpus
produces): cluster 1 coverage 0.75 (30/40 members tagged -- riscv/ppc symbol
tables are sparser, ~1/6 of members carry no boilerplate hit), cluster 2
coverage 1.0 (20/20).

**3x3 grid (cohesion floor x coverage floor -> clusters kept / members kept,
of 2 clusters / 60 members):**

| cohesion \ coverage | >=0.3 | >=0.5 | >=0.7 |
|---|---|---|---|
| >=0.3 | 2 / 60 | 2 / 60 | 2 / 60 |
| >=0.5 | 1 / 20 | 1 / 20 | 1 / 20 |
| >=0.7 | 0 / 0 | 0 / 0 | 0 / 0 |

Coverage never binds in this corpus (both real coverage values, 0.75 and 1.0,
clear every tested floor) because `boilerplate:runtime` is a coarse,
near-universal tag once rolled up to file level (see the bug note above:
`tag_taxonomy.origin_parent` deliberately collapses the full
`boilerplate:runtime:<libc>:<phase>` tag to just `boilerplate:runtime` at
file scope, so there is only ever one node per axis here -- a messier axis
like `av:` family tags would show real coverage spread; this corpus doesn't
have one). Cohesion is what actually gates: at the plan's fallback default
(0.5), the 40-member cluster -- two-thirds of this corpus's files -- loses
its inferred tags entirely, while the 20-member cluster keeps them. At 0.7,
both clusters are blanked.

**Caveats on this measurement:** n=2 clusters from a single homogeneous
program family is thin evidence for a histogram; it cannot show what a
messier, multi-family collection's cohesion spread looks like, and the
coverage axis was never actually tested by anything other than a uniform
tag. Treat the shape of the histogram as illustrative, but treat "a
real threshold_uf cluster measured well under 0.5 cohesion" as confirmed,
not hypothetical -- that was the specific, narrow thing E0 was gated on.

**Defaults picked:**

- `clustering.inferred_min_coverage = 0.5` -- keep the plan's default. Nothing
  in this measurement argues for changing it: it never bound here, and 0.5 is
  still the right "majority, not a plurality" bar for when a real spread
  shows up.
- `clustering.inferred_min_cohesion` -- keep the plan's fallback (0.5) as the
  *general* default, but add the per-engine override the Open Question
  proposed: **`clustering.inferred_min_cohesion_threshold_uf = 0.3`.** Reasoning:
  this measurement reproduces, on real data, exactly the blanking risk the
  Open Question warned about -- a 0.5 floor silently drops inferred tags from
  the majority of files in the default engine's most common cluster shape (a
  large, low-but-nonzero-threshold union-find merge). 0.3 still rejects a
  cluster with no real cohesion (a pure coincidental union), but stops
  penalizing threshold_uf specifically for being a lower, transitive-closure
  threshold by construction (`bin_uf_threshold = 0.1`) rather than a direct
  pairwise floor. `hierarchical_uf`/`hierarchical_snn` are unmeasured and keep
  the plain 0.5 fallback until someone runs the equivalent pass for them.

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

## Follow-up: retire the `inferred:` string prefix

Decision 7 registered `NAMESPACE_POLICY["inferred"]` so a hand-typed
`inferred:av:x` would be dropped at every `filter_tags` boundary. On review this
defends against a string shape that only exists because the prefix itself
exists -- remove the prefix and there is nothing of that shape left to type.

The real protection was never the prefix: `_member_tag_values`
(`cluster_utils.py`) reads only `meta["tags"]`/`meta["user_tags"]`, never
`meta["inferred_tags"]`, so a stored consensus guess can never re-enter as
evidence for another cluster's vote regardless of what string it's spelled
with. And every analysis namespace a gate could promote (`av:`, `yara:`, ...)
already excludes `user` from its own `writers` tuple, so a human typing the
bare tag directly (`av:x`, no wrapper) is rejected the same as before --
that check predates and is independent of Decision 7.

Net: `inferred_tag_values` (`cluster_utils.py`) now returns the plain tag id
(`av:clamav:mirai`, not `inferred:av:clamav:mirai`). `NAMESPACE_POLICY["inferred"]`
is deleted -- dead once no tag carries that namespace. `search_file.py`'s
`_TAG_FILTER_ALIASES` globs drop the `inferred:` literal (`"av:"` instead of
`"inferred:av:"`); the `inferred_tags` *field* stays the real separator, unchanged.
Existing stored values keep their old prefixed spelling until the next
cluster (re)build overwrites them (`_store_inferred_tags` replaces, never
unions) -- no migration script, no direct DB edit.
