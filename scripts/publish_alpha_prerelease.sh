#!/bin/bash
set -euo pipefail

TAG="v0.1.0-alpha.1"
REPOSITORY="opswitness/opswitness"
PUBLISH_BRANCH="codex/opswitness-alpha-release"
DMG_NAME="OpsWitness-0.1.0-alpha.1-macos-arm64.dmg"
WHEEL_NAME="opswitness-0.1.0a1-py3-none-any.whl"
SDIST_NAME="opswitness-0.1.0a1.tar.gz"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DMG_SOURCE="/private/tmp/opswitness-hidden-ui-dmg.PwrQbm"
MACOS_DIST="$REPO_ROOT/dist/macos"
PYTHON_DIST="$REPO_ROOT/dist/knowledge-hub"
FINAL_DMG="$MACOS_DIST/$DMG_NAME"
CANDIDATE_DMG="$MACOS_DIST/OpsWitness-0.1.0-alpha.1-macos-arm64-provider-hidden.dmg"
CHECKSUMS="$MACOS_DIST/SHA256SUMS"
RELEASE_NOTES="$MACOS_DIST/PRERELEASE-NOTES.md"
GH="/opt/homebrew/bin/gh"
RESUMABLE_DMG_SHA="4d1dbd8694ce487d76dadcc573f1c70e1df0d1dcce7100bc46acfaebb8c54956"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

sha256_of() {
  /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

cd "$REPO_ROOT"

test -x "$GH" || fail "GitHub CLI was not found at $GH"
"$GH" auth status -h github.com

test -d "$DMG_SOURCE/OpsWitness.app" || fail "prepared provider-hidden App is missing"
test -L "$DMG_SOURCE/Applications" || fail "Applications link is missing from the DMG source"
test "$(readlink "$DMG_SOURCE/Applications")" = "/Applications" ||
  fail "Applications link has an unexpected target"
test -f "$PYTHON_DIST/$WHEEL_NAME" || fail "wheel is missing"
test -f "$PYTHON_DIST/$SDIST_NAME" || fail "source distribution is missing"
test -f "$RELEASE_NOTES" || fail "prerelease notes are missing"

/usr/bin/codesign --verify --strict "$DMG_SOURCE/OpsWitness.app"

if test -f "$FINAL_DMG" && test "$(sha256_of "$FINAL_DMG")" = "$RESUMABLE_DMG_SHA"; then
  printf 'Resuming with the already verified provider-hidden DMG.\n'
  /usr/bin/hdiutil verify "$FINAL_DMG"
  /usr/bin/codesign --verify --strict "$FINAL_DMG"
else
  /usr/bin/hdiutil create \
    -ov \
    -volname OpsWitness \
    -srcfolder "$DMG_SOURCE" \
    -format UDZO \
    "$CANDIDATE_DMG"
  /usr/bin/hdiutil verify "$CANDIDATE_DMG"
  /usr/bin/codesign --force --sign - --timestamp=none "$CANDIDATE_DMG"
  /usr/bin/codesign --verify --strict "$CANDIDATE_DMG"

  if test -f "$FINAL_DMG"; then
    OLD_SHA="$(sha256_of "$FINAL_DMG")"
    BACKUP_DMG="$MACOS_DIST/${DMG_NAME%.dmg}.stale-${OLD_SHA:0:12}.dmg"
    if test ! -f "$BACKUP_DMG"; then
      mv "$FINAL_DMG" "$BACKUP_DMG"
    else
      mv "$FINAL_DMG" "$MACOS_DIST/${DMG_NAME%.dmg}.stale-$(date -u +%Y%m%dT%H%M%SZ).dmg"
    fi
  fi
  mv "$CANDIDATE_DMG" "$FINAL_DMG"
  /usr/bin/hdiutil verify "$FINAL_DMG"
  if test "$(sha256_of "$FINAL_DMG")" != "$RESUMABLE_DMG_SHA"; then
    printf 'New DMG SHA-256: %s\n' "$(sha256_of "$FINAL_DMG")"
  else
    printf 'DMG matches the resumable release candidate.\n'
  fi
fi

CHECKSUMS_TMP="$CHECKSUMS.tmp"
{
  printf '%s  %s\n' "$(sha256_of "$FINAL_DMG")" "$DMG_NAME"
  printf '%s  %s\n' "$(sha256_of "$PYTHON_DIST/$WHEEL_NAME")" "$WHEEL_NAME"
  printf '%s  %s\n' "$(sha256_of "$PYTHON_DIST/$SDIST_NAME")" "$SDIST_NAME"
} | LC_ALL=C sort -k2 > "$CHECKSUMS_TMP"
mv "$CHECKSUMS_TMP" "$CHECKSUMS"

git add -A
git diff --cached --check
"$REPO_ROOT/.venv/bin/python" scripts/verify_distribution.py "$PYTHON_DIST"

if ! git diff --cached --quiet; then
  git commit -s -m "release: prepare v0.1.0-alpha.1"
fi

COMMIT_SHA="$(git rev-parse HEAD)"
git push -u origin "HEAD:refs/heads/$PUBLISH_BRANCH"

if "$GH" release view "$TAG" --repo "$REPOSITORY" >/dev/null 2>&1; then
  IS_PRERELEASE="$("$GH" release view "$TAG" --repo "$REPOSITORY" --json isPrerelease --jq .isPrerelease)"
  test "$IS_PRERELEASE" = "true" || fail "existing $TAG release is not a prerelease"
  "$GH" release edit "$TAG" \
    --repo "$REPOSITORY" \
    --title "OpsWitness v0.1.0-alpha.1" \
    --notes-file "$RELEASE_NOTES" \
    --prerelease
  "$GH" release upload "$TAG" \
    --repo "$REPOSITORY" \
    --clobber \
    "$FINAL_DMG" \
    "$CHECKSUMS" \
    "$PYTHON_DIST/$WHEEL_NAME" \
    "$PYTHON_DIST/$SDIST_NAME"
else
  "$GH" release create "$TAG" \
    --repo "$REPOSITORY" \
    --target "$PUBLISH_BRANCH" \
    --title "OpsWitness v0.1.0-alpha.1" \
    --notes-file "$RELEASE_NOTES" \
    --prerelease \
    "$FINAL_DMG" \
    "$CHECKSUMS" \
    "$PYTHON_DIST/$WHEEL_NAME" \
    "$PYTHON_DIST/$SDIST_NAME"
fi

"$GH" release view "$TAG" \
  --repo "$REPOSITORY" \
  --json url,tagName,isPrerelease,publishedAt,assets \
  --jq '{url,tagName,isPrerelease,publishedAt,assets:[.assets[].name]}'

printf '\nPublished commit: %s\n' "$COMMIT_SHA"
printf 'DMG SHA-256: %s\n' "$(sha256_of "$FINAL_DMG")"
