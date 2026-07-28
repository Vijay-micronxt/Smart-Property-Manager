#!/usr/bin/env bash
# Smart Property Manager — install all three Frappe apps
#
# Run from inside your frappe-bench directory:
#   cd /home/frappe/frappe-bench
#   bash <(curl -s https://raw.githubusercontent.com/Vijay-micronxt/Smart-Property-Manager/fix/property-manager-bugs/install.sh) mysite.local

set -euo pipefail

SITE="${1:-}"
if [ -z "$SITE" ]; then
    echo "Usage: bash install.sh <site-name>"
    echo "Example: bash install.sh mysite.local"
    exit 1
fi

BRANCH="${BRANCH:-fix/property-manager-bugs}"
REPO_URL="https://github.com/Vijay-micronxt/Smart-Property-Manager.git"
SRC_DIR="/tmp/smart-property-manager-src"

echo "==> Cloning Smart-Property-Manager to $SRC_DIR ..."
rm -rf "$SRC_DIR"
git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$SRC_DIR"

echo "==> Installing property_core ..."
bench get-app "$SRC_DIR/property_core"

echo "==> Installing property_operations ..."
bench get-app "$SRC_DIR/property_operations"

echo "==> Installing property_commissions ..."
bench get-app "$SRC_DIR/property_commissions"

echo "==> Installing apps on site: $SITE"
bench --site "$SITE" install-app property_core
bench --site "$SITE" install-app property_operations
bench --site "$SITE" install-app property_commissions

echo "==> Running migrations ..."
bench --site "$SITE" migrate

echo ""
echo "Smart Property Manager installed on $SITE"
echo "You can remove the source clone: rm -rf $SRC_DIR"
