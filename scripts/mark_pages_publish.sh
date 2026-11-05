#!/bin/bash
# After a successful push, record whether this commit changes the live site.
# A commit made with GITHUB_TOKEN does not start other workflows. The data job
# calls Deploy site itself when this leaves data_pushed=true.
# A later data commit replaces an earlier one. A cache-only commit leaves the
# earlier note in place.
set -eu
note="${PAGES_PUBLISH_FILE:-pages_publish.env}"
names="$(git diff-tree --root --no-commit-id --name-only -r HEAD)"
if printf '%s\n' "$names" | grep -Eq '^(data|site)/'; then
  sha="$(git rev-parse HEAD)"
  printf 'data_pushed=true\npublish_sha=%s\n' "$sha" > "$note"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    cat "$note" >> "$GITHUB_OUTPUT"
  fi
  echo "data_pushed=true"
  echo "publish_sha=$sha"
else
  echo "data_pushed=false"
fi
