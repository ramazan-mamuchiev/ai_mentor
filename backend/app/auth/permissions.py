"""Permission engine for RBAC roles.

Merges permissions from multiple roles into effective permissions dict.
Provides helpers to check feature flags and read numeric limits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Role


def merge_permissions(roles: list[Role]) -> dict:
    """Merge permissions from multiple roles into effective permissions.

    Rules:
    - features: OR (any True wins)
    - limits: MAX (highest limit wins; missing key = unlimited wins)
    - chat_context.allowed_query_types: UNION
    - chat_context.suggestion_template_role: from highest-priority role
    """
    if not roles:
        return {"features": {}, "limits": {}, "chat_context": {}}

    sorted_roles = sorted(roles, key=lambda r: r.priority, reverse=True)

    merged_features: dict[str, bool] = {}
    merged_limits: dict[str, int | None] = {}
    merged_query_types: set[str] = set()
    suggestion_role: str = "default"

    for role in sorted_roles:
        perms = role.permissions or {}

        for key, val in perms.get("features", {}).items():
            if val or key not in merged_features:
                merged_features[key] = bool(val)

        for key, val in perms.get("limits", {}).items():
            existing = merged_limits.get(key)
            if existing is None and key in merged_limits:
                pass  # already unlimited
            elif val is None:
                merged_limits[key] = None  # unlimited wins
            elif key not in merged_limits:
                merged_limits[key] = val
            elif existing is not None:
                merged_limits[key] = max(existing, val)

        ctx = perms.get("chat_context", {})
        merged_query_types.update(ctx.get("allowed_query_types", []))

    top_ctx = sorted_roles[0].permissions.get("chat_context", {}) if sorted_roles else {}
    suggestion_role = top_ctx.get("suggestion_template_role", "default")

    return {
        "features": merged_features,
        "limits": merged_limits,
        "chat_context": {
            "allowed_query_types": sorted(merged_query_types),
            "suggestion_template_role": suggestion_role,
        },
    }


def has_permission(effective: dict, key: str) -> bool:
    """Check a single feature permission (e.g. 'documents.upload')."""
    return bool(effective.get("features", {}).get(key, False))


def get_limit(effective: dict, key: str) -> int | None:
    """Get a numeric limit (None = unlimited)."""
    return effective.get("limits", {}).get(key)
