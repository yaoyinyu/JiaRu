<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Project documentation rules

- `docs/technical-whitepaper.md` is the canonical integration and interface document.
- After every task that changes behavior, interfaces, usage, configuration, data contracts, models, scripts, deployment, or module status, update the relevant whitepaper section and append its change log before finishing the task.
- Keep one development log file per day under `dev-log/YYYY-MM-DD.md`; append all work from the same day to that file instead of creating multiple daily files.
- If a task genuinely has no whitepaper impact, record that conclusion and the reason in the daily development log.
