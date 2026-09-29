BSimVis is a tool to analyze similarities across a collection of binaries, based on [Ghidra](https://github.com/nationalsecurityagency/ghidra) analyzers and the BSim (Behavioral Similarity) plugin. It provides an API and Web interface to upload large quantities of decompiled binaries and BSim feature vectors to a Kvrocks database for similarity analysis, function diffing, and binary family clustering.

# 0.6.0

This release focuses on scan-time triage, function-similarity precision, and maintenance
tooling for running collections at scale.

## Scan / fast mode
* **Compare without ingest** — `bsimvis scan` / `POST /api/scan` analyses a file against
  existing collections without writing a single Kvrocks key, so an analyst can triage a
  sample before deciding to commit it. Multi-file upload, container unpacking (archives,
  packed files) and a recent-scans table are included; `POST /api/scan/{id}/commit`
  promotes a scan into a real collection without re-running Ghidra.

## Function similarity
* **Weighted cosine & binary cosine** — two new runtime matching algorithms alongside
  the existing BSim score, selectable per collection. Needs proper benchmarking, but
  looks more precise on early runs.
* **Discovery pass** (`similarity.discovery`) — stored function-sim docs only kept the
  pairs BSim proposed above `similarity.min_score`, so a rewritten-but-related function
  left no edge and the stored file score never counted it. The build can now greedy-match
  stored edges first, then re-match whatever's left straight from the collection's own
  tf vectors, recovering those edges at build time instead of only at read time.

## Clustering
* **SNN backend** — a shared strong-neighbor pass replaces plain threshold chaining,
  preventing over-merging where two loosely-linked binaries used to drag a whole cluster
  together.
* **Code/library axis split for clustering** — a binary identified as shared library code
  no longer scores and clusters as original code, so an analyst's cluster view stays
  focused on unidentified code.

## Tags & metadata
* **New tag namespaces and automatic metadata propagation** — retires the old inferred-tag
  system; namespace policy and propagation are now enforced consistently across function,
  file and cluster tags.
* **Boilerplate tagging** — automatic recognition of common compiler/runtime boilerplate
  function names (mingw, uclibc/libc internals, pformat-style helpers) for fast triage.

## Maintenance tools
* **Collection / pool maintenance API** — delete file entries, and rebuild any step of
  the similarity pipeline with different parameters or algorithms in place.
* **`bsimvis transfer`** — copy a collection between instances over the CLI.

## Security
* **XSS escaping sweep** — closed remaining unescaped sample-derived values reaching
  `innerHTML`, including the file detail view's metadata fields (fixed by new
  contributor [elhoim](https://github.com/elhoim)).
* Dependency bumps (anyio, pillow, setuptools, urllib3) for known advisories, and
  offline support via vendored (no-CDN) frontend libraries.

**New contributor:** [elhoim](https://github.com/elhoim).

**Next steps:** benchmarking BSimVis settings and algorithms for the storage/speed/precision
tradeoff across different datasets, to land on good default settings.
