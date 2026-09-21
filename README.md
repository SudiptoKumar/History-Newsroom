# Today in History Bot V1.3

A dataset-first Telegram history channel bot. It publishes real historical photographs with concise reader-first stories and modern Telegram Rich Messages.

## V1.3 changes

- Date line is one clean line: `September 21, 1745 - 🇬🇧 Prestonpans`.
- Event year is no longer duplicated on a second line.
- `People`, `Entity`, and `Category` metadata are removed from posts.
- Cerebras rewrites the title and story into a short historical-news style explainer.
- Exa adds web context only when the dataset description is weak or clearly missing context.
- Exactly 3 relevant hashtags are generated. `#TodayInHistory` and date-number hashtags are removed.
- `Today in History` is bold and linked to `https://t.me/HistoryNewsroom`.
- `Source:` is shown with the source name as a clickable link.
- No `Image:` attribution line appears in the Telegram post.
- Real historical images keep their original aspect ratio. The pipeline never crops the image to 16:9.
- Images are only resized/recompressed when Telegram upload limits require it.
- Telegram Bot API Rich Messages are used for heading, paragraph, link, and photo blocks, with the standard `sendPhoto` path as a fallback.
- Image attribution data is retained internally in `state/posted_state.json` for record-keeping even though it is not printed in the post.

## Example post structure

```text
[real historical photograph]

September 21, 1745 - 🇬🇧 Prestonpans

Nikita Khrushchev Elected Soviet Leader

Six months after the death of Soviet leader Joseph Stalin, Nikita Khrushchev succeeds him with his election as first secretary of the Communist Party of the Soviet Union.

Today in History
Source: Wikipedia

#SovietUnion #Leadership #PoliticalHistory
```

The bot does not copy the exact layout of another channel. It uses current Telegram Rich Message primitives (Bot API 10.3) to create the clean structure above.

## Content rules

The 12 supplied CSV files are the authoritative event dataset. External context is used only to clarify an event when the database description is weak, and the AI prompt is instructed not to invent dates, people, figures, quotations, motives, or political judgments.

The generated story is intentionally short: 50–80 words and 2–4 sentences. It should tell the reader what happened and provide enough context to understand the event without turning the post into a long article.

## Images

The image system looks for a real historical image, prioritizing Wikimedia Commons and optionally using Exa to improve Commons discovery. The post contains the real photograph itself, not a generated card and not a logo overlay.

Aspect ratio is preserved. If Telegram's upload constraints require a reduction in dimensions or JPEG quality, the image is scaled proportionally and never center-cropped.

## AI configuration

Cerebras uses the current `gpt-oss-120b` model by default. The project calls the documented `/v1/chat/completions` endpoint and uses structured JSON output for predictable title/story/hashtag generation.

Exa is used through `POST https://api.exa.ai/search` with highlights only when extra context is needed.

Environment variables:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL=@HistoryNewsroom
EXA_API_KEY=...
CEREBRAS_API_KEY=...
CEREBRAS_MODEL=gpt-oss-120b
USE_CEREBRAS=true
USE_EXA_CONTEXT=true
TIMEZONE=Asia/Dhaka
MAX_EVENTS_PER_DAY=20
BATCH_SIZE=10
BATCH_INDEX=1
```

## Local commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env

pytest -q
python main.py --self-test
python main.py --preview --date 2026-09-21 --batch 1
python main.py --dry-run --date 2026-09-21 --batch 1
```

## GitHub Actions

Scheduled runs remain:

- `02:00 UTC` = `08:00 Asia/Dhaka`, batch 1
- `14:00 UTC` = `20:00 Asia/Dhaka`, batch 2

Required repository secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL
CEREBRAS_API_KEY
EXA_API_KEY (optional)
```

The bot defaults to `@HistoryNewsroom` if the channel secret is empty.

## Repository tree

```text
TodayInHistoryBot/
├── .github/
│   └── workflows/
│       └── today-in-history.yml
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
├── state/
│   └── posted_state.json
├── tests/
│   ├── __init__.py
│   ├── test_core.py
│   └── test_images.py
├── .env.example
├── .gitignore
├── config.py
├── content_ai.py
├── dataset.py
├── flags.py
├── formatter.py
├── image_pipeline.py
├── image_resolver.py
├── main.py
├── requirements-dev.txt
├── requirements.txt
├── state_store.py
├── telegram_client.py
└── README.md
```
