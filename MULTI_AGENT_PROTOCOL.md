# Agnara Multi-Agent Coordination Protocol

Agnara is built to be developed by a *swarm* of autonomous agents and human developers simultaneously. To ensure that everyone can work without stepping on each other's toes, we use a deterministic, GitHub-backed coordination protocol.

## 1. The Execution Ledger

The repository itself is the control plane.
- **Strategic Direction**: `ROADMAP.md`
- **Planning**: `BACKLOG.md`
- **Executable Units**: GitHub Issues
- **Coordination**: GitHub Issue Comments

Agents must **never** begin work on an issue without successfully acquiring an atomic lease on it.

## 2. Work Metadata (JSON Schema)

Every executable issue MUST contain a JSON metadata block identifying its scopes and dependencies. This allows agents to safely multiplex work across the repository without merge conflicts.

Example:
```json
# agnara-work
{
  "id": "E1.3",
  "type": "feature",
  "priority": "P1",
  "scope": {
    "write": [
      "packages/agnara-core/src/agnara/registry/**",
      "tests/core/registry/**"
    ],
    "read": ["docs/**"]
  },
  "dependencies": {
    "blocked_by": [40],
    "conflicts_with": []
  }
}
```

*Note: we use ````json # agnara-work` because JSON is natively parsable by Python without third-party dependencies, preserving the zero-dependency nature of the framework infrastructure.*

## 3. The Coordination CLI

The CLI at `scripts/agent.py` implements the protocol. It relies on the `gh` command-line tool.

### Find work
```bash
python scripts/agent.py next
```
This evaluates all open issues, extracting their scopes and active leases. It returns the next issue that is ready and does not collide with currently executing work. Use `--json` for machine-readable output.

### Claim a Lease
```bash
python scripts/agent.py claim <issue_number> <worker_id>
```
This initiates an atomic claim process:
1. Posts a claim comment to the issue.
2. Re-evaluates the issue's comments chronologically.
3. Exits with `0` if you won the race, or `1` if another agent beat you to it.

### Release a Lease
```bash
python scripts/agent.py release <issue_number> <worker_id>
```
Releases the lease, allowing other agents to claim the issue or marking it ready for review.

### View Swarm Status
```bash
python scripts/agent.py status
```
Prints an overview of all active workers and their locked scopes.

## 4. Worktrees for Local Multi-Agent

When running multiple agents locally on the same machine, they MUST NOT share the same Git working directory.

Use `git worktree` to create isolated environments for each task:
```bash
git worktree add ../agnara-issue-42 -b feat/42-new-capability
cd ../agnara-issue-42
```
When finished and pushed, the worktree can be safely removed.

## 5. Review vs Implementation Ownership

Implementation ownership (the claim) is distinct from review ownership. An agent may claim an issue for implementation, push a PR, and release the claim. A *different* agent (or human) should independently review the PR.

An agent reviewing a PR MUST NOT claim the original implementation issue, but may claim a separate review issue if the backlog is structured that way.

## 6. Recovery and Expiration

Leases expire automatically after 2 hours. If an agent crashes, it will not permanently block the issue. Another agent will be able to claim it once the expiration time passes.
