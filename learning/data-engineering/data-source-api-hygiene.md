# Data-Source API Hygiene

**TL;DR:** When you ingest data from a third-party API, the API has opinions about how you should behave. Honoring them earns you reliable access and forward compatibility. Five basics: identify yourself with `User-Agent`, respect rate limits, retry-with-backoff, verify integrity (hash), and make your client idempotent.

---

## What it is

Every public data API — Scryfall, OpenAI, HuggingFace Hub, Twitter v2, weather services, market data providers — has a documented set of expectations for clients. Ignoring them works for a hobby script. **Production ML pipelines that ingest from APIs need to behave like good citizens** or they get rate-limited, banned, or silently degraded.

---

## Why it matters

**For this project:** Our Phase 1 downloader hit a 400 error on the first attempt because Scryfall now requires a `User-Agent` header on every request. Adding it made the difference between "API rejects me" and "API works."

**For ML engineering jobs:** Data ingestion from APIs is bread-and-butter work. The interviewer will ask:

- "Your training pipeline depends on an external API. How do you make it reliable?"
- "What do you do when the API rate-limits you?"
- "How do you verify the data you downloaded is correct?"

These are the five basics that show up in every senior answer.

---

## The five basics

### 1. Identify yourself

Send a `User-Agent` that says who you are. Many APIs reject anonymous requests. From Scryfall's docs (and similar from many others):

> All API requests must include a `User-Agent` header... otherwise, your request may be rejected with a 400 error.

```python
HEADERS = {
    "User-Agent": "MTGCardScanner/0.1 (+https://github.com/cgerrity/mtg-card-scanner)",
    "Accept": "application/json",
}
```

The `(+URL)` convention lets the API operator contact you if your traffic causes a problem. That **earns you forgiveness** when your client misbehaves accidentally.

### 2. Respect rate limits

Most APIs publish a rate limit:

- Scryfall: 50–100 ms between requests (their docs)
- OpenAI: tokens per minute, requests per minute, varies by tier
- HuggingFace Hub: variable, watch for 429
- GitHub: 5000 requests/hour with auth

Patterns:

- **Sleep between requests** matching the published limit
- **Parse the `Retry-After` header** when you hit 429 / 503 and honor it
- **Track your usage** if the API exposes counters (e.g. `X-RateLimit-Remaining`)

```python
import time
time.sleep(0.1)  # Scryfall's recommended floor between calls
```

### 3. Retry with exponential backoff

Network failures and 503s happen. Retry — but cap attempts and back off exponentially:

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry = Retry(
    total=5,
    backoff_factor=1.0,           # 1s, 2s, 4s, 8s, 16s between attempts
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "HEAD"],
)
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=retry))
```

For ML, this pattern lives in libraries like `tenacity` and `backoff`. Know them.

### 4. Verify integrity

When the API publishes a hash or `Content-Length`, check it:

- **Stream + SHA256** the body as you download (single pass, no extra memory).
- **Compare with the published hash** if available.
- **Record the hash you observed** even if no published hash exists — it lets you detect silent changes to your snapshot.

Our `scryfall_download.py` does this — hashes during the stream, writes the digest to a sidecar JSON for reproducibility.

### 5. Be idempotent

Re-running the script should be safe and cheap:

- If the resource hasn't changed, skip the download (check the upstream `updated_at`).
- If the previous run died halfway, the partial file should be detectable and recoverable. Atomic rename (`.partial` → final) is the cheapest way.

```python
# Our pattern:
tmp = dest.with_suffix(dest.suffix + ".partial")
# ... download to tmp ...
tmp.rename(dest)  # atomic rename — final file only appears if download succeeded
```

---

## Bonus: progress reporting in pipelines

In an interactive terminal, `\r` carriage-return lets you rewrite a single line of progress. But when stdout is piped (CI, log capture, our Claude session), each `\r` becomes a new line in the capture — a 500MB download with progress-per-chunk becomes 200KB of log noise.

Detect this and adapt:

```python
if sys.stderr.isatty():
    sys.stderr.write(f"\r  {seen_mb:.1f} MB / {total_mb:.1f} MB")
else:
    # log every N MB instead of every chunk
    if seen_mb - last_logged >= 25:
        print(f"  {seen_mb:.1f} MB downloaded", file=sys.stderr)
        last_logged = seen_mb
```

This shows up everywhere — `tqdm` does it automatically (`disable=not sys.stderr.isatty()`), Hugging Face's progress bars do it, etc. Worth wiring up yourself when you're writing pipelines that run in both interactive and CI contexts.

---

## Watch out for

- **API quirks change.** Scryfall didn't always require `User-Agent`; they added it as abuse grew. Code that worked yesterday can fail today. Build retry/backoff defensively.
- **Mixing concerns.** Don't conflate "is the network healthy" with "is the API healthy." A 503 means the API is overloaded — backoff. A connection error means the network is. Both retry but for different reasons.
- **Caching pitfalls.** A CDN may return cached responses that don't reflect the latest API state. Trust the `updated_at` or version stamp, not local-disk modification time.
- **Auth tokens in logs.** Scrub authorization headers before printing requests. A `User-Agent` is fine to log; an `Authorization: Bearer ...` token is not.
- **Retry-induced double effects.** If a write fails, idempotency keys matter. For pure-read GETs this is rarely an issue.

---

## In this project

Our `data/scryfall_download.py` implements:

- `User-Agent` + `Accept` headers
- SHA256 hashing during stream
- Sidecar `.meta.json` with version + hash for reproducibility
- Idempotency via `updated_at` comparison (skip re-download if cached)
- Atomic rename (`.partial` → final)
- TTY-aware progress reporting

Things we don't yet do but would in a production pipeline:

- Exponential backoff (Scryfall bulk download is single-request — moot here)
- Rate limit honor (we only make ~2 requests per build run)
- Resume from partial download via HTTP Range header (we re-download instead — simpler, fine for our scale)

---

## See also

- [Streaming large data](../ml-engineering/streaming-large-data.md)
- [Reproducible pipelines](../ml-engineering/reproducible-pipelines.md) — hash verification is one of its pillars

---

## Interview angle

> **"You're building an ETL job that pulls from a third-party API. Walk me through your reliability concerns."**

A senior answer covers the five basics above, then:

1. Monitoring — failures should page someone, not silently corrupt downstream
2. Schema versioning — if the API changes its schema, your downstream consumers should detect it (we use a `db_version` row in `meta`)
3. Graceful degradation — if today's snapshot fails, use yesterday's
4. Provider contact — your `User-Agent` includes a way for the provider to reach you when something goes wrong on either side
