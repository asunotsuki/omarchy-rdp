# Publishing

The public repository is https://github.com/asunotsuki/omarchy-rdp.
The plugin ID is `david.rdp` and remains stable across releases.

## Release process

1. Update the version in `manifest.json` and the changelog.
2. Run the tests and build the ZIP as described in README.md.
3. Review `git diff --cached` and `git status`. Stage only project files; never
   include connection exports, the local `.qa/` directory, passwords or keyrings.
4. Commit the reviewed files and push the `main` branch. Use your normal
   Git/GitHub credentials.
5. Tag that commit `vVERSION`, push the tag, and create the matching GitHub release.
   Attach `dist/omarchy-rdp-VERSION.zip` and its `.sha256` checksum.

No remote URL is configured by the packaging script. It builds locally and
does not upload, tag, commit or publish anything.

## Subsequent versions

Update the version in `manifest.json` and the changelog, run tests, build again,
then commit/tag/publish the matching version. Omarchy's Git updater follows the
repository's default branch; release tags and ZIP downloads let users choose
an explicit version. Test changes before merging them to the default branch.

The ZIP file contains only the files explicitly listed in `package.py` and
`install.py`. Review that list when adding runtime files. The Git checkout must
also contain those files; `.gitignore` excludes local test data and JSON exports.
