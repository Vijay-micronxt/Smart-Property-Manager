#!/usr/bin/env bash
#
# Deploy property_core on a server -- the one way that cannot diverge.
#
# Run it from the bench directory:
#
#     cd ~/frappe-bench
#     ./apps/property_core/scripts/deploy.sh <site>
#
# Why this exists: a plain `git pull` on the server kept failing with
# "divergent branches". With developer_mode on, saving a DocType in the desk
# rewrites the app's JSON on disk; somebody commits that on the server; the
# server's branch no longer matches GitHub; the next pull stops. Each time it
# needed someone to work out by hand what the server had and whether it was
# safe to drop.
#
# This script makes GitHub the only source of truth for the code on the
# server, without losing anything:
#
#   1. fetches the branch from GitHub;
#   2. finds everything on the server that is not on GitHub -- local commits,
#      edited files, stray files -- and saves all of it to
#      drift-backups/property_core/<timestamp>/ before touching anything;
#   3. puts the app folder exactly at the GitHub commit;
#   4. shows what migrate is about to change (deploy_check), then migrates,
#      builds, clears the cache and restarts;
#   5. confirms the new code imports.
#
# Options:
#   --branch <name>             deploy another branch (default: main)
#   --check-only                stop after step 2: report drift, change nothing
#   --disable-developer-mode    also switch developer_mode off for the site
#   --no-restart                skip `bench restart` (restart by hand)
#
# Nothing it discards is lost: every backup folder holds the patches to
# re-apply and a README saying what was found.

set -euo pipefail

APP="property_core"
REPO_MATCH="Smart-Property-Manager"
BRANCH="main"
CHECK_ONLY=0
DISABLE_DEV_MODE=0
RESTART=1
SITE=""

usage() {
	sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
	exit 1
}

while [ $# -gt 0 ]; do
	case "$1" in
		--branch) BRANCH="${2:?--branch needs a name}"; shift 2 ;;
		--check-only) CHECK_ONLY=1; shift ;;
		--disable-developer-mode) DISABLE_DEV_MODE=1; shift ;;
		--no-restart) RESTART=0; shift ;;
		-h|--help) usage ;;
		-*) echo "unknown option: $1" >&2; usage ;;
		*) SITE="$1"; shift ;;
	esac
done

[ -n "$SITE" ] || usage

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[31mxx %s\033[0m\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------- preflight --
BENCH_DIR="$(pwd)"
APP_DIR="$BENCH_DIR/apps/$APP"

[ -d "$BENCH_DIR/sites" ] || die "run this from the bench directory (the one holding sites/ and apps/)"
[ -d "$APP_DIR/.git" ] || [ -f "$APP_DIR/.git" ] || die "$APP_DIR is not a git checkout"
[ -d "$BENCH_DIR/sites/$SITE" ] || die "no site '$SITE' in $BENCH_DIR/sites -- check: ls sites/"
command -v bench >/dev/null || die "bench is not on PATH"

git_app() { git -C "$APP_DIR" "$@"; }

# The remote is called origin on some servers and upstream on others; find
# the one that points at the repo instead of assuming.
REMOTE="$(git_app remote -v | awk -v m="$REPO_MATCH" '$2 ~ m && $3 == "(fetch)" { print $1; exit }')"
[ -n "$REMOTE" ] || die "no git remote points at $REPO_MATCH -- see: git -C $APP_DIR remote -v"
TARGET="$REMOTE/$BRANCH"

say "Fetching $TARGET"
git_app fetch --quiet "$REMOTE" "$BRANCH"
TARGET_SHA="$(git_app rev-parse --short "$TARGET")"
TARGET_MSG="$(git_app log -1 --format=%s "$TARGET")"
echo "   GitHub is at $TARGET_SHA  $TARGET_MSG"

# ---------------------------------------------------- an unfinished pull ----
# A pull that stopped on a conflict -- "Pulling is not possible because you
# have unmerged files", "<<<<<<< HEAD" in a DocType JSON -- leaves the
# checkout half-way through a merge or rebase. Abandoning it puts the server
# back exactly as it was before that pull, which is the state worth backing
# up below. Only a half-finished conflict resolution is dropped, never a
# commit.
GIT_DIR_ABS="$(git_app rev-parse --absolute-git-dir)"
UNFINISHED=""
[ -d "$GIT_DIR_ABS/rebase-merge" ] || [ -d "$GIT_DIR_ABS/rebase-apply" ] && UNFINISHED="rebase"
[ -z "$UNFINISHED" ] && [ -f "$GIT_DIR_ABS/MERGE_HEAD" ] && UNFINISHED="merge"
[ -z "$UNFINISHED" ] && [ -f "$GIT_DIR_ABS/CHERRY_PICK_HEAD" ] && UNFINISHED="cherry-pick"
[ -z "$UNFINISHED" ] && [ -f "$GIT_DIR_ABS/REVERT_HEAD" ] && UNFINISHED="revert"

if [ -n "$UNFINISHED" ]; then
	warn "a git $UNFINISHED stopped half-way on this server (an earlier pull hit a conflict):"
	git_app diff --name-only --diff-filter=U | sed 's/^/      conflict: /'
	if [ "$CHECK_ONLY" -eq 1 ]; then
		echo "   (check only: left as it is -- a real run abandons it first)"
	else
		git_app "$UNFINISHED" --abort
		echo "   abandoned -- the server is back where it was before that pull"
	fi
fi

# ------------------------------------------------------------------- drift --
say "Looking for changes that exist only on this server"

HEAD_SHA="$(git_app rev-parse --short HEAD)"
CURRENT_BRANCH="$(git_app rev-parse --abbrev-ref HEAD)"
LOCAL_COMMITS="$(git_app log --oneline "$TARGET..HEAD" || true)"
EDITED="$(git_app status --porcelain --untracked-files=no || true)"
UNTRACKED="$(git_app ls-files --others --exclude-standard || true)"

echo "   server is at $HEAD_SHA on branch '$CURRENT_BRANCH'"
DRIFT=0
if [ -n "$LOCAL_COMMITS" ]; then
	DRIFT=1
	warn "commits on this server that are not on GitHub:"
	echo "$LOCAL_COMMITS" | sed 's/^/      /'
fi
if [ -n "$EDITED" ]; then
	DRIFT=1
	warn "files edited on this server (developer_mode writes these when a DocType is saved in the desk):"
	echo "$EDITED" | sed 's/^/      /'
fi
if [ -n "$UNTRACKED" ]; then
	DRIFT=1
	warn "files in the app folder that are not in the repo:"
	echo "$UNTRACKED" | sed 's/^/      /' | head -40
fi
[ "$DRIFT" -eq 0 ] && echo "   none -- the server matches what it last deployed"

if [ "$DRIFT" -eq 1 ] && [ "$CHECK_ONLY" -eq 1 ]; then
	echo
	echo "   (check only: nothing saved or changed -- a real run backs all of this up first)"
elif [ "$DRIFT" -eq 1 ]; then
	STAMP="$(date +%Y%m%d-%H%M%S)"
	BACKUP="$BENCH_DIR/drift-backups/$APP/$STAMP"
	mkdir -p "$BACKUP"

	git_app rev-parse HEAD > "$BACKUP/previous_head"
	[ -n "$LOCAL_COMMITS" ] && git_app format-patch --quiet -o "$BACKUP/commits" "$TARGET..HEAD"
	[ -n "$EDITED" ] && git_app diff HEAD > "$BACKUP/uncommitted.patch"
	if [ -n "$UNTRACKED" ]; then
		( cd "$APP_DIR" && git ls-files -z --others --exclude-standard \
			| tar --null -czf "$BACKUP/untracked.tgz" -T - )
	fi

	cat > "$BACKUP/README.txt" <<EOF
Drift found on $(hostname) in $APP_DIR, $(date)
Server was at $(cat "$BACKUP/previous_head") (branch $CURRENT_BRANCH).
Deployed $TARGET = $TARGET_SHA ($TARGET_MSG).

Local commits (patches in commits/):
${LOCAL_COMMITS:-  none}

Edited files (uncommitted.patch):
${EDITED:-  none}

Untracked files (untracked.tgz):
${UNTRACKED:-  none}

Nothing here was lost -- it was moved aside so the server runs exactly what
is on GitHub. If any of it was a real fix, it belongs in a pull request:
  git -C $APP_DIR checkout -b rescue-$STAMP $TARGET
  git -C $APP_DIR am $BACKUP/commits/*.patch          # local commits
  git -C $APP_DIR apply $BACKUP/uncommitted.patch     # edited files
  tar -xzf $BACKUP/untracked.tgz -C $APP_DIR          # stray files
EOF
	echo
	echo "   saved to $BACKUP"
fi

# -------------------------------------------------------- developer mode ----
DEV_MODE="$(cd "$BENCH_DIR/sites" && python3 - "$SITE" <<'PY'
import json, sys
def read(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except Exception:
        return {}
site = read(f"{sys.argv[1]}/site_config.json")
common = read("common_site_config.json")
print(int(bool(site.get("developer_mode", common.get("developer_mode", 0)))))
PY
)"

if [ "$DEV_MODE" = "1" ]; then
	warn "developer_mode is ON for $SITE."
	warn "That is what writes desk edits into the app folder and makes every pull diverge."
	if [ "$DISABLE_DEV_MODE" -eq 1 ]; then
		[ "$CHECK_ONLY" -eq 1 ] || {
			bench --site "$SITE" set-config developer_mode 0
			echo "   switched off for $SITE"
			if grep -q '"developer_mode": *1' "$BENCH_DIR/sites/common_site_config.json" 2>/dev/null; then
				warn "common_site_config.json also has developer_mode on -- it applies to every site on this bench."
				warn "Switch it off there too if no site here is a development site: bench set-config -g developer_mode 0"
			fi
		}
	else
		warn "Switch it off: rerun with --disable-developer-mode, or: bench --site $SITE set-config developer_mode 0"
	fi
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
	say "Check only -- nothing changed"
	exit 0
fi

# ------------------------------------------------------------- put the code --
say "Putting $APP at $TARGET_SHA"
# Everything below was backed up above. Clear it first: an edited or stray
# file that GitHub also changed would otherwise stop the checkout with
# "your local changes would be overwritten" -- the same wall a pull hits.
git_app reset --quiet --hard
git_app clean --quiet -fd          # ignored files (egg-info, caches) stay
git_app checkout --quiet -f -B "$BRANCH" "$TARGET"
git_app branch --quiet --set-upstream-to="$TARGET" "$BRANCH"
git_app reset --quiet --hard "$TARGET"
echo "   now at $(git_app rev-parse --short HEAD) on '$BRANCH', working tree clean"

# ------------------------------------------------------------------ deploy --
say "What migrate is about to change"
bench --site "$SITE" execute property_core.property_core.utils.deploy_check.run || \
	warn "deploy_check could not run (first deploy of it?) -- continuing"

say "Migrating $SITE"
bench --site "$SITE" migrate

say "Building assets"
bench build --app "$APP"

say "Clearing cache"
bench --site "$SITE" clear-cache

if [ "$RESTART" -eq 1 ]; then
	say "Restarting"
	bench restart || warn "bench restart failed -- restart by hand: sudo supervisorctl restart all"
fi

# ------------------------------------------------------------------ verify --
say "Checking the new code imports"
if ! "$BENCH_DIR/env/bin/python" - <<'PY'
import importlib
for module in (
    "property_core.api.crm.session",
    "property_core.api.crm.projects",
    "property_core.property_core.crm.scope",
):
    importlib.import_module(module)
    print("   ok", module)
PY
then
	die "the code is in place but does not import -- is the app installed in this bench's env? try: bench setup requirements"
fi

say "Deployed $APP $TARGET_SHA to $SITE"
if [ "$DRIFT" -eq 1 ]; then echo "   server-only changes were saved to $BACKUP -- read its README.txt"; fi
if [ "$DEV_MODE" = "1" ] && [ "$DISABLE_DEV_MODE" -eq 0 ]; then warn "developer_mode is still on -- this will happen again until it is off"; fi
exit 0
