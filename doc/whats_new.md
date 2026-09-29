BSimVis is a tool to analyze similarities across a collection of binaries, based on [Ghidra](https://github.com/nationalsecurityagency/ghidra) analyzers and the BSim (Behavioral Similarity) plugin. It provides an API and Web interface to upload large quantities of decompiled binaries and BSim feature vectors to a Kvrocks database for similarity analysis, function diffing, and binary family clustering.

# New features

This release focuses on automated analysis, triage of functions, and file level similarities views and searches :
- Mandiant capa integration

- Yara rules, with a Rulezet.org API dump tool

- Ghidra FunctionID for standard library identification

- LLM analysis and tagging

The new binary similarity view allows to split the similarities based on these triage. 
Some optimisations for incremental build, and improved clustering. 

![image-20260907144949763](../img/tag_sources.png)

## Agentic LLM analysis
* **Integrated chat agent** — Interactive context aware assistant panel.

![alt text](../img/agent_view.png)

* **MCP server** — Exposes search, call graphs, tags, and similarities to external MCP clients.
* **Batch and pair analysis** — Whole-file reports, batch tagging, and comparative analysis of binary pairs.

![alt text](../img/C2_search.png)

## External analysis integrations for triage
* **YARA preanalysis** tags functions for fast triage and inisights, with an automated Rulezet.org synchronization tool. 
* **capa rule metadata & axes** — ATT&CK/MBC rule metadata is recorded and inherited onto function tags, carrying family/vuln/MITRE/MBC triage axes. 
* **Provenance** — hover an analysis tag to see the rule that created it and its documentation. 

## Nested files and packed files
* **Auto-unpacking pipeline** — Seamless extraction of code from container formats such as Android APKs, fat/universal Mach-O binaries, and ZIP/TAR archives.
* **UPX packer support** — Automatic decompression of UPX-packed binaries, preserving both the original packed sample and the unpacked child executable for side-by-side diffing and analysis.

## Binary similarity & Call graph
* **Code/Library/Content score axes** — for every similarity between two files, similarity score is now split between original code and standard library code.
* **Pivotick call graph** — recursive expansion with depth cap, similarity edges merged in, drag-and-drop/bulk-add, persistent side panel with locked side-by-side diff, and binary clustering with notes sync.

![alt text](../img/call_graph_pivotick.png)
## Clustering
* **New clustering backend** — Threshold union-find replaces HDBSCAN for function clustering with incremental update, lowering drastically clustering time.

## Jobs and injesting
* **Reliable workflows** — Lease-based job scheduler, per-collection lanes, auto-unpacking of container files

## Search, UI & Security
* **Unified search** — Ctrl+K global search with streaming results.
* **Light theme** — Light mode support.
* **Security** — Hardened input escaping to prevent XSS.

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
