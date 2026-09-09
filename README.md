# quality-ratchet

Monotonic code-quality gate: six metrics (complexity, duplication, lint, tests ratio) are compared against a committed baseline, and a PR fails if any metric regresses beyond its tolerance. A single 0-100 Quality Score summarizes the baseline, anchored at 50 the day the baseline is created. The baseline never loosens on its own — the only way to accept a regression is `update --force --reason "<why>"`.

## Metrics

| metric | tool | direction | tolerance |
|---|---|---|---|
| `ccn_over_15` | lizard | lower | 0.0 |
| `max_ccn` | lizard | lower | 0.0 |
| `long_functions` | lizard | lower | 0.0 |
| `duplication_pct` | jscpd | lower | 0.1 |
| `lint_warnings` | swiftlint / eslint / ruff (configurable) | lower | 0.0 |
| `tests_per_kloc` | scc (LOC) + per-language test-function pattern | higher | 0.2 |

`direction` is "lower is better" or "higher is better"; `tolerance` is how much a metric may move against its baseline value before `check` treats it as a regression (`0.0` means any move in the wrong direction fails).

## Local install

```bash
pip install git+https://github.com/Cenadros/quality-ratchet@v0
npm install -g jscpd@4.3.0
go install github.com/boyter/scc/v3@v3.7.0
```

Pin the same `jscpd`/`scc` versions the GitHub Action uses (see `action.yml`) — `brew install scc` can resolve to a different version and shift numbers with no code change. `lizard` comes along as a Python dependency of the package above, pinned exactly (`==1.24.0`) for the same reason.

## Quickstart

```bash
quality-ratchet init
```

Commit the two files it creates, `quality-ratchet.yml` and `quality-baseline.json`. Then:

```bash
quality-ratchet check   # in PRs — exits 1 on regression
quality-ratchet update  # on main — ratchets the baseline forward on improvements
```

Editing `quality-ratchet.yml` itself (a new `exclude`, a changed threshold, a linter added/removed…) is a re-anchor event, same as a tool version bump: `update` refuses it with exit 2 unless you pass `--force --reason "<why>"`.

## Config

`quality-ratchet.yml`:

```yaml
version: 1                      # config schema version
include: [ios, android, firebase/functions/src]  # dirs/paths scanned by every collector
exclude: [build, node_modules, .build, Pods, fastlane, docs, "*.generated.*"]  # skipped everywhere (globs allowed)
tests:
  dirs: ["**/src/test/**", "**/src/androidTest/**", "**/*Tests/**", "**/*UITests/**"]  # globs that mark a file as test code (excluded from production LOC)
  patterns:                     # per-extension regex that counts as "one test function"; merged over the built-in defaults
    kt: "@Test"
    swift: "func test"
    ts: "\\b(it|test)\\("
thresholds:
  ccn: 15                       # cyclomatic complexity above which a function counts toward ccn_over_15
  function_nloc: 60             # lines-of-code above which a function counts toward long_functions
duplication:
  min_tokens: 50                # jscpd's minimum duplicated-token run to count as a clone
linters:
  swiftlint: { cwd: ios/Turnify }  # linters to run; keys must be one of swiftlint/eslint/ruff, value can set cwd/args
score:
  weights: { complexity: 0.30, duplication: 0.25, lint: 0.25, tests: 0.20 }  # group weights for the 0-100 score, must not need to sum to 1 (normalized)
```

## Score

Each metric's baseline value is anchored so its component score is 0.5 (neutral) the day the baseline is created. From there, for a metric with `initial` value:

- `lower`-is-better: `component = clamp(1 - value / (2 * initial), 0, 1)`
- `higher`-is-better: `component = clamp(value / (2 * initial), 0, 1)`

Special case when `initial == 0`: a `lower` metric stays neutral (0.5) while its value is still 0, and drops straight to 0 the moment it becomes positive — a repo that started with no linter warnings gets no free credit for having none. A `higher` metric with `initial == 0` is 1.0 as soon as its value is `> 0` (any test at all beats none).

The six components are averaged per group (`complexity`, `duplication`, `lint`, `tests`), weighted by `score.weights`, and turned into a 0-100 integer with Python's built-in `round()` — banker's rounding, so `62.5` rounds to `62`, not `63`.

`report` never writes a baseline (it's read-only, always exits 0). `check` creates the baseline on its first run in a repo. A metric that exists in the collectors but is missing from an older, already-committed baseline shows up as `new` in the table and is anchored at its current value the next time the baseline is written (by `check` on first run, or `update`).

## GitHub Action

The action only installs `quality-ratchet` itself plus `lizard`/`jscpd`/`scc` — any linter you configure under `linters:` (swiftlint, eslint, ruff…) is your responsibility to install in a prior step, exactly like any other CI dependency. `swiftlint` in particular needs a macOS runner (`runs-on: macos-latest`). Run the check on `pull_request`, never `pull_request_target`: the PR branch controls `quality-ratchet.yml` itself, and `pull_request_target` would run that (untrusted) config with write-level secrets.

```yaml
- uses: Cenadros/quality-ratchet@v0
  with:
    command: check
```

To ratchet the baseline forward on every push to `main` and commit it back:

```yaml
dogfood:
  runs-on: ubuntu-latest
  permissions:
    contents: write
  steps:
    - uses: actions/checkout@v4
    - uses: Cenadros/quality-ratchet@v0
      with:
        command: ${{ github.event_name == 'push' && 'update' || 'check' }}
    - name: Commit ratcheted baseline
      if: github.event_name == 'push'
      run: |
        if ! git diff --quiet -- quality-baseline.json; then
          git config user.name "quality-ratchet[bot]"
          git config user.email "quality-ratchet@users.noreply.github.com"
          score=$(python3 -c "import json;print(json.load(open('quality-baseline.json'))['score'])")
          git add quality-baseline.json
          git commit -m "chore(quality): baseline ↑ score ${score}"
          git pull --rebase origin main
          git push
        fi
```

## Exit codes

- `0` — no regression (or `report`/`update`, which never gate).
- `1` — `check` found at least one metric that regressed past its tolerance.
- `2` — internal error: a required tool is missing, the config or baseline is inconsistent, or an unexpected crash. Never conflates with a `1` quality regression.

## Changing tool versions

Bumping `lizard`/`jscpd`/`scc`/a linter can move the numbers with no code change. `check` warns (does not fail) when the installed tool's version differs from the one recorded in the baseline's `tool_versions`. After a deliberate bump, re-anchor explicitly:

```bash
quality-ratchet update --force --reason "bump lizard 1.17→1.18"
```

The same applies to `quality-ratchet.yml` itself: changing it is a re-anchor event, and `update` requires `--force --reason` once the config no longer matches the hash recorded in the baseline.
