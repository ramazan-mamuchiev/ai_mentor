"""Unit tests for billing pricing module."""

from decimal import Decimal

from app.billing.pricing import (
    MODEL_CHARGE,
    MODEL_COGS,
    SEARCH_CHARGE_USD,
    SEARCH_COGS_USD,
    calculate_llm_charge,
    calculate_llm_cogs,
    calculate_search_charge,
    calculate_search_cogs,
)


class TestCalculateLlmCogs:
    def test_gemini_flash_cogs(self):
        cost = calculate_llm_cogs("gemini-2.5-flash", prompt_tokens=1000, completion_tokens=500)
        expected_input = Decimal("0.30") * Decimal("1000") / Decimal("1000000")
        expected_output = Decimal("2.50") * Decimal("500") / Decimal("1000000")
        assert cost == (expected_input + expected_output).quantize(Decimal("0.00000001"))

    def test_gemini_pro_cogs(self):
        cost = calculate_llm_cogs("gemini-2.5-pro", prompt_tokens=5000, completion_tokens=2000)
        expected_input = Decimal("1.25") * Decimal("5000") / Decimal("1000000")
        expected_output = Decimal("10.00") * Decimal("2000") / Decimal("1000000")
        assert cost == (expected_input + expected_output).quantize(Decimal("0.00000001"))

    def test_unknown_model_returns_zero(self):
        cost = calculate_llm_cogs("unknown-model-xyz", prompt_tokens=1000, completion_tokens=500)
        assert cost == Decimal("0")

    def test_zero_tokens_returns_zero(self):
        cost = calculate_llm_cogs("gemini-2.5-flash", prompt_tokens=0, completion_tokens=0)
        assert cost == Decimal("0E-8")

    def test_large_token_count(self):
        cost = calculate_llm_cogs("gemini-2.5-flash", prompt_tokens=1_000_000, completion_tokens=1_000_000)
        expected = Decimal("0.30") + Decimal("2.50")
        assert cost == expected.quantize(Decimal("0.00000001"))


class TestCalculateLlmCharge:
    def test_gemini_flash_charge(self):
        charge = calculate_llm_charge("gemini-2.5-flash", prompt_tokens=1000, completion_tokens=500)
        expected_input = Decimal("0.50") * Decimal("1000") / Decimal("1000000")
        expected_output = Decimal("4.00") * Decimal("500") / Decimal("1000000")
        assert charge == (expected_input + expected_output).quantize(Decimal("0.00000001"))

    def test_charge_exceeds_cogs(self):
        """User-facing charge must always be >= our COGS for the same model."""
        for model in MODEL_COGS:
            if model in MODEL_CHARGE:
                cogs = calculate_llm_cogs(model, prompt_tokens=10000, completion_tokens=5000)
                charge = calculate_llm_charge(model, prompt_tokens=10000, completion_tokens=5000)
                assert charge >= cogs, f"Charge < COGS for {model}: {charge} < {cogs}"

    def test_unknown_model_returns_zero(self):
        charge = calculate_llm_charge("unknown-model-xyz", prompt_tokens=1000, completion_tokens=500)
        assert charge == Decimal("0")


class TestModelPricingStructure:
    def test_all_cogs_models_have_required_keys(self):
        for model_name, pricing in MODEL_COGS.items():
            assert "input_per_1m" in pricing, f"{model_name} missing input_per_1m"
            assert "output_per_1m" in pricing, f"{model_name} missing output_per_1m"
            assert isinstance(pricing["input_per_1m"], Decimal)
            assert isinstance(pricing["output_per_1m"], Decimal)

    def test_all_charge_models_have_required_keys(self):
        for model_name, pricing in MODEL_CHARGE.items():
            assert "input_per_1m" in pricing, f"{model_name} missing input_per_1m"
            assert "output_per_1m" in pricing, f"{model_name} missing output_per_1m"
            assert isinstance(pricing["input_per_1m"], Decimal)
            assert isinstance(pricing["output_per_1m"], Decimal)

    def test_charge_models_match_cogs_models(self):
        assert set(MODEL_COGS.keys()) == set(MODEL_CHARGE.keys())


class TestSearchCost:
    def test_cogs_returns_fixed_cost(self):
        cost = calculate_search_cogs()
        assert cost == SEARCH_COGS_USD
        assert isinstance(cost, Decimal)

    def test_charge_returns_fixed_cost(self):
        charge = calculate_search_charge()
        assert charge == SEARCH_CHARGE_USD
        assert isinstance(charge, Decimal)

    def test_search_charge_exceeds_cogs(self):
        assert calculate_search_charge() >= calculate_search_cogs()

    def test_search_costs_are_positive(self):
        assert calculate_search_cogs() > 0
        assert calculate_search_charge() > 0
