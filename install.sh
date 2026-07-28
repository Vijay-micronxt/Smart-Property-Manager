#!/usr/bin/env bash
# Smart Property Manager — install all three Frappe apps
#
# Usage (run as frappe user or with sudo from inside frappe-bench):
#   cd /home/frappe/frappe-bench
#   sudo bash /tmp/spm_install.sh mysite.local
#
# Or one-liner (run as frappe user):
#   curl -s https://raw.githubusercontent.com/Vijay-micronxt/Smart-Property-Manager/fix/property-manager-bugs/install.sh -o /tmp/spm_install.sh
#   sudo bash /tmp/spm_install.sh mysite.local

set -euo pipefail

SITE="${1:-}"
if [ -z "$SITE" ]; then
    echo "Usage: bash install.sh <site-name>"
    echo "Example: sudo bash install.sh mysite.local"
    exit 1
fi

# Auto-detect bench directory (default: /home/frappe/frappe-bench)
BENCH_DIR="${BENCH_DIR:-/home/frappe/frappe-bench}"
BRANCH="${BRANCH:-fix/property-manager-bugs}"
REPO_URL="https://github.com/Vijay-micronxt/Smart-Property-Manager.git"
SRC_DIR="/tmp/smart-property-manager-src"

PYTHON="$BENCH_DIR/env/bin/python"
PIP="$BENCH_DIR/env/bin/pip"

echo "==> Cloning Smart-Property-Manager ..."
rm -rf "$SRC_DIR"
git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$SRC_DIR"

for APP in property_core property_operations property_commissions; do
    echo "==> Setting up $APP ..."

    # Remove any previous failed install
    rm -rf "$BENCH_DIR/apps/$APP"

    # Copy the app folder into bench's apps directory
    cp -r "$SRC_DIR/$APP" "$BENCH_DIR/apps/$APP"

    # Install the Python package into bench's virtualenv
    "$PIP" install --quiet --upgrade -e "$BENCH_DIR/apps/$APP"
done

echo "==> Building frontend assets ..."
cd "$BENCH_DIR"
bench build

echo "==> Installing apps on site: $SITE ..."
bench --site "$SITE" install-app property_core
bench --site "$SITE" install-app property_operations
bench --site "$SITE" install-app property_commissions

echo "==> Running migrations ..."
bench --site "$SITE" migrate

echo ""
echo "Smart Property Manager installed on $SITE"
rm -rf "$SRC_DIR"
