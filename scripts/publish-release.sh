#!/usr/bin/env bash
# Push a version tag to GitHub. The "Release" workflow builds the binary and
# creates the GitHub Release — no gh CLI required.
#
# Usage:
#   ./scripts/publish-release.sh 1.2.3
#   ./scripts/publish-release.sh v1.2.3
#   ./scripts/publish-release.sh --dry-run 1.2.3
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRY=0
while [[ "${1:-}" == "--dry-run" ]]; do
  DRY=1
  shift
done

VERSION_RAW="${1:-}"
if [[ -z "$VERSION_RAW" ]]; then
  echo "Usage: $0 [--dry-run] <version>   e.g. 1.2.3 or v1.2.3" >&2
  exit 1
fi

VERSION="${VERSION_RAW#v}"
TAG="v${VERSION}"

if [[ "$DRY" -eq 1 ]]; then
  echo "Would run: git tag -a \"$TAG\" -m \"Release $TAG\""
  echo "Would run: git push origin \"$TAG\""
  exit 0
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "error: tag $TAG already exists" >&2
  exit 1
fi

git tag -a "$TAG" -m "Release $TAG"
git push origin "$TAG"
echo "Pushed $TAG — open the repo’s Actions tab, then Releases, for the build."
