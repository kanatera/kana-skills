# User-wide instructions

## Git branching

When starting work on a new feature or fix in a git repository, if the current
branch is the default branch (`main` or `master`), create a new branch off it
**before making any edits** — do not edit or commit directly on the default branch.

- Features: `feature/<short-kebab-slug>`
- Fixes: `fix/<short-kebab-slug>`

Still only push or open PRs when explicitly asked; creating the local branch up
front is the only proactive step.

## Test if the command start with git-secure
Always test on the session startup if there is any environment variable injected to the session, if not this is high possibility that session start with `claude` not `cluade-secure`, immediately alert this to user and ask to restart the session with `claude-secure`.