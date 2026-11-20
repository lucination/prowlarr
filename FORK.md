## Automatic container publication

This fork builds native amd64/arm64 images at `ghcr.io/lucination/prowlarr` after
successful main CI or stable-upstream sync, with `latest` and immutable
`sha-<full-commit>` tags. See [container usage and publication policy](distribution/docker/README.md)
for nonroot `/config` persistence, source provenance, native runtime gates, and
the owner-controlled GHCR public-visibility prerequisite. Publication is not deployment.

# Customized mirror: optional Usenet redirect

This is a customized mirror of [Prowlarr](https://github.com/Prowlarr/Prowlarr), not an official Prowlarr release. The upstream copyright notices and GPL-3.0 license in `LICENSE` continue to apply, including obligations when distributing binaries or source to others.

## Use

In an indexer's settings, turn off **Redirect** to have Prowlarr fetch the NZB and return it to the requesting client as `application/x-nzb`, with the requested `.nzb` filename. Leave Redirect enabled for the existing direct-to-indexer behavior. Existing saved settings are respected; new Usenet indexers retain upstream's enabled default. Torrent downloads and magnet handling are unchanged. This affects the Newznab download endpoint; it does not rewrite upstream indexer URLs or override provider authentication and download errors.

Redirect requires both `SupportsRedirect` and the saved `Redirect` flag, consistently for both protocols. Usenet providers that do not support redirect (including BinSearch, NzbIndex and Headphones) now return fetched NZBs through this endpoint even if an older saved flag is true; they are no longer forcibly redirected. This is an intentional part of removing forced Usenet redirects, consistent with the existing client-side download path. No existing flags or history migration are rewritten. Upstream HTTP redirect following inside indexer downloads is unchanged.

## Validation and upstream maintenance

Pushes and pull requests run `.github/scripts/validate.sh`. It runs local-repository synchronization fixtures, builds the API and executes the complete API test project, including settings validation and download controller behavior tests. It also runs the core Download tests, including existing client provider/status tests and Usenet client proxy-versus-link regression tests. It is not a full upstream-suite, frontend, packaging or all-platform release pipeline.

The scheduled workflow runs daily and can also be started with **Run workflow**. It tracks upstream **master**, not develop. A candidate worktree merges upstream into the current mirror main, then runs the same validation before publishing anything. Normal feature development uses rebased, fast-forward commits. Upstream synchronization is the narrow exception: a merge commit preserves both complete upstream ancestry and customization history without rewriting main.

An unchanged upstream does nothing. Merge conflicts, failing validation, or a changed main tip fail the workflow without publishing the candidate. A pre-push expected-tip guard and Git's receive-side old-tip check prevent stale publication; pushes are never forced. Failures are visible in Actions and require manual resolution. The script verifies the published tip after pushing. A simultaneous later update can cause that verification to fail even if the sync itself was published.

The sync job uses only its repository-scoped `GITHUB_TOKEN` with contents write permission; ordinary CI is read-only and receives no application secrets. The token's push does not trigger another push workflow, so candidate validation is intentionally performed inside the sync job. A successful changed sync also triggers the separately gated container-publication workflow described above; unchanged syncs skip image publication. Container publication is enabled, but release creation and deployment are not. GitHub Actions must be enabled for this repository, and branch rules must permit the synchronization job to fast-forward main; protection that requires PRs will intentionally block direct sync publication. Scheduled workflows run from the default branch, so set it to main.

Upstream issue-labeling, issue-closing and locking workflows are removed from this mirror. If upstream later changes those deleted files, a sync may conflict rather than silently enabling repository automation.

## Local commands

Install the SDK specified in `global.json`, Python 3, Git and the normal .NET OS dependencies (including ICU on Linux). From the repository root:

```sh
bash .github/scripts/validate.sh
```

Synchronization publishes main, so do not invoke it as a read-only check. It requires a clean checkout and a configured `origin` with a main branch. Its fixture suite uses only temporary local repositories and makes no network requests:

```sh
python3 .github/scripts/test_upstream_sync.py
```
