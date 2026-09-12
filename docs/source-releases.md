# Corresponding-source releases

DocQA's original application code is GNU AGPL v3 only. `LICENSE` is the unmodified
GNU license text downloaded from <https://www.gnu.org/licenses/agpl-3.0.txt>.
`NOTICE` identifies the project and preserves third-party licensing. The public
`/about` page offers source and license downloads without an account or API access.
GitHub is project history; it is not assumed to contain uncommitted release changes.

## Prepare a release

Run from the repository root with Python 3.12. Review the working tree and the exact
path allowlist in `scripts/source-files.txt` before publication. Do not add private
configuration, keys, customer documents, operational logs or audit/planning files.

```bash
python3 scripts/build_source.py --output .release/2026-09-12-publication
export DOCQA_RELEASE_DIR="$PWD/.release/2026-09-12-publication"
```

The output must not already exist. Choose a new directory after any source edits.
The builder reads current files, including reviewed uncommitted changes. It creates
one sanitized build tree and a deterministic `.tar.gz` under `ui/public/source/` in
that tree. Both use the exact same bytes. Each archive entry has a normalized timestamp,
owner and mode; `SOURCE-MANIFEST.json` records file hashes and executable modes.
The public download filename identifies the source inventory; the public manifest
also records the archive SHA-256. No Git history or commit is required.

The allowlist includes Python application code, Alembic migrations, dependency
lockfiles, UI source/assets, scripts, tests and build/deployment instructions.
Only the reviewed `.env.example` files are included, never real `.env` files.
Dependencies are fetched from their locked upstream distributions at build time;
their own notices remain in those distributions. Font notices are also available
from About. Documents and external text corpora are runtime inputs and are excluded;
the application can be rebuilt and run with an empty database and stub providers.

New application, migration and UI build inputs cause packaging to fail until they
are explicitly reviewed and added to the allowlist. Listed symlinks, non-regular
files, prohibited paths and recognized key material fail packaging. This is a
bounded publication input list, not a substitute for reviewing the contents of
newly added files. Do not edit the prepared tree after packaging.

## Build the prepared tree

Use the source overlay **last**, with the same environment, Compose project name
and deployment overlays as the target stack:

```bash
docker compose -f docker-compose.prod.yml \
  -f deploy/docker-compose.shared-host.yml \
  -f deploy/docker-compose.source.yml build api worker beat migrate ui
```

For the bundled Caddy deployment use `deploy/docker-compose.deploy.yml` instead of
the shared-host overlay. The source overlay sends only the prepared root to the
backend build and its `ui/` subdirectory to the UI build; it also binds the prepared
migration/grant scripts. Existing `.dockerignore` rules still apply. Keep private
deployment values outside the release tree, in the original `.env` or environment.
The UI Docker build fails if the source archive is absent, corrupt or mismatched
with its UI source. Use the same final overlay when starting these built images,
following the reviewed deployment runbook; building alone does not deploy anything.

Do not reuse an older backend image with a newly packaged UI source offer. Preserve
the chosen `DOCQA_RELEASE_DIR`, Compose files and image tags for rollback as one
release. Prepare a new source tree after any code, migration, dependency or asset
change. A release directory is ignored by Git and by the root Docker context.

## Rebuild a downloaded archive

Extract the archive into an empty directory and enter `docqa/`. Follow `README.md`
for the API's local setup (`uv sync --frozen` installs the locked Python packages).
For the UI, run `npm --prefix ui ci` and `npm --prefix ui run build`; Node 22 is the
Docker build runtime. Public API URL, demo mode and accounts mode are build arguments
documented in `ui/.env.example` and the deployment overlays. Private provider and
storage credentials are operator-supplied runtime settings, not source inputs.

To build public Docker images from a downloaded archive, first run the preparation
command above from the extracted `docqa/` directory. This regenerates the offer
without recursively including the previous source archive. `npm run dev` and an
ordinary unpackaged `npm run build` remain usable locally; About honestly reports
that no corresponding-source download was packaged. Public Docker builds require it.

## Check before publication

```bash
uv run pytest tests/unit/test_source_release.py
node --test ui/tests/source-release.test.cjs
```

Build the prepared UI, then check `/about` and its archive/license links without
cookies. Verify the archive SHA-256 shown on About against the downloaded file.
Check that About remains reachable from the footer when the API/session request
fails. Confirm the home/Ask page has only the understated About link and no source
or GitHub callout. These publication checks do not certify the site's legal notices
or privacy obligations; no postal address has been supplied or invented.
