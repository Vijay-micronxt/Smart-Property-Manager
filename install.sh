#!/usr/bin/env bash
# Smart Property Manager — full installation script
# Usage: bash install.sh <site-name>
# Example: bash install.sh mysite.local
#
# Run this from inside your frappe-bench directory:
#   cd /home/frappe/frappe-bench
#   bash apps/Smart-Property-Manager/install.sh mysite.local

set -euo pipefail

SITE="${1:-}"
if [ -z "$SITE" ]; then
    echo "Usage: bash install.sh <site-name>"
    echo "Example: bash install.sh mysite.local"
    exit 1
fi

BENCH_DIR="$(pwd)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing property_core ..."
bench get-app "$REPO_DIR/property_core"

echo "==> Installing property_operations ..."
bench get-app "$REPO_DIR/property_operations"

echo "==> Installing property_commissions ..."
bench get-app "$REPO_DIR/property_commissions"

echo "==> Installing apps on site: $SITE"
bench --site "$SITE" install-app property_core
bench --site "$SITE" install-app property_operations
bench --site "$SITE" install-app property_commissions

echo "==> Running migrations ..."
bench --site "$SITE" migrate

echo ""
echo "✓ Smart Property Manager installed successfully on $SITE"
