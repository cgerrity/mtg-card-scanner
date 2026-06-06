# Learning Notes — MTG Card Scanner

This directory is a **reference library** of concepts encountered during the MTG Card Scanner build. Tracked in git for cross-machine sync and rendering on GitHub.

When you encounter a new concept in the build, look here first. When something new gets taught in a session, a file should get added in the same turn.

---

## Topic organization

```
learning/
├── ml-engineering/        # Concepts for your ML engineer career
├── apple-ios/             # iOS, Swift, Apple ecosystem
├── python-tooling/        # Python project hygiene
└── data-engineering/      # Data pipelines, databases, search
```

New topic dirs get added as the build touches new areas.

---

## Index

### ML Engineering
- [Reproducible pipelines](ml-engineering/reproducible-pipelines.md) — what makes a pipeline reproducible and why interviewers ask
- [Streaming large data](ml-engineering/streaming-large-data.md) — when and how to stream instead of load-all
- [Bayesian streaming inference](ml-engineering/bayesian-streaming-inference.md) — sequential probability updates, log-space arithmetic

### Apple / iOS
- [Bundle identifiers](apple-ios/bundle-identifiers.md) — what iOS uses to identify your app, and why stability matters

### Python tooling
- [Dependency management](python-tooling/dependency-management.md) — requirements.txt, pyproject.toml, pinning, lockfiles
- [Python version management on macOS](python-tooling/python-version-management.md) — why `python3` is the wrong way to create a venv

### Data engineering
- [SQLite for read-mostly workloads](data-engineering/sqlite-readmostly-design.md) — schema choices when reads dominate
- [Data-source API hygiene](data-engineering/data-source-api-hygiene.md) — User-Agent, retry, hash verification, idempotency, progress reporting

---

## File format

Each concept file follows roughly this template:

````markdown
# Concept Name

**TL;DR:** 1-2 sentence summary that explains it in one breath.

## What it is
The core idea.

## Why it matters
For this project AND for your ML eng career — explicitly both.

## How it works
Mechanics, math, code, or diagrams as needed.

## Watch out for
Common pitfalls and gotchas.

## See also
Links to related concepts.

## Interview angle
How this comes up in technical interviews (when relevant).
````

---

## Cross-references

Files link to each other with relative markdown links: `[other concept](../other-topic/other-concept.md)`. Whenever you mention a concept that has (or should have) its own file, link it.

---

## Maintenance protocol

This directory grows as the build progresses. Two rules:

1. **When Claude teaches a new concept in a session, the matching learning file gets written or updated in the same turn.** Not later. Things deferred to "later" get forgotten.
2. **Updates to a concept go in the file, not in chat.** If we revise our understanding of (say) Bayesian streaming, that revision lands in the file.

If a concept is missing, ask: "make a learning note on X."
