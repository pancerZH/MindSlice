# Retrieval evaluation

A small, bilingual (English and Chinese) evaluation of how well `search()` ranks memory cards. The method
follows [SpaceBridge](https://github.com/pancerZH/SpaceBridge): per-query scores, 95% bootstrap intervals over
queries, paired comparisons against alternative systems, pass lines fixed before results, frozen data digests,
and a ledger of which data informed which decision.

- **[PLAN.md](PLAN.md):** the rules: data, systems, metrics, pass lines, verdicts, and the ledger.
- **[results/summary.md](results/summary.md):** the latest generated tables.

## Run it

```bash
python -m evals.retrieval check          # data integrity and digests; scores nothing
python -m evals.retrieval run            # dev and limits splits, printed
python -m evals.retrieval run --splits dev,holdout,limits,holdout-2,holdout-3 --write   # also writes results/
```

It needs nothing beyond the repository and runs in about a second. `tests/test_retrieval_eval.py` runs in CI.
It verifies the data, the metrics and the patch isolation of the comparison systems. It also fails if any
split or language loses more than 0.02 nDCG@5 against `results/run.json`.

## Layout

| Path | What it is |
| --- | --- |
| `data/kb-en.slice/`, `data/kb-zh.slice/` | The two handbooks, mounted as `@kb-en` (precedence 50) and `@kb-zh` (40), both `curated` |
| `data/overlay/` | Runtime cards copied into `@overlay`: they supersede or extend handbook cards |
| `data/tiny-en/`, `data/tiny-zh/` | Two 10-card overlay-only memories (an agent's first week on one project), with saturated vocabulary. Queries with `corpus = "tiny-en"` or `"tiny-zh"` run there |
| `data/aliased/` | The same five corpus directories, with every card's `aliases` line written by an agent following the `slice-builder` skill. `check` verifies nothing else differs |
| `data/queries.toml` | Queries with graded judgments, by split (`dev`, `holdout`, `limits`, `holdout-2`, `holdout-3`), language, corpus and category |
| `data/DIGESTS.json` | SHA-256 of the corpus and of each split, frozen before the first run |
| `systems.py` | `mindslice`, plus versions of it that each change one design decision: `coverage-first` (the reverted ordering), `unweighted-coverage`, `strict-phrase`, `v1-baseline`. One keeps the engine and changes the data: `aliases` (built from `data/aliased/`) |
| `metrics.py` | nDCG@5, Recall@10, MRR@10, the bootstrap, verdicts |
| `results/` | `summary.md`, `per_query.jsonl` (every system's top 10 per query), `run.json` (environment, digests, numbers). `archive/` keeps the record each past decision was read on |

## Reading the results

- **Absolute numbers are optimistic.** One author wrote the corpus, the queries and the engine, so queries share
  more words with their answers than real users' would. Compare systems, not raw scores, with other projects.
- **The `limits` split is meant to fail.** Synonyms, typos, Traditional script and cross-lingual queries show
  where an agent must rephrase, because lexical search can't bridge them.
- **`holdout-3` counts the other handbook's card as related.** Its blind writer graded the other team's
  same-topic card 1 on 73 of 80 queries, which caps nDCG@5 for a system that never returns it. Read its
  lines next to the same-team section of the summary, which drops those judgments.
- **20 queries per group means wide intervals.** A difference decided by one or two queries can't settle a
  design question; the ledger says when that happened.

## Adding queries

Don't edit `holdout` to fix a result. Add a new split instead (for example `holdout-2`): write its queries and
judgments, add it to `SPLITS` in `dataset.py`, run `freeze`, record its digest and any new lines in `PLAN.md`,
and only then run it. Changes to `dev` are fine, but rerun `freeze` and note them in the ledger.
