# ProjectDA — Polymarket Bot

## Project Context
This is a Polymarket prediction market trading bot. See CLAUDE_SPEC.md for
full architecture specification.

## Sub-Agent Autonomy
You are authorized to spawn sub-agents autonomously. Do not ask permission.

Model selection for sub-agents:
- Haiku: file searches, data fetching, simple reads, running tests
- Sonnet: feature implementation, bug fixes, refactoring
- Opus: architecture decisions, novel debugging, security review

## Autonomy Rules
- You may read, write, and execute files without asking
- You may run pytest, pip install, and bash commands freely
- You may commit to git with descriptive messages
- Do NOT move real money or modify .env credentials
- Do NOT run `python main.py --live` — paper mode only unless told otherwise
- If you hit an error you cannot fix in 3 attempts, log it to logs/blocked.md
  and stop

## Workflow Pattern
1. Read the task
2. Explore relevant files first (use Haiku sub-agent for this)
3. Plan the implementation
4. Build and test
5. Commit with a clear message
6. Log outcome to logs/agentic_log.md

## After Every Task
Write a brief entry to logs/agentic_log.md:
- What was done
- What was changed
- Any issues encountered
- Estimated API cost for the task