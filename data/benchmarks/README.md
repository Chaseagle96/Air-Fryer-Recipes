# Benchmark adjudication

The checked-in benchmark is a versioned validation set, not a production training set.

## Duplicate benchmark

The current seed set is intentionally small and adversarial. The V5 target is at least **500 manually adjudicated pairs** across:

- definite syndicated/republished duplicates
- probable duplicates with wording/unit changes
- same dish family but independent recipes
- similar titles with different principal ingredients
- hard negatives near the production similarity threshold

`output/dedupe_label_queue.csv` is generated from ambiguous live-corpus candidates. Human review should populate the adjudication columns before examples are promoted into `dedupe_pairs.json`. Production CI requires at least 95% precision and 90% recall on the checked-in benchmark. Benchmark examples should not be selected solely to make the current model look good.

## Evidence calibration

`evidence_labels.json` records reviewed fixture expectations for extracted rating, count, and evidence class. Empirical confidence replacement is disabled for an evidence class until it has at least 30 reviewed examples. Until then, semantic confidence defaults remain in force.

## Fixture policy

Live deep crawls may create sanitized candidate HTML snapshots under the workflow artifact `fixture-candidates`. Those candidates never overwrite `tests/fixtures/real_pages/` automatically. A fixture is promoted only through a reviewed source change so a publisher markup regression cannot silently redefine the test contract.
