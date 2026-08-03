# Cline Auto-Approval Configuration for LOATS13July2026

## Setup Session Configuration
This configuration applies to the initial setup session only.

### Enabled Permissions (Setup Session)
- ✅ Read files
- ✅ Edit files
- ✅ Execute safe commands
- ✅ Use MCP servers

### Limits
- Max Requests: 10 (setup session only)

## Post-Setup Configuration
After setup completes, the following applies:

### Enabled Permissions
- ✅ Auto-approve for Execute commands

Be extremely concise.
- No greetings, filler, hedging, or restating the question.
- Use short sentences or bullet points.
- Keep all technical details, code, commands, file paths, and errors 100% exact.
- Prefer fragments or telegraphic style when clarity is not lost.
- Never end with “let me know if you need more” or similar offers.
- When explaining, lead with the answer, then minimal supporting detail.

### Per-Phase Manual Gating
After setup, strict per-phase manual gating resumes as defined in loats.md:
- Phase gates (G1-G10) must be manually verified
- Git commits/pushes require explicit approval
- Each phase must complete before starting the next

## Project Context
@loats.md
