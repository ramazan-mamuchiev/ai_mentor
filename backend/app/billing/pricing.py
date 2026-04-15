"""Model pricing: COGS (our LLM API cost) and charge (user-facing price)."""

from decimal import Decimal

_ONE_MILLION = Decimal("1000000")

# --- COGS: actual LLM provider prices (what we pay) ---
# Source: INFRASTRUCTURE_COSTS.md §2.6
MODEL_COGS: dict[str, dict[str, Decimal]] = {
    "gemini-2.5-flash":      {"input_per_1m": Decimal("0.30"),  "output_per_1m": Decimal("2.50")},
    "gemini-2.5-flash-lite": {"input_per_1m": Decimal("0.15"),  "output_per_1m": Decimal("1.25")},
    "gemini-2.5-pro":        {"input_per_1m": Decimal("1.25"),  "output_per_1m": Decimal("10.00")},
    "gemini-2.0-flash":      {"input_per_1m": Decimal("0.10"),  "output_per_1m": Decimal("0.40")},
}

# --- Charge: user-facing prices (what the client pays) ---
# Source: MONETIZATION.md §AI Model Tiers — per-token billing
# These rates include our margin over COGS.
MODEL_CHARGE: dict[str, dict[str, Decimal]] = {
    "gemini-2.5-flash":      {"input_per_1m": Decimal("0.50"),  "output_per_1m": Decimal("4.00")},
    "gemini-2.5-flash-lite": {"input_per_1m": Decimal("0.25"),  "output_per_1m": Decimal("2.00")},
    "gemini-2.5-pro":        {"input_per_1m": Decimal("2.50"),  "output_per_1m": Decimal("20.00")},
    "gemini-2.0-flash":      {"input_per_1m": Decimal("0.20"),  "output_per_1m": Decimal("0.80")},
}

SEARCH_COGS_USD = Decimal("0.0003")
SEARCH_CHARGE_USD = Decimal("0.0005")

# Embedding models are input-only (no output tokens).
EMBEDDING_COGS: dict[str, Decimal] = {
    "gemini-embedding-2-preview": Decimal("0.05"),   # $0.05 per 1M tokens
    "text-embedding-004":        Decimal("0.025"),
}
EMBEDDING_CHARGE: dict[str, Decimal] = {
    "gemini-embedding-2-preview": Decimal("0.10"),
    "text-embedding-004":        Decimal("0.05"),
}


def _calc(
    pricing: dict[str, Decimal],
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    input_cost = pricing["input_per_1m"] * Decimal(prompt_tokens) / _ONE_MILLION
    output_cost = pricing["output_per_1m"] * Decimal(completion_tokens) / _ONE_MILLION
    return (input_cost + output_cost).quantize(Decimal("0.00000001"))


def calculate_llm_cogs(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Our cost for an LLM call (what we pay the provider)."""
    pricing = MODEL_COGS.get(model)
    if pricing is None:
        return Decimal("0")
    return _calc(pricing, prompt_tokens, completion_tokens)


def calculate_llm_charge(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """User-facing charge for an LLM call (what the client pays us)."""
    pricing = MODEL_CHARGE.get(model)
    if pricing is None:
        return Decimal("0")
    return _calc(pricing, prompt_tokens, completion_tokens)


def calculate_search_cogs() -> Decimal:
    """Our cost per vector search query."""
    return SEARCH_COGS_USD


def calculate_search_charge() -> Decimal:
    """User-facing charge per vector search query."""
    return SEARCH_CHARGE_USD


def calculate_embedding_cogs(model: str, tokens: int) -> Decimal:
    """Our cost for an embedding API call."""
    rate = EMBEDDING_COGS.get(model)
    if rate is None or tokens <= 0:
        return Decimal("0")
    return (rate * Decimal(tokens) / _ONE_MILLION).quantize(Decimal("0.00000001"))


def calculate_embedding_charge(model: str, tokens: int) -> Decimal:
    """User-facing charge for an embedding API call."""
    rate = EMBEDDING_CHARGE.get(model)
    if rate is None or tokens <= 0:
        return Decimal("0")
    return (rate * Decimal(tokens) / _ONE_MILLION).quantize(Decimal("0.00000001"))


def calculate_mcp_cogs(
    embedding_model: str,
    embedding_tokens: int,
    rerank_model: str,
    rerank_prompt_tokens: int,
    rerank_completion_tokens: int,
    resolve_model: str = "",
    resolve_prompt_tokens: int = 0,
    resolve_completion_tokens: int = 0,
) -> Decimal:
    """Total COGS for one MCP tool call: search infra + embedding + rerank + resolve."""
    cost = SEARCH_COGS_USD
    cost += calculate_embedding_cogs(embedding_model, embedding_tokens)
    cost += calculate_llm_cogs(rerank_model, rerank_prompt_tokens, rerank_completion_tokens)
    if resolve_model and (resolve_prompt_tokens or resolve_completion_tokens):
        cost += calculate_llm_cogs(resolve_model, resolve_prompt_tokens, resolve_completion_tokens)
    return cost


def calculate_mcp_charge(
    embedding_model: str,
    embedding_tokens: int,
    rerank_model: str,
    rerank_prompt_tokens: int,
    rerank_completion_tokens: int,
    resolve_model: str = "",
    resolve_prompt_tokens: int = 0,
    resolve_completion_tokens: int = 0,
) -> Decimal:
    """Total user-facing charge for one MCP tool call: search + embed + rerank + resolve."""
    charge = SEARCH_CHARGE_USD
    charge += calculate_embedding_charge(embedding_model, embedding_tokens)
    charge += calculate_llm_charge(rerank_model, rerank_prompt_tokens, rerank_completion_tokens)
    if resolve_model and (resolve_prompt_tokens or resolve_completion_tokens):
        charge += calculate_llm_charge(resolve_model, resolve_prompt_tokens, resolve_completion_tokens)
    return charge
