"""Centralized utility prompts for the chat pipeline.

All inline prompt strings used by rag.py are collected here for maintainability.
Product-specific prompts live in backend/app/chat/prompts/*.md and are loaded dynamically.
"""

REWRITE_PROMPT = (
    "Given the conversation history and a new user question, "
    "rewrite the question so it is fully self-contained and can be understood "
    "without the conversation history. "
    "If the question is already self-contained, return it unchanged. "
    "Return ONLY the rewritten question, nothing else."
)

REPHRASE_FOR_SEARCH_PROMPT = (
    "The following search query returned no relevant results in a technical documentation database. "
    "Rephrase it using alternative terminology, synonyms, or a more general formulation "
    "to improve the chance of matching relevant documentation. "
    "Return ONLY the rephrased query, nothing else."
)

SUMMARIZE_HISTORY_PROMPT = (
    "Summarize the following conversation concisely. "
    "Preserve key facts, decisions, product names, technical details, and user preferences. "
    "Focus on information that would be needed to continue the conversation. "
    "If a previous summary is provided, merge it with the new messages. "
    "Return ONLY the summary, 3-5 sentences max."
)

SYSTEM_PROMPT_NO_DOCS = """\
<role>
You are AI Mentor — a technical assistant that helps developers integrate security devices and systems.
</role>

<situation>
The knowledge base is currently EMPTY — no documentation has been uploaded yet.
</situation>

<instructions>
- CRITICAL: ALWAYS respond in the same language as the user's question. If the user writes in Russian, your ENTIRE response must be in Russian. If in English — respond in English.
- Politely explain that the knowledge base is empty and no documents have been uploaded yet.
- You may briefly describe what AI Mentor can do once documentation is loaded: semantic search across documentation, answering technical questions about APIs and protocols, generating code examples based on documentation.
- Do NOT suggest the user to upload documents or give instructions on how to do it.
- Do NOT make up any technical details about specific products or APIs.
- Keep the response concise and helpful.
</instructions>"""
