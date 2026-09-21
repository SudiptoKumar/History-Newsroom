# Today in History Bot

A dataset-first Telegram bot that turns a curated year-round history database into concise daily historical posts with real historical imagery and Telegram Rich Messages.

The project is intentionally simple: **your 12 monthly CSV files are the source of truth**. The bot does not depend on news feeds or continuous event discovery. It finds the events for today's date, prepares a reader-friendly story, finds a real historical image when possible, and publishes the result to the `Today in History` Telegram channel.

---

## What This Project Does

Every day, the bot reads the bundled history dataset and publishes the most significant events recorded for that calendar date.

The default daily plan is:

- Up to **20 events per date**
- **Batch 1:** first 10 events
- **Batch 2:** next 10 events
- Two scheduled runs per day through GitHub Actions
- No invented filler events when a date contains fewer than 20 records

The current bundled dataset contains **6,879 historical event records** across January through December.

---

## How It Works

```text
12 Monthly CSV Files
        │
        ▼
Load + Normalize Dataset
        │
        ▼
Validate Records
        │
        ▼
Find Today's Events
        │
        ▼
Rank by Historical Significance Score
        │
        ▼
Select Batch (10 events)
        │
        ├───────────────┐
        ▼               ▼
Cerebras AI         Wikimedia Commons
        │               │
        │               └─ Real historical image
        │
        └─ Title + Story + 3 Hashtags
        │
        ▼
Build Telegram Rich Message
        │
        ▼
Publish to @HistoryNewsroom
        │
        ▼
Save Event ID + Message ID
        │
        ▼
Prevent Duplicate Posts
```

### Processing principle

The dataset remains authoritative for the event's identity, date, and core facts. AI is used to **rewrite and clarify** the material for readers, not to decide what historical event exists.

When an event description is weak, Exa can provide additional web context for the AI rewrite. If AI is unavailable, the bot falls back to a deterministic local rewrite using facts already present in the dataset.

---

## Telegram Post Format

Each post follows this structure:

```text
[Real historical photograph]

September 21, 1745 🇬🇧 Prestonpans

Battle of Prestonpans

A concise historical mini-story explaining what happened,
who was involved when relevant, and the essential context
needed for a reader to understand the event.

Today in History

#RelevantTag #RelevantTag #RelevantTag

Source: Wikipedia
```

### Formatting rules

- The date, year, flag, and location appear on **one line**.
- `People`, `Entity`, and `Category` metadata are not shown.
- The event title is presented as the main heading.
- The story normally targets **45–70 words** and about **3–4 sentences**.
- `Today in History` is **bold and clickable** to the channel.
- Exactly **3 relevant hashtags** are used.
- Generic tags such as `#TodayInHistory` and date-number tags are excluded.
- `Source: Wikipedia` appears at the **very end** of the post and is clickable.
- No separate `Image:` attribution line is displayed.
- Image attribution and source-page information are retained internally in state when an image is used.

---

## Image System

The bot posts the **real historical image itself**, not a generated news card.

### Image workflow

```text
Event
  ↓
Wikimedia Commons search
  ↓
Match image using event title, people, location, year, etc.
  ↓
Download image
  ↓
Validate image + license metadata
  ↓
Prepare for Telegram
  ↓
Publish
```

Exa can also help discover a relevant Wikimedia Commons page when the direct Commons search does not find a suitable result.

### Aspect ratio policy

The bot does **not** force historical photographs into 16:9.

- Original composition is preserved.
- No center-cropping.
- No decorative frame.
- No logo overlay.
- No generated card.
- Images are proportionally resized only when Telegram upload limits require it.
- JPEG quality can be reduced when necessary to meet the file-size limit.

If no suitable image is found, the bot publishes the event as a **text-only Rich Message**.

---

## AI Layer

### Cerebras

Cerebras is the main content-enrichment service.

**Purpose:**

- Rewrite the event title into a natural historical-news headline.
- Turn a short database description into a clearer mini-story.
- Add essential context when supported by the available record/context.
- Generate exactly 3 relevant hashtags.
- Return predictable structured JSON.

Default model:

```text
CEREBRAS_MODEL=gpt-oss-120b
```

Endpoint used by the project:

```text
https://api.cerebras.ai/v1/chat/completions
```

The bot keeps the supplied historical record as its primary factual basis and explicitly instructs the model not to invent dates, people, figures, quotations, motives, or unsupported claims.

### Exa

Exa is optional.

**Purpose:**

- Provide additional web context when the dataset description is too short or clearly incomplete.
- Help discover Wikimedia Commons pages for historical images.

Endpoint used by the project:

```text
https://api.exa.ai/search
```

If `EXA_API_KEY` is missing, the bot continues using the dataset and direct Wikimedia Commons search.

---

## Telegram Rich Messages

The bot uses Telegram's structured **Rich Messages** through `sendRichMessage` rather than relying only on a traditional text caption.

The message is built from blocks such as:

```text
Photo block
Paragraph block       → date/location
Heading block         → event title
Paragraph block       → story
Paragraph block       → Today in History link
Paragraph block       → hashtags
Paragraph block       → source link
```

There is also a standard Bot API fallback using `sendPhoto` or `sendMessage` if the Rich Message request fails.

Official Telegram Bot API documentation:

https://core.telegram.org/bots/api

Telegram introduced Rich Messages in Bot API 10.1 and expanded the feature in later 2026 releases. The project uses the structured block-based interface exposed by the Bot API.

---

## Data Source

The repository contains one CSV file for every month:

```text
January.csv
February.csv
March.csv
April.csv
May.csv
June.csv
July.csv
August.csv
September.csv
October.csv
November.csv
December.csv
```

The loader normalizes small schema differences between monthly files into one internal `Event` model.

### Important event fields

The dataset contains fields such as:

- `Event ID`
- `Day`
- `Month`
- `Year`
- `Era`
- `Event title`
- `Description`
- `City location`
- `Region`
- `Modern country`
- `Event type`
- `Event category`
- `People involved`
- `Historical entity`
- `Source 1 name`
- `Source 1 URL`
- `Date certainty`
- `Verification status`
- `Historical significance score`

Not every monthly file has exactly the same optional columns. The dataset loader handles these differences automatically.

### Daily selection

Events for the current month/day are sorted primarily by:

```text
Historical significance score ↓
Event ID
Event title
```

The bot then limits the day to `MAX_EVENTS_PER_DAY` and selects the requested 10-event batch.

---

## Duplicate Protection

The bot stores publication state in:

```text
state/posted_state.json
```

For every published event it records information such as:

- Event ID
- Telegram message ID
- Publication timestamp
- Send mode
- Historical image source page
- Image credit

Before publishing, the bot checks the event ID. A previously published event is skipped.

The state file is updated after each successful publication, so a failure later in a batch does not require already-published events to be sent again.

---

## APIs and Services

| Service | Required | Purpose |
|---|---|---|
| Telegram Bot API | Yes | Publish posts to the channel |
| Cerebras API | Recommended | Generate the reader-friendly title/story/hashtags |
| Exa API | Optional | Extra historical context and Commons image discovery |
| Wikimedia Commons API | No API key | Search and retrieve historical images |

### Required credentials

```text
TELEGRAM_BOT_TOKEN
CEREBRAS_API_KEY
```

### Optional credential

```text
EXA_API_KEY
```

### Channel

Default channel:

```text
@HistoryNewsroom
```

The bot also accepts:

```text
@HistoryNewsroom
https://t.me/HistoryNewsroom
t.me/HistoryNewsroom
-100xxxxxxxxxx
```

For a channel, the bot must be added with permission to publish posts.

---

## Python Dependencies

### Runtime

The project intentionally uses a small dependency set:

```text
requests==2.32.5
urllib3==2.5.0
Pillow==11.3.0
```

| Package | Purpose |
|---|---|
| `requests` | HTTP requests to Telegram, Cerebras, Exa, and Wikimedia Commons |
| `urllib3` | HTTP transport dependency used with the requests stack |
| `Pillow` | Image validation, EXIF orientation handling, resizing, and JPEG preparation |

### Development / testing

```text
pytest==9.0.2
```

No Telegram framework is required. The project talks directly to the Telegram Bot API over HTTP.

---

## Environment Configuration

Copy the example file:

```bash
cp .env.example .env
```

Then configure:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL=@HistoryNewsroom

CEREBRAS_API_KEY=your_cerebras_key
EXA_API_KEY=your_exa_key

CEREBRAS_MODEL=gpt-oss-120b
USE_CEREBRAS=true
USE_EXA_CONTEXT=true

TIMEZONE=Asia/Dhaka
MAX_EVENTS_PER_DAY=20
BATCH_SIZE=10
BATCH_INDEX=1
BOT_NAME=Today in History
```

### Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | empty | Telegram bot token |
| `TELEGRAM_CHANNEL` | `@HistoryNewsroom` | Target Telegram channel |
| `CEREBRAS_API_KEY` | empty | Cerebras API key |
| `EXA_API_KEY` | empty | Exa API key |
| `CEREBRAS_MODEL` | `gpt-oss-120b` | Cerebras model name |
| `USE_CEREBRAS` | `true` | Enable AI enrichment |
| `USE_EXA_CONTEXT` | `true` | Allow Exa context for weak records |
| `TIMEZONE` | `Asia/Dhaka` | Calendar date used by scheduled runs |
| `MAX_EVENTS_PER_DAY` | `20` | Maximum events considered for one date |
| `BATCH_SIZE` | `10` | Events published per run |
| `BATCH_INDEX` | `1` | Local/default batch selection |
| `BOT_NAME` | `Today in History` | Internal bot name |

Never commit `.env` or API keys to GitHub.

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/TodayInHistoryBot.git
cd TodayInHistoryBot
```

### 2. Create a virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Create `.env`

```bash
cp .env.example .env
```

On Windows, simply copy `.env.example` to `.env` manually if `cp` is unavailable.

Add your credentials.

### 5. Run validation

```bash
python main.py --self-test
```

### 6. Run the test suite

```bash
pytest -q
```

### 7. Preview a date without publishing

```bash
python main.py --preview --date 2026-09-21 --batch 1
```

### 8. Dry-run the publishing pipeline

```bash
python main.py --dry-run --date 2026-09-21 --batch 1
```

A dry run processes the events and logs the generated title/story without sending anything to Telegram.

### 9. Publish locally

```bash
python main.py --date 2026-09-21 --batch 1
```

For the second batch:

```bash
python main.py --date 2026-09-21 --batch 2
```

Normally you should use `--preview` or `--dry-run` before the first real publish.

---

## GitHub Actions

The repository includes:

```text
.github/workflows/today-in-history.yml
```

Scheduled runs are:

| UTC | Bangladesh time | Batch |
|---|---|---|
| `02:00` | `08:00` | 1 |
| `14:00` | `20:00` | 2 |

The workflow also supports manual execution with `workflow_dispatch` and a batch selector.

### GitHub repository secrets

Add these under:

```text
Settings → Secrets and variables → Actions
```

Required:

```text
TELEGRAM_BOT_TOKEN
CEREBRAS_API_KEY
```

Recommended / optional:

```text
TELEGRAM_CHANNEL
EXA_API_KEY
```

The workflow defaults to `@HistoryNewsroom` when `TELEGRAM_CHANNEL` is not supplied.

The workflow requests `contents: write` permission because the bot commits the updated `state/` data after successful publication.

---

## Repository Structure

```text
TodayInHistoryBot/
├── .github/
│   └── workflows/
│       └── today-in-history.yml
│
├── assets/
│   └── today-in-history-logo.png
│
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
│
├── state/
│   └── posted_state.json
│
├── tests/
│   ├── __init__.py
│   ├── test_core.py
│   └── test_images.py
│
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

### What each file does

| File | Responsibility |
|---|---|
| `main.py` | Orchestrates the complete daily run, batch selection, publishing, and CLI commands |
| `dataset.py` | Loads all 12 CSV files, normalizes fields, filters dates, sorts events, and validates the dataset |
| `content_ai.py` | Cerebras generation, optional Exa context lookup, title/story/hashtag generation, and deterministic fallback |
| `formatter.py` | Builds Telegram Rich Message blocks and the standard fallback caption |
| `image_resolver.py` | Searches Wikimedia Commons and optionally uses Exa to discover Commons pages |
| `image_pipeline.py` | Preserves image ratio and prepares images for Telegram without cropping |
| `telegram_client.py` | Direct Telegram Bot API communication, Rich Messages, photo upload, and retry handling |
| `state_store.py` | Loads, updates, and saves publication state |
| `flags.py` | Converts country codes/aliases into country flag emoji |
| `config.py` | Environment variables, paths, defaults, and country aliases |
| `assets/` | Final Today in History brand logo |
| `data/` | Authoritative 12-month history dataset |
| `tests/` | Automated regression tests |
| `.github/workflows/` | Scheduled and manual GitHub Actions publishing |

---

## Command Reference

| Command | Use |
|---|---|
| `python main.py --self-test` | Validate dataset, post structure, and project invariants |
| `pytest -q` | Run automated tests |
| `python main.py --preview --date YYYY-MM-DD --batch 1` | Preview selected events and generated content locally |
| `python main.py --dry-run --date YYYY-MM-DD --batch 1` | Execute processing without sending to Telegram |
| `python main.py --date YYYY-MM-DD --batch 1` | Publish a real batch |

If `--date` is omitted, the bot uses the current date in the configured `TIMEZONE`.

---

## Failure and Fallback Behavior

The bot is designed so that one external failure does not automatically destroy the whole pipeline.

### AI failure

If Cerebras is unavailable or returns unusable structured output:

```text
Cerebras
   ↓ failure
Local deterministic fallback
```

The fallback uses the event record already in the dataset.

### Image failure

If no suitable Wikimedia Commons image is found:

```text
Image lookup
   ↓ failure
Text-only Rich Message
```

### Rich Message failure

If `sendRichMessage` fails:

```text
Rich Message
   ↓ failure
sendPhoto / sendMessage fallback
```

### Dataset failure

If validation detects missing IDs, titles, descriptions, source URLs, invalid dates, or similar critical issues, the run stops rather than publishing potentially bad data.

---

## Testing

The test suite covers the core production assumptions, including:

- Full dataset loading
- Dataset validation
- Daily event selection
- Two-batch behavior
- Incomplete-date behavior
- Date-line formatting
- Rich Message structure
- Photo block handling
- Hashtag rules
- Footer order
- Telegram channel normalization
- Story length ceiling
- Image aspect-ratio preservation

Run:

```bash
pytest -q
```

And:

```bash
python main.py --self-test
```

---

## Design Principles

### Dataset-first

The supplied historical dataset is the canonical event source.

### Reader-first

Metadata is transformed into a short explanation that tells the reader what happened instead of exposing raw database fields.

### Evidence-aware

External context is used to clarify weak records, not to replace the curated event database.

### Real imagery

Use historical images when a relevant image can be found. Do not fabricate historical photographs.

### No unnecessary cropping

Preserve the source image composition whenever possible.

### Deterministic publishing

Significance score, batch selection, and event IDs provide stable behavior.

### Idempotent runs

A published event is recorded and skipped on later runs.

### Minimal dependencies

The project uses direct HTTP APIs instead of a large Telegram framework or unnecessary middleware.

---

## Security Notes

- Keep `.env` out of Git.
- Store production secrets in GitHub Actions Secrets.
- Never hard-code bot tokens or API keys in source files.
- The bot only needs channel publishing permission for its normal operation.
- Treat source URLs and dataset content as untrusted input and keep HTML escaping enabled when formatting posts.

---

## Operational Notes

The bot intentionally does **not** invent missing daily events. If a date contains fewer records than `MAX_EVENTS_PER_DAY`, it publishes only the available records.

The state file is part of the operational data flow. In GitHub Actions, successful state changes are committed back to the repository so the next run knows which events have already been published.

The `generated/` directory is runtime image storage and is ignored by Git. It can be deleted safely when you want to clear the local image cache.

---

## Project Identity

**Channel:** [Today in History](https://t.me/HistoryNewsroom)  
**Telegram:** `@HistoryNewsroom`

The final brand logo is stored at:

```text
assets/today-in-history-logo.png
```

The logo is a brand asset only. It is **not** overlaid on historical photographs.

---

## License and Image Rights

This repository contains a curated historical dataset and code. Individual historical images may come from Wikimedia Commons and can have different licenses or attribution requirements.

The bot retains image source and credit information internally when an image is selected. Always verify the license of an individual image before reusing it outside the Telegram publication workflow.

---

## Quick Start

For the shortest path from clone to local test:

```bash
git clone https://github.com/YOUR_USERNAME/TodayInHistoryBot.git
cd TodayInHistoryBot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
# add TELEGRAM_BOT_TOKEN and CEREBRAS_API_KEY to .env
python main.py --self-test
pytest -q
python main.py --preview --date 2026-09-21 --batch 1
```

Then configure the GitHub Actions secrets and let the scheduled workflow handle daily publication.
