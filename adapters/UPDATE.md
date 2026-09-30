# Adapters — Rules and Update Log

This file is the running record for **C5: adapters**. Update it whenever an adapter is added, changed, tested, enabled, disabled, fails in an important way, or requires a decision.

Do not record secrets here. API keys, passwords, OAuth tokens, customer data, and full request/response bodies belong only in local ignored environment files or the relevant secure provider dashboard.

## Rules

1. **One responsibility per adapter.** An adapter translates one external service into one port from `contracts.ports`.
2. **Agents use ports, never providers.** An agent must use `ports.search`, `ports.llm`, and similar interfaces. It must not import a provider SDK or an adapter module directly.
3. **Keep adapters independent.** Adapters must not import agents, the worker, the API, or the database.
4. **Keep secrets local.** Read credentials from environment settings. Never hard-code, log, commit, paste into documentation, or add them to test fixtures.
5. **Keep a fake for every port.** Fakes are the default for automated tests and must remain deterministic and free of network calls or paid API usage.
6. **Classify failures clearly.** Use `NonRetryableAgentError` for invalid credentials or invalid configuration. Use `AgentError` for temporary provider, network, or rate-limit failures so the worker can retry them.
7. **Test before enabling.** Add mocked adapter tests first. Then perform one small live request with a non-sensitive test query and record the result below.
8. **Minimize cost and scope.** Use the provider's lowest suitable tier and bounded requests. Do not enable paid features or send production data without an explicit decision.
9. **Document every meaningful change here.** Each entry must state the date, owner, what changed, how it was verified, and any follow-up or risk.
10. **Do not silently change providers.** Record the reason, configuration change, compatibility impact, and rollback path before switching a provider.

## Change-entry template

Copy this for every meaningful adapter event:

```md
### YYYY-MM-DD — <adapter or provider> — <short outcome>

- Owner: <name>
- Change or event: <what happened>
- Configuration: <environment variable names only; never values>
- Verification: <test or check performed and outcome>
- Cost / limits: <expected usage, if relevant>
- Follow-up / rollback: <next action or how to disable safely>
```

## Current adapter status

| Port | Provider | State | Notes |
| --- | --- | --- | --- |
| Search | Tavily | Enabled locally | Used by the Researcher through `SearchPort`. |
| LLM | OpenAI | Fake by default until `OPENAI_API_KEY` is configured | Used by the Writer through `LLMPort`. |
| Text-to-speech | gTTS | Available in real-adapter mode | Used by Video. |
| Image | Cloudflare Workers AI (FLUX.1 Schnell) | Enabled locally | Used by Image through `ImagePort`; requires both Cloudflare environment variables. |
| Publish | YouTube Data API v3 / Google Drive API | Ready locally | Requires the account owner to grant the relevant Google OAuth scope; every upload still requires Publisher approval. |
| Email | Mailtrap Email API | Prepared locally | Activates only after a verified `MAIL_FROM_EMAIL` is configured; otherwise remains fake. |
| Storage | Local storage | Enabled | Stores local development artifacts. |

## Update log

### 2026-09-20 — Project setup — workspace and Docker prepared

- Owner: Ahmed
- Change or event: Updated local `main` from commit `71244d5` to `1e1faa2`, then created the working branch `codex/c4-agents` for C4/C5 work.
- Configuration: Docker Compose development stack was built and started locally.
- Verification: API, frontend, PostgreSQL, and Redis containers started; database migration completed successfully.
- Cost / limits: None.
- Follow-up / rollback: Keep all implementation work on `codex/c4-agents` until it is reviewed and merged.

### 2026-09-20 — Researcher agent — baseline reviewed

- Owner: Ahmed
- Change or event: Reviewed the Researcher C4 plug-in before connecting real search. It accepts `topic` and `num_sources`, calls only `SearchPort`, returns notes and source records, and raises a readable no-sources error.
- Configuration: No provider credentials changed during the review.
- Verification: Reviewed the agent, manifest, fixture, and isolated test. The expected test path was identified as `agents/researcher/tests`.
- Cost / limits: None.
- Follow-up / rollback: Keep provider logic in C5 adapters; the Researcher must continue to know only `SearchPort`.

### 2026-09-20 — Test environment — limitations identified

- Owner: Ahmed
- Change or event: Identified two development-container limitations while validating the Researcher and Tavily work: the worker image does not include `pytest`, and asynchronous tests require an async pytest configuration or plug-in when run directly in that image.
- Configuration: No production service setting changed by this observation.
- Verification: Direct test attempts reported the missing test runner and async-test support. The new Tavily adapter test was made self-contained, avoiding an async pytest dependency for that focused check.
- Cost / limits: None.
- Follow-up / rollback: Run the full component suites through the repository's standard development test environment; do not add test-only tools to the production worker image solely for ad-hoc testing.

### 2026-09-20 — Search provider decision — Tavily selected

- Owner: Ahmed
- Change or event: Selected Tavily as the first real search provider because it is suited to agent research and the repository already included a `TavilySearch` adapter behind `SearchPort`.
- Configuration: The provider is controlled by `SEARCH_API_KEY`; the adapter is enabled locally through `FAKE_ADAPTERS=false`.
- Verification: Reviewed the Tavily API requirements and compared the existing adapter implementation with the current authentication method.
- Cost / limits: Basic searches consume one Tavily credit. Development runs should request only the sources needed.
- Follow-up / rollback: SerpApi remains a possible future alternative if Google-specific result features, maps, shopping, or detailed SERP data are needed.

### 2026-09-20 — Tavily Search — enabled locally

- Owner: Ahmed
- Change or event: Connected the existing Tavily `SearchPort` adapter for real Researcher searches.
- Configuration: `FAKE_ADAPTERS=false`; `SEARCH_API_KEY` is stored only in local ignored `.env`.
- Verification: Added mocked adapter tests for Bearer authentication, result mapping, and service-error classification; all 3 tests pass. A live bounded query returned 2 sources through the project adapter.
- Cost / limits: Tavily basic searches use one credit each. Use small result counts during development.
- Follow-up / rollback: Set `FAKE_ADAPTERS=true` or remove `SEARCH_API_KEY` from local `.env` to return to fake search. Rotate the Tavily key because it was shared in chat during setup.

### 2026-09-20 — OpenRouter Writer — enabled locally

- Owner: Ahmed
- Change or event: Configured the Writer's OpenAI-compatible adapter to use OpenRouter's free-model router. Added an optional `OPENAI_BASE_URL` setting so compatible providers can be selected without changing the Writer agent.
- Configuration: `OPENAI_API_KEY`, `OPENAI_MODEL=openrouter/free`, and `OPENAI_BASE_URL=https://openrouter.ai/api/v1` are stored only in local ignored `.env`.
- Verification: A real Writer request completed through OpenRouter and returned a validated Markdown article.
- Cost / limits: The free router uses currently available free models with provider-controlled limits and availability. Do not send sensitive material to free models without first reviewing that model's data policy.
- Follow-up / rollback: Remove `OPENAI_BASE_URL` and restore an OpenAI model to use OpenAI later; set `FAKE_ADAPTERS=true` to return all adapters to deterministic fakes. Rotate the OpenRouter key because it was shared in chat during setup.

### 2026-09-20 — OpenRouter Writer — free-router response rejected

- Owner: Ahmed
- Change or event: A real Researcher → Writer run reached Tavily and OpenRouter successfully, but the Writer rejected the provider response because `article_md` was an empty string.
- Configuration: `OPENAI_MODEL=openrouter/free` selects a currently available free model at request time rather than a fixed model.
- Verification: Researcher completed successfully. OpenRouter returned HTTP 200 for Writer requests. The Writer log recorded: `article_md: String should have at least 1 character`; its in-agent reformat attempt and worker retry then began. The run was cancelled before a valid Writer result was produced.
- Cost / limits: The requests used free-router availability; no paid provider was enabled.
- Follow-up / rollback: The free router is not reliable enough for structured Writer output. Choose a fixed model that supports JSON/schema output, or keep the fake Writer for deterministic testing. Investigate the separate cancellation-state issue: after cancellation, the active Writer node remained marked `running` in the local execution log.

### 2026-09-20 — Run outputs — visible in the application

- Owner: Ahmed
- Change or event: Added `GET /runs/{run_id}/outputs` and an Outputs section on the run screen. Owners can now read saved text outputs, including the Writer's Markdown article, directly in the application.
- Configuration: No provider credentials changed.
- Verification: Regenerated the OpenAPI contract and frontend types. The focused API suite passes (14 tests) and the frontend type check passes.
- Cost / limits: None.
- Follow-up / rollback: File and URL outputs currently show their saved reference; richer download/preview controls can be added when those agents are enabled.

### 2026-09-20 — Cloudflare Workers AI Image — enabled locally

- Owner: Ahmed
- Change or event: Selected Cloudflare Workers AI's FLUX.1 Schnell model as the real Image adapter. Added the adapter behind `ImagePort`, preserving the deterministic fake when the integration is disabled or incomplete. The Image agent now detects PNG versus JPEG output and saves the matching extension and MIME type.
- Configuration: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are stored only in local ignored `.env`; `FAKE_ADAPTERS=false` enables real adapters.
- Verification: Added mocked tests for Workers AI authorization, request shape, base64 image decoding, and error classification; all 4 focused adapter checks pass. After recreating the worker so Docker reloaded local `.env`, one bounded live request returned a 287,880-byte JPEG.
- Cost / limits: FLUX.1 Schnell uses Cloudflare Workers AI usage. Development runs use four diffusion steps per image; keep image counts small.
- Follow-up / rollback: Restart the worker after the focused tests pass, then run one single-image workflow. Set `FAKE_ADAPTERS=true` or remove either Cloudflare variable to return to fake images. Rotate the Cloudflare token because it was shared in chat during setup.

### 2026-09-20 — Image outputs — preview and download controls added

- Owner: Ahmed
- Change or event: The run Outputs page now renders saved Image-agent files as inline previews, with Open image and Download controls. It derives the local file URL from the stored path rather than showing an unusable raw path.
- Configuration: No provider credentials changed.
- Verification: Frontend type check passes.
- Cost / limits: None.
- Follow-up / rollback: The local file server is development-only. Replace these URLs with signed storage URLs when production storage is enabled.

### 2026-09-20 — Video worker — baseline reviewed

- Owner: Ahmed
- Change or event: Reviewed the Video agent. It turns the Writer's article into plain narration text, requests MP3 narration through `TTSPort`, then assembles a playable H.264/AAC MP4 in the worker using FFmpeg. Real-adapter mode already uses gTTS and needs no API key.
- Configuration: `FAKE_ADAPTERS=false` selects gTTS; FFmpeg is installed in the worker image.
- Verification: Frontend type check passes. A bounded live gTTS narration and FFmpeg render produced a playable 4.46-second MP4; the Outputs screen renders saved MP4 files with player, Open video, and Download controls.
- Cost / limits: gTTS is a third-party network service with practical request limits; keep initial scripts short. FFmpeg uses worker CPU and may take a few minutes for longer narration.
- Follow-up / rollback: The current renderer is an honest narrated black-background MP4. Decide whether the next enhancement should add timed title/content slides and reuse the Image-agent assets.

### 2026-09-29 — Publisher — YouTube selected

- Owner: Ahmed
- Change or event: Selected YouTube as the first real publishing destination. The Publisher agent already requires an explicit approval before any upload attempt; the real YouTube adapter and OAuth connection screen are still to be implemented.
- Configuration: Planned variables are `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`; access tokens must be encrypted in the credentials store, never placed in a workflow or committed environment file.
- Verification: Confirmed the YouTube Data API upload endpoint and its minimum `youtube.upload` OAuth scope. No video has been uploaded.
- Cost / limits: YouTube uploads require an OAuth-authorized channel. Unverified Google API projects created after 28 July 2020 upload as private until Google completes an API compliance audit.
- Follow-up / rollback: Create a Google Cloud OAuth web client for the local application, then implement and test an unlisted/private test-channel upload. Keep the fake publisher as the rollback path.

### 2026-09-29 — Publisher — YouTube OAuth and upload adapter ready

- Owner: Ahmed
- Change or event: Added the signed Google OAuth connection flow and a YouTube Data API v3 uploader. OAuth tokens are encrypted in the credentials table; the worker retrieves only the token belonging to the user who started a run. The adapter validates the local video path, uploads the approved MP4 with its configured metadata and privacy, then returns its canonical watch URL.
- Configuration: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `JWT_SECRET` are read only from local environment configuration. The OAuth scope is limited to `youtube.upload`.
- Verification: API OAuth imports, worker YouTube-publisher imports, and worker startup succeeded. The frontend contract was regenerated and the TypeScript type check passes. No real upload has been made.
- Cost / limits: Uploads consume YouTube API quota. The Google project’s unverified-app restriction can force uploads private until Google completes its compliance review.
- Follow-up / rollback: The account owner must click **Connect Google**, complete consent, then approve one short unlisted test upload. Disconnecting/removing the stored credential disables the real YouTube publisher; fake mode remains available for test runs.

### 2026-09-29 — Publisher — Google Drive upload adapter ready

- Owner: Ahmed
- Change or event: Replaced the Drive publisher stub with a real Google Drive API uploader. It uploads the approved MP4 to the connected account's Drive root, preserves title and description metadata, and returns the Drive file URL. It never changes Drive sharing permissions, so files stay private by default.
- Configuration: The existing Google OAuth client uses the same client ID and secret but authorizes Drive separately with `drive.file`; it must not request that scope together with `youtube.upload`.
- Verification: Drive publisher and Google scope configuration import successfully in the running containers; frontend type check passes. No Drive file has been uploaded yet.
- Cost / limits: Uses Google Drive API quota and the user's available Drive storage.
- Follow-up / rollback: Enable Google Drive API in the same Google Cloud project, click **Connect Google Drive**, then approve a small test upload. Removing the stored Drive credential disables only Drive publishing.

### 2026-09-29 — Publisher — Google scope incompatibility corrected

- Owner: Ahmed
- Change or event: Google rejected a combined `youtube.upload` and `drive.file` consent request because those scopes cannot be requested together. Split OAuth into independent **Connect YouTube** and **Connect Google Drive** actions, each with its own signed state, encrypted credential, and worker injection.
- Configuration: No new secrets. Existing YouTube authorization remains stored as the `youtube` credential; Drive authorization is stored separately as `drive`.
- Verification: Regenerated API contract and frontend types; frontend type check passes. API OAuth endpoints and worker provider-specific credential wiring import successfully.
- Cost / limits: None beyond the respective Google API quotas.
- Follow-up / rollback: Click **Connect Google Drive** for a new Drive-only consent flow. Do not reconnect YouTube unless that account or permission needs to change.

### 2026-09-29 — Email — Mailtrap transactional adapter prepared

- Owner: Ahmed
- Change or event: Added a Mailtrap HTTPS transactional-email adapter behind `EmailPort`. It sends plain-text messages with Mailtrap's API token and returns the provider message ID; failures distinguish credential, invalid-sender, and temporary-service errors.
- Configuration: `MAILTRAP_API_TOKEN` is stored only in ignored local `.env`. `MAIL_FROM_EMAIL` is intentionally blank until a verified Mailtrap sending address is chosen.
- Verification: Source review confirms the factory keeps `FakeEmail` active unless both the token and a sender address are set. Docker Desktop was unavailable before the local import check could run.
- Cost / limits: Mailtrap Email API/SMTP delivery requires a verified sending domain. The provider's Email Sandbox is separate from Email Sending.
- Follow-up / rollback: Add a verified sender address as `MAIL_FROM_EMAIL`, start Docker Desktop, then send one message only to a controlled test recipient. Clear either Mailtrap variable or set `FAKE_ADAPTERS=true` to return to fake email.

### 2026-09-29 — Email — Mailtrap sender activated locally

- Owner: Ahmed
- Change or event: Set the local Mailtrap sender to `hello@lnq.world` after the owner confirmed the `lnq.world` sending domain was verified.
- Configuration: `MAIL_FROM_EMAIL` is set only in ignored local `.env`; the Mailtrap API token remains local-only.
- Verification: No message was sent. Docker Desktop was not running during the earlier verification attempt, so the worker still needs a restart before the adapter becomes active.
- Cost / limits: No usage yet.
- Follow-up / rollback: Start Docker Desktop, restart the worker, then provide a controlled recipient for one delivery test. Clear `MAIL_FROM_EMAIL` to keep FakeEmail active.

### 2026-09-29 — Email — Mailtrap live delivery verified

- Owner: Ahmed
- Change or event: Recreated the local worker so it loaded the Mailtrap configuration, then sent one owner-authorized transactional test email to a controlled Gmail recipient from `hello@lnq.world`.
- Configuration: `MAILTRAP_API_TOKEN` and `MAIL_FROM_EMAIL` remain only in ignored local `.env`.
- Verification: Mailtrap accepted the send request and returned a provider message ID. No recipient list, token, or message ID is recorded here.
- Cost / limits: One transactional-email send consumed.
- Follow-up / rollback: Confirm inbox and spam-folder delivery. Use the Email workflow only for explicit recipients; clear either Mailtrap setting or set `FAKE_ADAPTERS=true` to disable real delivery.

### 2026-09-29 — Email — approval gate removed by owner request

- Owner: Ahmed
- Change or event: Changed the Email agent manifest so it sends automatically when reached in a workflow. Publisher remains independently approval-gated.
- Configuration: No provider configuration changed.
- Verification: The Email-agent manifest test expectation was updated; the worker catalog needs a restart to load the changed manifest.
- Cost / limits: Each workflow run can now send to its configured recipients without a pause.
- Follow-up / rollback: Set `requires_approval` back to `true` in the Email manifest to restore the gate. Keep recipient lists controlled because Mailtrap delivery is active.

### 2026-09-20 — Worker startup — development blocker fixed

- Owner: Ahmed
- Change or event: Normalized Windows line endings for `worker-entrypoint` while building the Linux worker image. The worker had exited with `bash\\r` not found.
- Configuration: No credentials changed.
- Verification: Rebuilt and started the worker; Celery connected to Redis and published 6 agents to the catalog.
- Cost / limits: None.
- Follow-up / rollback: Keep line-ending normalization in the Docker build so Windows checkouts remain supported.

### 2026-09-20 — Adapter documentation — rules adopted

- Owner: Ahmed
- Change or event: Created this file as the durable rules and activity record for all adapter work.
- Configuration: No provider credentials changed.
- Verification: Rules, change-entry template, current provider status, completed work, and open decisions are documented here.
- Cost / limits: None.
- Follow-up / rollback: Add an entry for every material adapter event before the related branch is considered ready to merge.

## Open decisions and follow-ups

- Choose and document the real image-generation provider.
- Configure an OpenAI API key before enabling real Writer generation.
- Configure provider credentials and approval policy before enabling real publishing or email delivery.
- Add a live smoke-test checklist for each enabled provider without exposing credentials.
