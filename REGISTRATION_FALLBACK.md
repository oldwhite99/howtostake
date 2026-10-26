# Railway registration fallback — 2026-10-25

Railway confirmed an October 21, 2026 security incident with session/credential invalidations. A new-signup-disabled error was also reported after the incident. These facts do not identify the exact reason a given Google account fails.

1. **Do not repeatedly try unrelated Google accounts.** If trying Railway recovery, use the original account identity; try an incognito window and official Railway recovery guidance. New account creation might remain paused.
2. **Recommended for this pilot**: use Render free Web Service with Git deployment. Render allows Python/Docker containers, environment secrets, and health checks.
3. **If Render sign-in also fails**: Google Cloud Run (existing GCP account and billing setup) or another existing cloud provider can host the same protected Docker container. Service deployment still requires access and may cost money.
4. The user's ChatGPT Plus account does not inherently provide a runnable always-on public server or universal custom write/execute MCP integration. The Render ChatGPT plugin, even if connected, is primarily for infrastructure deployment/management and does not itself imply that protected TTS synthesis will be called by ChatGPT automatically.

Do not publish the pilot as a commercial YouTube asset until TTS commercial rights are reviewed.
