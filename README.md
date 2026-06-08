# kana-skills

A collection of the Claude skills, slash commands, and MCP servers I've built for my
homelab workflow. **No secrets live in this repo** — every credential is supplied at runtime
from [Bitwarden Secrets Manager](https://bitwarden.com/products/secrets-manager/) (see
[Secrets](#secrets) below).

## Contents

| Path | Type | What it does |
|------|------|--------------|
| [`skills/truenas-app-setup/`](skills/truenas-app-setup/SKILL.md) | Skill | Installs a catalog app on my TrueNAS Scale host via the `truenas` MCP, applying my host-path storage conventions. |
| [`commands/container-deploy.md`](commands/container-deploy.md) | Slash command | Builds an image with podman, runs a local health check, and pushes to my LAN registry. |
| [`mcp/truenas/`](mcp/truenas/) | MCP server | Python MCP exposing TrueNAS Scale app/dataset/filesystem tools over the TrueNAS API. |
| [`CLAUDE.md`](CLAUDE.md) | Config | My user-wide Claude Code instructions (git-branching convention). Auto-loads when working in this repo. |

## Install

### Skill
Copy into your Claude skills directory:
```bash
cp -r skills/truenas-app-setup ~/.claude/skills/
```

### Slash command
```bash
cp commands/container-deploy.md ~/.claude/commands/
```

### `truenas` MCP
The server is vendored in [`mcp/truenas/`](mcp/truenas/) (runs with [`uv`](https://docs.astral.sh/uv/)).
Register it by merging [`mcp/truenas/.mcp.json`](mcp/truenas/.mcp.json) into your `~/.claude.json`
(or a project `.mcp.json`). Adjust the `--directory` path to wherever you cloned this repo, then:
```bash
uv run --directory mcp/truenas python main.py   # smoke-test it standalone
```

## Secrets

Nothing here contains a credential. The only real secret is `TRUENAS_API_KEY`, stored in
Bitwarden Secrets Manager and injected into the environment at launch — the MCP reads it from
`os.environ`, and `.mcp.json` references it as `${TRUENAS_API_KEY}`.

One-time setup:

1. In Bitwarden Secrets Manager, create a project (e.g. `claude-code`), add the secret
   `TRUENAS_API_KEY`, create a machine account with read access, and generate an access token.
2. Store the token locally (never in git):
   ```bash
   mkdir -p ~/.config/bws && umask 077
   printf 'BWS_ACCESS_TOKEN=%s\n' '<your-access-token>' > ~/.config/bws/token
   chmod 600 ~/.config/bws/token
   ```
3. Launch Claude Code with secrets injected — add to `~/.bashrc`:
   ```bash
   claude-secure() {
     [ -f ~/.config/bws/token ] && { set -a; . ~/.config/bws/token; set +a; }
     bws run -- claude "$@"
   }
   ```
   Then start sessions with `claude-secure` (not plain `claude`). `bws run` injects every
   secret in the project as an environment variable named after its key.

See [`.env.example`](.env.example) for the full list of variables.

## Notes

- The LAN container registry (`192.168.7.17:5000`) is unauthenticated plain-HTTP and LAN-only,
  so `container-deploy.md` does no `podman login`.
- `mcp/truenas/main.py` reads `TRUENAS_HOST` + `TRUENAS_API_KEY` from the environment only;
  it has no hardcoded credentials.
