# Deploying property_core

One command, from the bench directory:

```bash
cd ~/frappe-bench
./apps/property_core/scripts/deploy.sh <site>
```

That is the whole deploy. **Do not `git pull` in the app folder by hand.**

---

## Why not `git pull`

A pull on the server kept stopping with *"You have divergent branches"*. The
cause is always the same:

1. `developer_mode` is on for the live site.
2. Someone saves a DocType in the desk. With developer mode on, Frappe writes
   that change **into the app's JSON files on disk**, not just the database —
   even a harmless save rewrites `modified` and `modified_by`.
3. Someone commits that on the server.
4. The server's branch now has a commit GitHub does not, and every pull after
   that needs a person to work out what the server has and whether it is safe
   to drop.

## What the script does instead

1. Fetches the branch from GitHub. The remote is found by URL, so it works
   whether the server calls it `origin` or `upstream`.
2. Lists everything on the server that is not on GitHub — local commits, edited
   files, stray files such as an exported `fixtures/` folder — and **saves all
   of it** to `drift-backups/property_core/<timestamp>/` before touching
   anything. Each backup has a `README.txt` saying what was found and how to put
   it back.
3. Puts the app folder exactly at the GitHub commit.
4. Prints what `migrate` is about to change (`deploy_check`), then runs
   migrate, build, clear-cache and restart.
5. Checks the new code actually imports.

GitHub is the only source of truth for the code on the server. Nothing the
server had is lost — it is moved aside where it can be read, and turned into a
pull request if it was a real fix.

## Options

| | |
|---|---|
| `--check-only` | report what is different on the server and stop — changes nothing |
| `--disable-developer-mode` | also switch `developer_mode` off for the site |
| `--branch <name>` | deploy a branch other than `main` |
| `--no-restart` | skip `bench restart` |

Not sure what the server has? Run `--check-only` first; it is safe any time.

## Switch developer mode off on production

This is what stops the drift at the source. Once, on the live site:

```bash
./apps/property_core/scripts/deploy.sh <site> --disable-developer-mode
```

or by hand: `bench --site <site> set-config developer_mode 0 && bench restart`.

After that, change fields through **Customize Form**, never by editing a
DocType. Customize Form keeps the change in the database (Property Setters and
Custom Fields), survives every deploy, and never touches the app folder.

If a change really belongs in the app — a new field every site should have —
make it on a development bench, commit it, and open a pull request.

## The first time on a server that has already diverged

The script comes with the code, so a server that cannot pull yet does not have
it. Fetch works even when pull does not; run the script straight out of the
fetched commit:

```bash
cd ~/frappe-bench
git -C apps/property_core fetch upstream        # or origin -- see: git -C apps/property_core remote -v
git -C apps/property_core show upstream/main:scripts/deploy.sh > /tmp/deploy.sh
bash /tmp/deploy.sh <site> --check-only         # look first
bash /tmp/deploy.sh <site> --disable-developer-mode
```

From then on the script is in the app folder and the one-line command above is
all a deploy takes.

## After a deploy that added roles

Migrate creates roles; it never gives them to anyone. For the CRM hierarchy,
each person needs one of Property Manager, Property Sales Manager or Property
Sales Executive, and an Employee record with `user_id` set and `reports_to`
pointing at their manager.
