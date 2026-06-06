# Python Version Management on macOS

**TL;DR:** A modern Mac often has 5+ Python installs simultaneously (system, Xcode CLT, Homebrew, MacPorts, Anaconda, python.org). Plain `python3` resolves to whichever one comes first in `PATH` — often the wrong one. **Always create venvs with an explicit minor-version binary like `python3.13`.**

---

## What it is

macOS does not ship with a "user" Python. Every Python on your Mac was installed by some tool: Xcode Command Line Tools, Homebrew, MacPorts, Anaconda/Miniconda, the python.org installer, asdf, pyenv, uv. Each one drops a `python3` symlink in its bin directory and prepends that directory to your `PATH` via your shell rc files.

The result is that `which python3` depends on `PATH` order, which depends on the order of `eval` statements and `export PATH=...` lines in `~/.zshrc`, `~/.zprofile`, `/etc/paths.d/*`, etc. The Python that "wins" is often not the newest one — often it's the **first one you installed years ago**.

In this project we discovered `python3` was Anaconda's Python 3.8.10, which was released in May 2021 and hit end-of-life in October 2024 — past EOL.

---

## Why it matters

**For the project:** Code that uses any post-3.8 feature (PEP 604 `int | None`, `from datetime import UTC`, dict-union `d1 | d2`, walrus in comprehensions, `tomllib`, etc.) will silently break on the wrong interpreter.

**For ML engineering jobs:** Production training environments are containerized (Docker, conda) specifically to avoid this. Knowing how to:

- Spot the version drift symptom (`SyntaxError` or `AttributeError: module 'datetime' has no attribute 'UTC'`)
- Audit the available Pythons on a machine
- Pin the version explicitly in `pyproject.toml` / Dockerfile
- Use the right interpreter for venv creation

is a baseline competence for ML eng work.

---

## How to audit your Pythons

```bash
# Where do all the "python3" symlinks live?
type -a python3
ls -la /opt/homebrew/bin/python3* 2>/dev/null
ls -la /usr/local/bin/python3* 2>/dev/null
ls -la /usr/bin/python3* 2>/dev/null
ls -la ~/opt/anaconda3/bin/python3* 2>/dev/null
ls -la /Library/Frameworks/Python.framework/Versions/*/bin/python3* 2>/dev/null

# What version does each minor binary point to?
for v in 3.9 3.10 3.11 3.12 3.13 3.14; do
    command -v python$v && python$v --version
done
```

You'll often discover 4+ Pythons installed. Pick the newest stable one and use **the explicit binary** for venv creation.

---

## The rule

Whenever you create a venv:

```bash
python3.13 -m venv .venv     # ✅ explicit minor version
python3 -m venv .venv        # ❌ depends on PATH order — surprises
```

Whenever you run something globally (where you're not in a venv):

```bash
python3.13 -m pip install ...   # ✅ explicit
python3 -m pip install ...      # ❌ which interpreter again?
```

---

## Why we picked 3.13 here

The user had 3.8, 3.11, 3.13, and 3.14 installed. We chose 3.13 because:

- **3.13** is the current stable release — mature, well-tested, broad library support.
- **3.14** is too new (~2 months old as of mid-2026) — some C-extension libraries may not have wheels yet. Wait 6–9 months before standardizing on a brand-new major.
- **3.11** would work but misses some niceties like the improved error messages introduced in 3.12/3.13.

**Rule of thumb for ML projects:** target one minor version behind the latest (`latest - 1`). You get modern features without bleeding-edge breakage.

---

## Watch out for

- **Anaconda's `conda activate` rewrites your PATH** — even if you set up Homebrew first, activating a conda env shadows it. If you're confused why `python3` is suddenly old, check if a conda env is active.
- **`/usr/bin/python3` is sometimes a stub** that prompts you to install Xcode CLT. It can also be outdated. Don't rely on it.
- **VS Code Python extension picks up whatever's in PATH** unless you point it at a venv explicitly. Use the "Select Interpreter" command and pick `.venv/bin/python`.
- **`pyenv install 3.13` followed by `pyenv global 3.13`** is the cleanest approach if you want a single "current" version. But many people don't use pyenv.
- **CI surprise:** if your CI machine has a different default Python than yours, tests pass locally and fail in CI. Pin Python version in CI config explicitly.

---

## In ML eng work, you'll also encounter:

- **`uv` (recommended modern tool):** does venv + dep resolution + version selection in one binary. `uv venv --python 3.13 .venv` makes the version-picking explicit and automatic.
- **`conda` envs:** required for some packages that need compiled C libraries (PyTorch with specific CUDA versions, MKL, etc.). Slower than pip, fewer surprises for the GPU stack.
- **Docker:** the production answer. `FROM python:3.13-slim` in your Dockerfile pins the version and isolates from the host. ML training pipelines in production are almost always containerized.

---

## See also

- [Dependency management](dependency-management.md)
- [Reproducible pipelines](../ml-engineering/reproducible-pipelines.md) — environment versioning is one of the three pillars

---

## Interview angle

> **"Walk me through how you set up a Python environment for a new project."**

A senior answer covers:

1. Pick the Python minor version intentionally (latest stable, often `latest - 1` for ML libs)
2. Create the venv with the explicit binary (`python3.13 -m venv` not `python3 -m venv`)
3. Pin runtime deps with version bounds, dev deps separately
4. Lock the transitive tree (lockfile)
5. For production, containerize with explicit base image
6. Document the environment in README so contributors don't reproduce your `~/.zshrc` accidentally

Bonus: explain why you'd reach for `uv` / `conda` / `docker` in different scenarios.
