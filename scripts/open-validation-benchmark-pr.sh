#!/usr/bin/env bash
# Create a pull request for validation/benchmarking documentation split and
# benchmark_matrix.py. Run from repository root in WSL/Linux:
#
#   chmod +x scripts/open-validation-benchmark-pr.sh
#   ./scripts/open-validation-benchmark-pr.sh
#
# Prerequisites:
#   - git remote pointing at GitHub (origin)
#   - gh auth login  (https://cli.github.com/)
#   - clean intent to open PR into main (edit BASE_BRANCH below if needed)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASE_BRANCH="${BASE_BRANCH:-main}"
FEATURE_BRANCH="${FEATURE_BRANCH:-docs/validation-benchmark-split}"

PR_FILES=(
  README.md
  CHANGELOG.md
  CONTRIBUTING.md
  CHECKLIST.md
  MAINTENANCE.md
  docs/validation.md
  docs/benchmarking.md
  docs/appendix_b_verification.md
  examples/benchmark_matrix.py
)

echo "Repository: $REPO_ROOT"
echo "Base branch: $BASE_BRANCH"
echo "Feature branch: $FEATURE_BRANCH"
echo

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI (gh) is not installed."
  echo "Install: https://cli.github.com/  then run: gh auth login"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated. Run: gh auth login"
  exit 1
fi

git fetch origin "$BASE_BRANCH"

if git show-ref --verify --quiet "refs/heads/$FEATURE_BRANCH"; then
  echo "Checking out existing branch $FEATURE_BRANCH"
  git checkout "$FEATURE_BRANCH"
else
  echo "Creating branch $FEATURE_BRANCH from origin/$BASE_BRANCH"
  git checkout -b "$FEATURE_BRANCH" "origin/$BASE_BRANCH"
fi

missing=0
for f in "${PR_FILES[@]}"; do
  if [[ ! -e "$f" ]]; then
    echo "MISSING: $f"
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

git add "${PR_FILES[@]}"

if git diff --cached --quiet; then
  echo "No staged changes — nothing to commit. Files may already be committed on this branch."
else
  git commit -m "$(cat <<'EOF'
docs: separate validation from TSNet performance benchmarking

Split correctness documentation (validation.md) from performance studies
(benchmarking.md), restructure README sections, and add a multi-case
benchmark_matrix.py script for reproducible TSNet timing comparisons.
EOF
)"
fi

echo "Pushing $FEATURE_BRANCH to origin …"
git push -u origin "$FEATURE_BRANCH"

gh pr create \
  --base "$BASE_BRANCH" \
  --head "$FEATURE_BRANCH" \
  --title "docs: separate validation from performance benchmarking" \
  --body "$(cat <<'EOF'
## Summary

- Split **validation** (solver correctness) from **benchmarking** (wall-clock speed vs TSNet).
- Added `docs/validation.md` with the regression test map, tolerance policy, and reference artifacts.
- Rewrote `docs/benchmarking.md` to focus on TSNet performance reproduction.
- Restructured README **Validation** and **Benchmarking** sections (concise summary + links).
- Added `examples/benchmark_matrix.py` to sweep time step / duration and print a timing table.

## Motivation

RTHYM-MOC’s value proposition has two parts: a **validated** MOC implementation and a **much faster** core than pure-Python TSNet. Keeping those stories separate makes reviews and CI scope clearer.

## Test plan

- [ ] `pytest -q` (validation regressions unchanged)
- [ ] `python examples/benchmark_vs_tsnet.py` (optional; requires `pip install tsnet==0.3.1`)
- [ ] `python examples/benchmark_matrix.py` (optional; same TSNet dependency)
- [ ] Read through README Validation / Benchmarking sections for broken links

## Notes

- TSNet remains an optional dependency; not added to default CI.
- Re-run `benchmark_matrix.py` on target hardware before citing speedup ratios in papers or release notes.
EOF
)"

echo
echo "Done. PR URL should be printed above."
