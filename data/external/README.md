# Local public-data workspace

Run `python scripts/download_public_data.py` to download and canonicalize UCI Online
Retail II. The archive, workbook, canonical transactions, and local quality report are
ignored by Git because they are reproducible from the licensed source and are not needed
for code review.

Only source metadata, aggregate validation results, tests, and a small fictional fixture
are committed. See [`docs/PUBLIC_DATA_CARD.md`](../../docs/PUBLIC_DATA_CARD.md) for source,
license, integrity, exclusions, and analytical limitations.
