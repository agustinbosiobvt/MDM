#!/bin/sh
# Prove the built production images contain no trace of the e2e mock Google.
set -eu
for image in ${IMAGES:-bvt-mdm-api bvt-mdm-web}; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "check_images: $image not built yet (run make up first)" >&2
    exit 1
  fi
  found=$(docker run --rm --entrypoint sh "$image" -c \
    "grep -rIl --exclude-dir=proc --exclude-dir=sys --exclude-dir=dev 'mock_oidc\|mock-oidc' /srv /usr/share/nginx /etc/nginx 2>/dev/null; find / -xdev -name 'mock_oidc*' 2>/dev/null" || true)
  if [ -n "$found" ]; then
    echo "check_images: mock found in $image:" >&2
    echo "$found" >&2
    exit 1
  fi
  echo "check_images: $image is clean"
done
