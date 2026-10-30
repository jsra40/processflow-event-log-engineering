# Publication review checklist

## Technical checks (performed on this release candidate)

- [x] Built from the generalized enterprise-demo package, not the original institutional ZIP.
- [x] Excluded `output/`, `secure_local/`, `input/`, `.venv/`, caches and local logs.
- [x] Checked included text files for common institutional/clinical terms and common credential patterns; see `RELEASE_AUDIT.md`.
- [x] 34 automated tests passed.
- [x] Clean synthetic scenario: 1,000 cases, 7,716 events, quality PASS.
- [x] Invalid synthetic scenario: 1,000 cases, 7,714 events, quality FAIL.

## Human review required before public upload

- [ ] Confirm you have the rights to publish and license the underlying source code under your employment or other agreements.
- [ ] Manually inspect all source code, documentation, examples and configurations for nonpublic business logic or identifying details.
- [ ] Inspect any screenshots and exported reports separately before committing them.
- [ ] Decide whether to add a LICENSE file and which license is appropriate.
- [ ] Review third-party dependency licenses and security posture.
- [ ] Create a **new, empty** repository; do not import private Git history.
- [ ] Check `git status` and `git diff --cached --name-only` before the first commit.
- [ ] Confirm that no local `output/`, `secure_local/`, real input files or `.env` files are staged.

**Never treat a text scan as proof that a repository contains no confidential information.**
