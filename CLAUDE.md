# User-wide instructions

## Git branching

When starting work on a new feature or fix in a git repository, if the current
branch is the default branch (`main` or `master`), create a new branch off it
**before making any edits** — do not edit or commit directly on the default branch.

- Features: `feature/<short-kebab-slug>`
- Fixes: `fix/<short-kebab-slug>`

Still only push or open PRs when explicitly asked; creating the local branch up
front is the only proactive step.

## Test if the command start with claude-secure
Always test on the session startup if there is any environment variable injected to the session, if not this is high possibility that session start with `claude` not `claude-secure`, immediately alert this to user and ask to restart the session with `claude-secure`.

## Syncing skills, MCPs, and this file to the kana-skills repo

The `kana-skills` repo (`~/dev/kana-skills`) is the canonical collection of my Claude
skills, slash commands, and MCP servers.

- Whenever a skill, slash command, or MCP server is **created, updated, or deleted**
  (anywhere — `~/.claude`, a project, or Claude Desktop), **ask whether the change should
  be propagated to the kana-skills repo.**
- Whenever **this CLAUDE.md** is updated, **ask the same** — its copy lives at the repo root.

Just ask; don't sync or push automatically. Respect any artifact marked to keep private.