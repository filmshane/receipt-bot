import json

import pytest

from receipt_bot.llm.grok_client import _parse_json_content
from receipt_bot.models import ExtractionResult


def test_parse_json_fenced():
    raw = '```json\n{"is_receipt": true, "total": 12.5, "category": "Food", "confidence": 0.9}\n```'
    d = _parse_json_content(raw)
    ext = ExtractionResult.model_validate(d)
    assert ext.is_receipt is True
    assert ext.total == 12.5
