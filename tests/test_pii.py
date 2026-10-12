import pytest

from app.observability.pii import  redact_pii
from app.observability.presidio import redact_pii_presidio

def test_pii():
    # Исходный текст с PII (включая перенос строки в номере карты)
    raw_text = "Мой email ivan@mail.ru, тел +7 (999) 123-45-67, карта 4111 1111 1111 1111"

    prompt_preview_reg = redact_pii(raw_text)
    expected_text_reg = "Мой email [EMAIL], тел [PHONE], карта [CARD]"

    prompt_preview_presidio = redact_pii_presidio(raw_text)
    expected_text_presidio="Мой email [PII], тел [PII], карта [PII]"
    assert prompt_preview_reg == expected_text_reg
    assert prompt_preview_presidio == expected_text_presidio