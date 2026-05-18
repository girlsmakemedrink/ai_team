"""MCP server: `ai_team_repo` — path-scoped repo ops for code-writing agents.

Per ADR-004, agent code-write/Bash access is never raw. This server wraps:

- File writes (path-scope enforced; no traversal, no symlink escape).
- Shell commands (a fixed enum of command classes, each with a per-class
  arg validator — `Bash` is never on an agent's `--allowed-tools` once
  Backend is live).
- Branch/PR ops (refuses pushes/PRs targeting `main|master|release/*`).
- Read-only repo status.

Configuration is environment-driven so the dispatcher can lock down per-role
scope at server-spawn time (see ADR-004 path matrix):

- `AI_TEAM_REPO_ROOT`         — absolute path to repo working tree.
- `AI_TEAM_PATH_PREFIXES`     — comma list of repo-relative dir prefixes the
                                caller may write to (`*` = unrestricted within
                                the root). Example: `docs/adr,docs/architecture.md`.
- `AI_TEAM_FORBID_BRANCH_RE`  — regex of branch names refused for push / PR base.
                                Default: `^(main|master|release/.*)$`.
- `AI_TEAM_PR_BASE`           — default base branch for `open_pr` if caller
                                doesn't pass one. Defaults to `main`
                                (single-repo exception until iter-5; see
                                ADR-009).
"""
