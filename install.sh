#!/usr/bin/env bash
# Smart Property Manager — full installation script
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

echo "==> Step 1: Install property_core (clones repo, renames dir to apps/property_core/)"
bench get-app "$REPO_URL" --branch "$BRANCH"
# bench renames apps/Smart-Property-Manager → apps/property_core after reading setup.py

echo "==> Step 2: Install property_operations from the cloned mono-repo"
bench get-app "$(pwd)/apps/property_core/property_operations"

echo "==> Step 3: Install property_commissions from the cloned mono-repo"
bench get-app "$(pwd)/apps/property_core/property_commissions"

echo "==> Step 4: Install all three apps on site: $SITE"
bench --site "$SITE" install-app property_core
bench --site "$SITE" install-app property_operations
bench --site "$SITE" install-app property_commissions

echo "==> Step 5: Run migrations"
bench --site "$SITE" migrate

echo ""
echo "Smart Property Manager installed successfully on $SITE"
