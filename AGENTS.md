# AI Voice Agent — Development Rules

## Source of truth
Read PROJECT_CONTEXT.md before making architectural changes.
If a project context document is missing, ask for it instead of inventing
decisions or silently replacing the project's requirements.

## Current objective
Validate a local voice conversation in Spanish before building the full CRM.

## Technology boundaries
- Web application: Next.js, React, TypeScript and pnpm.
- Voice experimentation: isolated Python service, managed with uv.
- Database: SQLite and Drizzle ORM, to be introduced in the CRM phase.
- Local models first; do not purchase APIs.
- Do not introduce Docker during initial voice validation.

## Engineering rules
- Use strict TypeScript.
- Keep business logic separate from UI components.
- Do not add large dependencies or download models without explaining
  their size, license, hardware requirements and alternatives.
- Do not claim compatibility or successful execution without verification.
- Run relevant tests, lint and type checks after changes.
- Never commit secrets, real contact lists or personal data.
- Use synthetic business data in the public repository.

## Voice and safety rules
- The initial product is a local simulation, not a telephone dialer.
- Never present the AI as a human.
- Do not implement automated commercial calls to real people in the MVP.
- Respect rejection and requests not to be contacted.
- Never invent prices, business facts or meeting availability.
- A meeting request is not a confirmed booking.

## Workflow
1. Inspect the existing implementation before editing.
2. Propose a small, focused change.
3. Explain the files and dependencies affected.
4. Implement the change.
5. Run relevant checks and report actual results.
6. Summarize what works, what failed and the next step.
7. Update the project decision log when an architectural decision changes.
