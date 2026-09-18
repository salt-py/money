# CLAUDE

- Do NOT under any circimstance leak any of my banking information into Claude, at all times we should write a script, keep data local etc
- Do not add Claude co-authorship/attribution lines (e.g. "Co-Authored-By: Claude...", "Generated with Claude Code") to git commit messages or PR descriptions.
- **This repo's GitHub account is `salt-py`.** `gh`'s active account is one
  global toggle shared by every terminal/session on this machine, not
  scoped per-project -- another session working in a different repo
  (e.g. under the `saltpy-mv` account) can and will silently flip it back.
  Before running *any* `gh` command here (`gh api`, `gh pr`, `gh repo`,
  `gh run`, etc.), first run `gh auth switch --hostname github.com --user
  salt-py` and don't assume the account left active from earlier in the
  conversation is still correct -- verify with `gh auth status` if in
  doubt. Plain `git push`/`pull` are unaffected by this (the remote uses a
  dedicated SSH host alias, `git@gh-salt-py:...`, not gh's credential
  helper) -- this only matters for `gh` subcommands that hit the API.