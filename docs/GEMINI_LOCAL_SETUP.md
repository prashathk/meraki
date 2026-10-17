# Gemini Developer API for the local Meraki demo

The local configuration uses the Gemini Developer API through Google AI Studio,
not Vertex AI. It defaults to `gemini-3.5-flash-lite`. The only permitted
Developer API model IDs are `gemini-3.5-flash-lite` and `gemini-3.8-flash`, both
listed with free input/output on Google's pricing page on 17 October 2026.
Exact IDs are pinned; unknown models and moving aliases are rejected.

## Activate locally

1. Open [Google AI Studio API keys](https://aistudio.google.com/api-keys).
2. Create/select a project whose billing tier is **Free Tier**. Keep billing
   unlinked for that project. Create an API key for it.
3. In the repository root `.env`, set:

   ```dotenv
   GEMINI_PROVIDER=developer
   GEMINI_MODEL=gemini-3.5-flash-lite
   GEMINI_API_KEY=your_key_here
   ```

4. Keep the key in that local file; it is Git-ignored. Never paste it into the
   frontend, a `VITE_` variable, a screenshot, or a chat message.
5. Refresh Meraki, log in as `university@meraki.local`, and open Course preparation.
   Choose **Gemini — AI Studio (free-tier models)** and upload a public/sample
   prospectus or enter a public course listing URL. Review the extracted rows.

Both the API and worker read these Gemini settings from the root `.env` for each
request/job; exported environment variables take precedence. Editing the key in
`.env` does not need a restart after this version has been deployed. Other app
settings retain their existing environment-variable behavior.

## Cost and data behavior

The model allowlist limits model selection, **not account billing**. The same
models incur charges with a paid-tier key. Meraki cannot determine the project's
billing tier from the API key. Verify **Free Tier** in AI Studio and keep billing
disabled. Google's model availability, pricing and quotas can change; recheck
the pricing page before future releases. Update the allowlist only after review.

The adapter sends extracted source text and approved taxonomy labels to Google.
Free-tier content can be used to improve Google's products. Use public/demo
course material rather than private student or institutional data.

No Search/Maps grounding, paid tools, batch jobs or context caching are requested.
Quota exhaustion stops that extraction with a clear error; there are no automatic
retries, provider switches or model upgrades. The user can explicitly select the
local NLP baseline. Student recommendations continue using the existing scoring
formula and do not call Gemini.

`GET /api/health` reports the provider, model and whether a key/configuration is
present, without returning the key. `gemini_configured: true` means configuration
is present, not that the key, quota or billing tier has been verified. An actual
successful extraction is the live integration check.

The pre-existing Vertex adapter remains available only when an operator explicitly
sets `GEMINI_PROVIDER=vertex`, `GOOGLE_CLOUD_PROJECT`, `GEMINI_MODEL`, location and
Google Cloud credentials. That is a separate billed configuration, not this demo's
free-tier setup; Developer API errors never fall back to Vertex.

References:

- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Billing tiers and API keys](https://ai.google.dev/gemini-api/docs/billing)
- [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
