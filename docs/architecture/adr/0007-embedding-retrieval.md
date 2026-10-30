# 7. Memory retrieval by embeddings

- **Status:** Proposed
- **Date:** 2026-10-30
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

UC-09 draws on what the companion remembers. UC-25 step 3 gathers memories "by how recent, how
important and how related they are". The specification takes this from Generative Agents, which
adds three normalised terms and computes relevance as a cosine between embeddings. The earlier
records did not say how Cognia computes "how related".

NFR-15 forbids any download, so an embedding model must ship in the installer. NFR-09 needs the
memory list to work with the model stopped. NFR-04 needs a deletion to remove all traces.

## Decision

**Relevance is the cosine between embeddings.** The score adds recency, importance and relevance.
Each term is scaled from 0 to 1, and the three weights are equal. Recency decays with each real
hour since the item was last retrieved. Section 6.8.1 of
[`ARCHITECTURE.md`](../ARCHITECTURE.md) gives a worked example.

**A second server computes embeddings.** The installer ships one small GGUF embedding model.
`--embedding` restricts a `llama-server` to embeddings, so Cognia runs a second child process, under
the same supervisor as the chat server (ADR 0002). Measurement selects the model.

**Vectors live on the row they describe.** `memory_items`, `commitments` and `journal_entries` each
gain `embedding`, `importance` and `last_retrieved_at`. `settings.embedding_model` names the model
that made the vectors. A deletion removes the vector with the row, and `secure_delete` covers it. An
edit clears the vector, and a later job computes it again.

**Search reads each vector.** Python 3.12 has `math.sumprod`, so the standard library does the work.
This is D-16 in `ARCHITECTURE.md`, and it is a proposal. `sqlite-vec` is the upgrade if a measured
search on a real store takes too long.

**Retrieval stays outside the rules.** The result depends on a model, so it cannot be an input to a
pure rule. It selects what a reply or a reflection reads. The reply source tables record the result,
and a replay does not repeat it.

## Consequences

**Positive**

- The companion finds a different wording of the same idea, which keyword search misses.
- Deleted memories leave no second copy, because no separate vector table exists.

**Negative**

- One more model in the installer, one more process, and more memory.
- `embedding` is a `BLOB`, so a reader of the file with `sqlite3` sees numbers that mean nothing. The
  text columns stay readable, and ADR 0002's promise about conversations is unchanged.
- Each search reads all vectors, so its time grows with the store.
- With the embedding server stopped, retrieval uses recency and importance only.

**Neutral**

- A new embedding model means that each vector is computed again.

## Alternatives considered

**FTS5 with BM25.** Built into SQLite, deterministic, and it needs no model. Rejected because it misses
a different wording, such as "thesis" and "chapter 3". FTS5 also keeps old index entries by default, so
it would need `secure-delete`.

**A hybrid of FTS5 and embeddings.** The best recall. Rejected because it has the cost of both.

**Recency and importance only.** The least work. Rejected because it does not meet UC-25 step 3.

**A separate vector table, or `sqlite-vec` from the start.** Rejected for now. A separate table needs a
key for each kind of row. `sqlite-vec` is pre-v1 and warns of breaking changes.
