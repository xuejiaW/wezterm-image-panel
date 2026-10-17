# First GitHub upload

This project can be published as its own repository. Do not upload the entire
parent Projects directory or a folder archive containing `.codex-local/`.
Suggested repository name: **wezterm-image-panel**. Publish an empty repository
first if you intend to push this existing checkout, without generating another
README or license on GitHub.

## Configure a public commit identity

Before making the first commit, set the identity for this repository locally.
Replace the placeholders with your public name and GitHub-provided noreply
address, available in your GitHub email settings:

```sh
git config --local user.name "YOUR_PUBLIC_NAME"
git config --local user.email "YOUR_GITHUB_NOREPLY_EMAIL"
```

This avoids inheriting a work identity from global Git configuration. Do not
put access tokens or passwords in a remote URL or in source files.

## Review the actual upload set

```sh
python -m unittest discover -v
python scripts/check_release.py
git status --short
git diff --cached --stat
```

Only source, documentation, examples, tests, and repository configuration
should be included. `.codex-local/` holds private local material and must stay
out of Git. Do not use a forced add to bypass that boundary.

After reviewing the staged files, create a commit and push it to the repository
you create on GitHub. No remote account, repository, or upload is created by
the setup scripts. Use SSH or your own Git credential manager to authenticate.

Before a tagged release, complete the manual Windows/macOS checklist in
[VALIDATION.md](../VALIDATION.md) and check the hosted Actions results. A source
upload can describe GUI validation as pending; it should not claim a verified
cross-platform release.
