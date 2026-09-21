# Today in History Bot V1

A lightweight Telegram bot that publishes historical events from the supplied 12-month dataset. The CSV dataset is the source of truth. V1 does not perform news discovery or invent missing events.

## What V1 does

- Loads January–December CSV files and normalizes schema differences.
- Resolves the current date in `Asia/Dhaka`.
- Selects up to 20 events for that date, ranked by the dataset's `Historical significance score`.
- Publishes the first 10 events in batch 1 and the next 10 in batch 2.
- Uses persistent event IDs so reruns do not duplicate successful posts.
- Finds a real historical image from Wikimedia Commons; optional Exa search improves event-specific Commons discovery.
- Crops the real source image to a clean 16:9 photo; no branded card, generated illustration, or text overlay is added.
- Falls back to a text-only Telegram post when no suitable image can be found.
- Posts the image with an HTML-formatted Telegram caption and source links.
- Retries transient HTTP failures.
- Never fills an incomplete date with fabricated events.

## Dataset

The repository contains all 12 supplied CSV files in `data/`. The final TIH logo is kept as channel/bot branding and is not composited onto event photographs.

Current dataset validation result: **6,879 records**. Most calendar dates have 20 events, but April is incomplete at 5–6 events per day and six November dates have fewer than 20. V1 publishes only records actually present for a date.

## Environment variables

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL=@TodayInHistory
EXA_API_KEY=...
TIMEZONE=Asia/Dhaka
MAX_EVENTS_PER_DAY=20
BATCH_SIZE=10
BATCH_INDEX=1
```

`EXA_API_KEY` is optional and improves real-image discovery when the dataset source page does not expose a useful event image. `CEREBRAS_API_KEY` remains an optional future extension. It is not required by V1 because the dataset already contains event descriptions and verification/significance metadata.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL` before publishing.

## Test and preview

```bash
python main.py --self-test
python main.py --preview --date 2026-09-21 --batch 1
python main.py --dry-run --date 2026-09-21 --batch 1
pytest -q
```

## GitHub Actions

The workflow uses UTC cron entries corresponding to Dhaka local time (UTC+6):

- 08:00: batch 1
- 20:00: batch 2

It can also be started manually with a selected batch. The workflow runs the self-test before publishing and commits the posting state after execution.

Required repository secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL
EXA_API_KEY (optional)
```

## Repository structure

```text
TodayInHistoryBot/
├── .github/workflows/today-in-history.yml
├── assets/
│   └── today-in-history-logo.png
├── data/
│   ├── January.csv
│   ├── February.csv
│   ├── March.csv
│   ├── April.csv
│   ├── May.csv
│   ├── June.csv
│   ├── July.csv
│   ├── August.csv
│   ├── September.csv
│   ├── October.csv
│   ├── November.csv
│   └── December.csv
├── generated/
├── state/posted_state.json
├── config.py
├── dataset.py
├── flags.py
├── formatter.py
├── image_pipeline.py
├── main.py
├── state_store.py
├── telegram_client.py
├── tests/test_core.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Design principle

The historical dataset is authoritative. External discovery, article scraping, event clustering, and news-ranking systems are deliberately excluded from V1. They can be added later only where the dataset itself cannot satisfy a new requirement.
