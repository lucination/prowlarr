# Fork container images

The publication workflow builds this repository's backend and frontend from source
for **linux/amd64** and **linux/arm64** on separate native GitHub-hosted runners.
It does not repackage a stock Prowlarr release. Native SQLite and Mono.Unix assets,
the production web UI, and the GPL license are included.

```sh
docker run -d --name prowlarr \
  -p 127.0.0.1:9696:9696 \
  -v prowlarr-config:/config \
  ghcr.io/lucination/prowlarr:latest
```

The process runs as **9696:9696**, not root. A fresh named volume is writable;
for bind mounts the operator must prepare ownership/permissions for that UID/GID.
`/config` contains configuration, credentials, SQLite databases, and logs and must
be backed up and persisted. No authentication bypass is supplied by the image:
complete Prowlarr's normal initial authentication setup before exposing it to others.
The unauthenticated `/ping` endpoint is used only for container liveness.
The package uses Prowlarr's Docker update mechanism; replace the image to upgrade,
rather than enabling the in-app binary updater. This workflow never deploys it.

## Tags and provenance

* `latest`: most recently promoted successful current-main candidate.
* `sha-<full 40-character commit>`: immutable multi-platform publication.
* `candidate-<run>-<attempt>-<architecture>`: intermediate registry artifacts,
  not release tags; a failed job can leave these behind but cannot promote them.

`org.opencontainers.image.source` points to this fork and
`org.opencontainers.image.revision` is the exact source commit. OCI image version
is `sha-<full-commit>`, not the base operating system's inherited version.
These labels reside in each platform's image config and are checked by the native
pulled-digest smoke. Promotion does not add index annotations: the Docker manifest
list format used here does not support them. Docker media types remain enabled
to preserve and verify the shipped container healthcheck.
AssemblyVersion is
the upstream pipeline's three-component `majorVersion` plus `.0` (initially
`3.0.2.0`), deliberately not the misleading development default `10.0.0.*` and
not an invented upstream CI build number. Use the OCI revision or immutable tag
to identify fork builds; multiple fork commits can share AssemblyVersion.
Base images and external Actions are pinned by digest/SHA; update those pins
deliberately when refreshing the toolchain/security baseline.

## Publication admission

`Publish container images` listens for successful `Mirror CI` and `Sync stable
upstream` completions, plus manual dispatch on main. Forks, PRs (including a PR
whose source branch is named main), failed runs, unrelated workflows, and arbitrary
manual refs cannot publish. Only the canonical `lucination/prowlarr` main is used.
The sync workflow pushes with `GITHUB_TOKEN`, so a push-only image workflow would
silently miss scheduled sync updates. Its completion's `head_sha` is the old
control commit, not necessarily the new merge; the image workflow resolves current
main, freezes that SHA, and reruns the complete mirror validation before any
candidate image publication. A successful sync whose control SHA still equals
current main is a no-op and skips image publication, avoiding daily rebuilds of
the same immutable commit. A changed main still follows full validation and both
native build/smoke gates.

To repair a missing first publication without a new source commit, run **Publish
container images** directly with **Run workflow** on main (a successful main
**Mirror CI** manual run also remains eligible). These paths are not suppressed
by the no-op-sync check. They intentionally do not bypass immutable-tag safety:
if that SHA tag already exists with different rebuilt digests, publication fails
instead of overwriting it.

Both native jobs must build, push a candidate, pull its exact registry digest,
and pass real health/UI/authenticated API/SQLite/persistence-restart smoke before
the multi-platform index is assembled. Promotion checks the exact two digests and
platforms. An existing immutable tag with different digests fails closed instead
of being overwritten (including a nondeterministic rebuild on retry).
All publication paths share one concurrency group with `queue: max` (up to 100
pending runs), so a late old completion does not replace a newer pending run.
Immediately before changing
`latest`, promotion rereads main and withholds a stale candidate; GitHub main and
GHCR cannot be updated atomically, so a main advance during the final registry
write remains a narrow cross-service race, not a strict atomic guarantee.

No registry PAT is required: jobs use repository `GITHUB_TOKEN`, contents-read and
packages-write only in native publication/promotion jobs. **A newly created GHCR
package can initially be private even when this repository is public.** The owner
must set its package visibility to public in GitHub's package settings if needed.
Only an anonymous pull establishes public access; repository visibility and a
successful authenticated workflow do not. Link package access to this repository
if an existing package does not grant its Actions token write access.

## Local source build and acceptance

On a native amd64 or arm64 Docker host, from a clean frozen commit:

```sh
sha=$(git rev-parse HEAD)
docker build --build-arg SOURCE_REVISION="$sha" -t prowlarr:local .
python3 .github/scripts/smoke_image.py prowlarr:local "$sha" amd64
```

Use `arm64` for the final argument on ARM. The smoke test uses no external network,
creates its own disposable volume, checks the nonroot identity and source labels,
fetches compiled UI assets, proves API authentication and Docker updater policy,
writes configuration through the API, restarts, checks persistence and SQLite
integrity, then removes only its own container and volume. A sandbox where default
Docker bridge DNS is unavailable may need `docker build --network=host`; this is a
build-host workaround, not a runtime deployment setting.

To diagnose assembly compatibility without publishing any tags, use existing
registry digest references with the read-only probe:

```sh
python3 .github/scripts/check_image_assembly.py "$sha" "$amd64_digest" "$arm64_digest"
```

It runs the same assembly command as promotion with only `--dry-run` added and
verifies that the returned manifest list contains exactly those two native digests
and platforms. It reuses existing Docker credentials if needed and never logs in.
