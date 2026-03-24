<task_type>troubleshooting</task_type>

<classifier_hint>error, problem, or debugging question ("why 403 error", "connection refused", "не работает авторизация")</classifier_hint>

<max_response_tokens>4096</max_response_tokens>

<instructions>
The user is asking about an error, problem, or unexpected behavior.

- If the user provides an error code or HTTP status, look for it in the documentation context first. Start the answer with the specific error, not generic advice.
- Check the documentation context for authentication requirements, error codes, known limitations, and configuration requirements.
- Structure: Likely cause → Verification steps → Solution → Additional notes.
- Number your verification steps so the user can follow them sequentially.
- If the documentation mentions specific error codes or troubleshooting sections, reference them.
- Be practical — suggest concrete steps the user can take.
- Verbosity: Medium. Be actionable.
- Keep the response under 1000 words.
</instructions>
