# Interview problem — TaskBoard

Welcome, and thanks for taking the time. This is an **open-ended, 2-hour**
exercise. You will build a small task board (a stripped-down Trello/Kanban).

**The point is not to "finish."** Almost nobody finishes everything. We care
about **how far you get** and, above all, **how effectively you work with
Claude Code** to get there. Work the way you actually would.

## Rules

- Use **Claude Code** for the work. That's the tool we're evaluating you with.
- Stack: **Django + PostgreSQL** for the backend, **JavaScript or TypeScript**
  for the small frontend. Use Django REST Framework if you like.
- **Commit often** with `git`. Your history is part of the story.
- Keep a short note (in `NOTES.md`) of decisions and trade-offs as you go.
- You may be asked afterwards to **explain your choices**, so don't ship
  anything you don't understand.

## What you're building

A board with **tasks** that move through **columns** (`To Do → Doing → Done`).
Tackle the milestones roughly in order. Do as many as you can; partial progress
counts.

### Milestone ladder

- **M0 — It runs.** The Django project starts, connects to Postgres, and
  migrations apply cleanly. A health endpoint or the admin page loads.
- **M1 — Tasks (core CRUD).** A `Task` model (at least: `title`, `status`,
  `created_at`) persisted in Postgres. REST endpoints to **list, create,
  update, and delete** tasks.
- **M2 — Workflow + validation.** `status` is one of `todo` / `doing` / `done`.
  Moving a task between columns updates its status. The server **rejects bad
  input** (empty title, invalid status) with sensible 4xx responses.
- **M3 — A minimal UI.** A single page (vanilla JS/TS or a framework — your
  call) that lists tasks by column and lets you **create a task** and **move
  one** between columns, talking to your API.
- **M4 — Make it solid.** Add a few things that show care: input-validation
  error messages, filtering or pagination on the list endpoint, and **a few
  automated tests**.
- **M5 — Stretch (pick ONE).** Whatever you'd be proud of:
  - user accounts + "my boards" (auth),
  - drag-and-drop between columns,
  - an activity log of task changes,
  - due dates with an "overdue" filter,
  - Dockerized one-command startup.

## What "good" looks like

- You get the boring stuff (setup, DB, migrations) working fast and spend your
  thinking time on the interesting parts.
- You **review what Claude produces** rather than pasting blindly, and you catch
  problems early.
- When something breaks, you debug it with Claude methodically instead of
  flailing.
- Your prompts give Claude enough context and direction to be useful.

## Submitting

There's nothing to submit — just stop when time is called. Make sure your last
change is committed. We capture your working folder and your full Claude Code
session automatically.

Good luck, and have fun with it.
