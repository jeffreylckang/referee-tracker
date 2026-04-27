# Project Setup Structure Template

Use this file as a reference when starting a new project with Claude Code.
Tell Claude: "Follow the structure in Setup_Structure.md for this project."

---

## Directory Layout

```
Project Root/
├── CLAUDE.md                        <- Claude Code instructions + index (keep concise)
├── Setup_Structure.md               <- This file (reusable template reference)
├── .claude/
│   ├── prompts/
│   │   ├── data-agent.md            <- Prompt template for data fetching agent
│   │   ├── health-agent.md          <- Prompt template for monitoring agent
│   │   └── update-agent.md          <- Prompt template for API validation agent
│   └── schemas/
│       ├── README.md                <- What schemas are and how to use them
│       └── *.schema.json            <- One schema file per core data entity
└── docs/
    └── architecture.md              <- Agent diagram, data flow, tech decisions
```

---

## CLAUDE.md Structure (keep to 3-4 sections, each brief)

1. **Project Overview** — 2-3 sentences: what this project does and the end goal
2. **Working Style** — how Claude should collaborate (plan -> confirm -> execute, one step at a time)
3. **Agent Architecture** — agent roles in 1 line each, pointer to docs/architecture.md
4. **Key References** — where schemas live, where prompts live, where decisions are documented

> Rule: CLAUDE.md is a map, not a manual. If a section needs more than a few lines, it belongs in a separate file that CLAUDE.md points to.

---

## Schema Contracts (.claude/schemas/)

- Treat schema files as the **primary source of truth** for all data shapes
- Every agent or piece of code that reads/writes data must reference the relevant schema first
- One `.schema.json` file per core entity (e.g., foul_event, referee, player)
- Include a `schemas/README.md` explaining the contract rules

## Agent Prompts (.claude/prompts/)

- One markdown file per agent
- Each prompt file should define: role, inputs, outputs, constraints, error behavior

## Docs (docs/)

- `architecture.md` — agent diagram, data flow, key decisions and their rationale
- Add more docs files as the project grows; do not bloat CLAUDE.md with this content

---

## Working Style Rules (to paste into CLAUDE.md)

- Always plan and outline before doing anything
- Confirm the plan with the user before executing
- Work one step at a time — do not do everything at once
- Prefer editing existing files over creating new ones
- Keep solutions simple; do not over-engineer
- When in doubt about scope, ask before acting
