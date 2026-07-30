from __future__ import annotations

from decimal import Decimal


def _emv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
    crc = 0xFFFF
    for char in payload.encode("ascii"):
        crc ^= char << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def format_phone_for_promptpay(phone: str) -> str:
    normalized = "".join(char for char in phone if char.isdigit() or char == "+")
    if normalized.startswith("+66"):
        normalized = f"0{normalized[3:]}"
    if not normalized.startswith("0") or len("".join(char for char in normalized if char.isdigit())) != 10:
        raise ValueError("PromptPay phone must contain 10 digits")
    digits = "".join(char for char in normalized if char.isdigit())
    return f"0066{digits[1:]}"


def generate_promptpay_payload(
    target: str,
    amount: Decimal | None = None,
) -> str:
    digits = "".join(char for char in target if char.isdigit() or char == "+")
    if len("".join(char for char in digits if char.isdigit())) == 10 or digits.startswith("+66"):
        merchant_target = format_phone_for_promptpay(target)
    elif len("".join(char for char in digits if char.isdigit())) == 13:
        merchant_target = "".join(char for char in digits if char.isdigit())
    else:
        raise ValueError("PromptPay target must be a Thai mobile number or 13-digit tax ID")

    poi = "12" if amount is not None else "11"
    merchant_info = _emv("00", "A000000677010111") + _emv("01", merchant_target)
    payload = "".join(
        [
            _emv("00", "01"),
            _emv("01", poi),
            _emv("29", merchant_info),
            _emv("53", "764"),
            _emv("58", "TH"),
        ]
    )
    if amount is not None:
        payload += _emv("54", f"{Decimal(amount):.2f}")
    payload_with_crc = f"{payload}6304"
    return f"{payload_with_crc}{_crc16_ccitt(payload_with_crc)}"
