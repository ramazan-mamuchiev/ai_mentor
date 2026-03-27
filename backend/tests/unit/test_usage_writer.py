"""Unit tests for billing usage_writer module."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.billing.usage_writer import write_usage_log


def _mock_session_context():
    """Create a mock async session context manager."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_cm, mock_session


class TestWriteUsageLog:
    @pytest.mark.asyncio
    async def test_chat_completion_writes_record(self):
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="chat",
                action="chat_completion",
                request_id="test-uuid-1234",
                llm_provider="openai",
                llm_model="gemini-2.5-flash",
                prompt_tokens=1000,
                completion_tokens=500,
                context_chunks=5,
                context_tokens=3000,
                query_tokens=12,
                history_tokens=800,
                system_prompt_tokens=400,
                query_text="how to open a door",
                duration_ms=1500.0,
                llm_ms=1200.0,
            )

        mock_session.add.assert_called_once()
        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.channel == "chat"
        assert usage_log.action == "chat_completion"
        assert usage_log.request_id == "test-uuid-1234"
        assert usage_log.prompt_tokens == 1000
        assert usage_log.completion_tokens == 500
        assert usage_log.total_tokens == 1500
        assert usage_log.query_tokens == 12
        assert usage_log.history_tokens == 800
        assert usage_log.system_prompt_tokens == 400
        assert usage_log.cogs_usd > 0
        assert usage_log.charge_usd > 0
        assert usage_log.charge_usd > usage_log.cogs_usd
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mcp_search_writes_record(self):
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="mcp",
                action="search_documentation",
                request_id="test-uuid-5678",
                query_text="ONVIF PTZ",
                query_tokens=3,
                result_count=5,
                response_tokens=2000,
                response_length=8000,
                duration_ms=200.0,
            )

        mock_session.add.assert_called_once()
        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.channel == "mcp"
        assert usage_log.action == "search_documentation"
        assert usage_log.query_tokens == 3
        assert usage_log.cogs_usd == Decimal("0.0003")
        assert usage_log.charge_usd == Decimal("0.0005")

    @pytest.mark.asyncio
    async def test_list_products_zero_cost(self):
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="mcp",
                action="list_products",
                request_id="test-uuid-9999",
                result_count=10,
                cogs_usd=Decimal("0"),
                charge_usd=Decimal("0"),
            )

        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.cogs_usd == Decimal("0")
        assert usage_log.charge_usd == Decimal("0")

    @pytest.mark.asyncio
    async def test_db_error_does_not_propagate(self):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=Exception("DB connection failed"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="chat",
                action="chat_completion",
                request_id="test-uuid-fail",
                llm_model="gemini-2.5-flash",
                prompt_tokens=100,
                completion_tokens=50,
            )

    @pytest.mark.asyncio
    async def test_unknown_model_logs_warning_and_zero_cost(self):
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="chat",
                action="chat_completion",
                request_id="test-uuid-unknown",
                llm_model="unknown-model",
                prompt_tokens=1000,
                completion_tokens=500,
            )

        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.cogs_usd == Decimal("0")
        assert usage_log.charge_usd == Decimal("0")

    @pytest.mark.asyncio
    async def test_explicit_costs_override_calculation(self):
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="chat",
                action="chat_completion",
                request_id="test-uuid-override",
                llm_model="gemini-2.5-flash",
                prompt_tokens=1000,
                completion_tokens=500,
                cogs_usd=Decimal("0.50"),
                charge_usd=Decimal("0.99"),
            )

        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.cogs_usd == Decimal("0.50")
        assert usage_log.charge_usd == Decimal("0.99")

    @pytest.mark.asyncio
    async def test_partial_override_cogs_only(self):
        """When only cogs_usd is provided, charge_usd is auto-calculated."""
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="chat",
                action="chat_completion",
                request_id="test-uuid-partial",
                llm_model="gemini-2.5-flash",
                prompt_tokens=1000,
                completion_tokens=500,
                cogs_usd=Decimal("0.50"),
            )

        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.cogs_usd == Decimal("0.50")
        assert usage_log.charge_usd > 0

    @pytest.mark.asyncio
    async def test_api_key_id_and_tenant_id_persisted(self):
        """api_key_id and tenant_id are forwarded to UsageLog."""
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="mcp",
                action="search_documentation",
                request_id="test-uuid-audit",
                query_text="ONVIF",
                result_count=3,
                duration_ms=100.0,
                tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                api_key_id="11111111-2222-3333-4444-555555555555",
            )

        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.tenant_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert usage_log.api_key_id == "11111111-2222-3333-4444-555555555555"

    @pytest.mark.asyncio
    async def test_api_key_id_none_when_jwt(self):
        """api_key_id defaults to None for JWT-authenticated requests."""
        mock_cm, mock_session = _mock_session_context()

        with patch("app.billing.usage_writer.async_session", return_value=mock_cm):
            await write_usage_log(
                channel="chat",
                action="chat_completion",
                request_id="test-uuid-jwt",
                llm_model="gemini-2.5-flash",
                prompt_tokens=100,
                completion_tokens=50,
                tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            )

        usage_log = mock_session.add.call_args[0][0]
        assert usage_log.tenant_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert usage_log.api_key_id is None
