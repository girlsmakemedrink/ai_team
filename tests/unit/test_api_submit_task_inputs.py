"""SubmitTaskRequest must accept and forward an optional `inputs` dict
so brainstorm-products (and future structured-intent flows) can pass
typed metadata to TL without encoding it in description text."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.main import SubmitTaskRequest


def test_inputs_default_is_none() -> None:
    req = SubmitTaskRequest(title="t", description="d")
    assert req.inputs is None


def test_inputs_accepts_dict_with_nested_values() -> None:
    payload = {
        "intent": "brainstorm_products",
        "niches": ["dev_tools", "b2b_smb"],
        "candidates_per_niche": 5,
        "constraints": {"solo_developer": True, "ttfr_max_months": 6},
    }
    req = SubmitTaskRequest(title="t", description="d", inputs=payload)
    assert req.inputs == payload


def test_inputs_rejects_non_dict() -> None:
    with pytest.raises(ValidationError):
        SubmitTaskRequest(title="t", description="d", inputs=["not", "a", "dict"])
