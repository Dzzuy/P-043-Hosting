"""Local, customer-scoped pseudonymization. No plaintext fallback or tracing."""

from __future__ import annotations

import json
import re

from cryptography.fernet import Fernet

from src.config import get_settings
from src.observability import private_customer_context
from src.services.llm import get_llm


class PIIUnavailableError(ValueError):
    pass


class CustomerPII:
    def __init__(self, encrypted: str | None = None, *, customer_id: str | None = None):
        key = get_settings().sales_pii_key.get_secret_value()
        self.customer_id = customer_id
        try:
            self.cipher = Fernet(key.encode())
            data = (
                json.loads(self.cipher.decrypt(encrypted.encode()))
                if encrypted
                else {"customer_id": customer_id, "mapping": {}}
            )
            if data["customer_id"] != customer_id:
                raise ValueError("Wrong customer scope")
            self.mapping = data["mapping"]
            self._initial_mapping = dict(self.mapping)
        except Exception:
            raise PIIUnavailableError("Cần cấu hình SALES_PII_KEY hợp lệ để xử lý dữ liệu khách.") from None

    @property
    def has_new_tokens(self) -> bool:
        return self.mapping != self._initial_mapping

    def encrypt(self):
        return self.cipher.encrypt(
            json.dumps({"customer_id": self.customer_id, "mapping": self.mapping}, ensure_ascii=False).encode()
        ).decode()

    def _token(self, kind, value):
        def normalized(original):
            digits = re.sub(r"\D", "", original)
            if kind == "SDT" and digits.startswith("84") and len(digits) == 11:
                return "0" + digits[2:]
            return digits

        for token, original in self.mapping.items():
            same = normalized(original) == normalized(value) if kind in ("SDT", "CCCD") else original == value
            if token.startswith(f"[{kind}_") and same:
                return token
        token = f"[{kind}_{1 + sum(k.startswith(f'[{kind}_') for k in self.mapping)}]"
        self.mapping[token] = value
        return token

    def mask(self, text: str):
        # Identity numbers stay private without labels. Birth dates require birth
        # context, otherwise an appointment date or a price could be overmasked.
        for token, original in sorted(self.mapping.items(), key=lambda pair: -len(pair[1])):
            if not token.startswith("[NGAY_SINH_"):
                text = re.sub(r"(?<!\d)" + re.escape(original) + r"(?!\d)", lambda _: token, text)
        # Recognize contextual identity numbers before generic telephone detection.
        text = re.sub(
            r"(?i)(\b(?:cccd(?:_number)?|căn cước(?: công dân)?|can cuoc(?: cong dan)?)\s*(?:số|so)?[\s\"']*[:#=-]?[\s\"']*)(\d(?:[ .-]?\d){11})(?!\d)",
            lambda m: m[1] + self._token("CCCD", m[2]),
            text,
        )
        # Dates are private only in birth context; appointment/contract dates stay intact.
        text = re.sub(
            r"(?i)((?:ngày tháng năm sinh|ngày sinh|ngay sinh|sinh ngày|sinh ngay|sinh năm|sinh nam|năm sinh|nam sinh|sinh nhật|sinh nhat|date of birth|date_of_birth|birth_date|birth_year|dob|born|sinh|\bsn\b)[\s\"']*(?:là\s+)?[:=]?[\s\"']*)((?:ngày\s+)?\d{1,2}\s+tháng\s+\d{1,2}(?:\s+năm\s+\d{4})?|tháng\s+\d{1,2}(?:\s+năm\s+\d{4})?|ngày\s+\d{1,2}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}(?:[-/.]\d{2,4})?|\d{4}|\d{1,2})",
            lambda m: m[1] + self._token("NGAY_SINH", m[2]),
            text,
        )

        def phone(m):
            value = m[0]
            digits = re.sub(r"\D", "", value)
            if (
                (value.startswith("+") or value.startswith("("))
                and 8 <= len(digits) <= 15
                or (digits.startswith("00") and 10 <= len(digits) <= 17)
                or (9 <= len(digits) <= 11 and digits.startswith("0"))
            ):
                return self._token("SDT", value)
            return value

        text = re.sub(r"(?<![\w\d])(?:\+\d|0\d|\(\d)(?:[ .()-]{0,4}\d){7,16}(?![\w\d])", phone, text)
        text = re.sub(
            r"(?i)((?:phone|telephone|mobile|điện thoại|dien thoai|sđt|sdt)[\s\"']*[:=]?[\s\"']*)(\+?\(?\d[\d ()-]{6,22}\d)",
            lambda m: m[1] + self._token("SDT", m[2]) if 8 <= len(re.sub(r"\D", "", m[2])) <= 15 else m[0],
            text,
        )
        for token, original in sorted(self.mapping.items(), key=lambda pair: -len(pair[1])):
            if not token.startswith("[NGAY_SINH_"):
                text = re.sub(r"(?<!\d)" + re.escape(original) + r"(?!\d)", lambda _: token, text)
        return text

    def restore(self, text: str):
        def replace(m):
            if m[0] not in self.mapping:
                raise ValueError("Phản hồi chứa mã PII không hợp lệ.")
            return self.mapping[m[0]]

        return re.sub(r"\[(?:SDT|NGAY_SINH|CCCD)_\d+\]", replace, text)

    def private_payload(self, value):
        """Mask leaves while preserving native JSON types for money and dates."""
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if isinstance(item, (str, int)) and re.fullmatch(
                    r"(?i)(dob|birth_date|birth_year|date_of_birth|ngày sinh|năm sinh|cccd(?:_number)?|phone|telephone|mobile)",
                    key,
                ):
                    combined = self.mask(f"{key}: {item}")
                    result[key] = combined.split(": ", 1)[1]
                else:
                    result[key] = self.private_payload(item)
            return result
        if isinstance(value, list):
            return [self.private_payload(item) for item in value]
        return self.mask(value) if isinstance(value, str) else value

    async def ask(self, system, payload, schema):
        """Mask before model construction; disable inherited LangSmith tracing too."""
        self.private_payload(payload)  # Discover contextual identifiers across leaves first.
        masked = json.dumps(self.private_payload(payload), ensure_ascii=False, default=str)
        try:
            with private_customer_context():
                model = get_llm(temperature=0, max_tokens=6000, max_retries=0)
                result = await model.with_structured_output(schema, method="json_schema").ainvoke(
                    [{"role": "system", "content": system}, {"role": "user", "content": masked}],
                    config={"callbacks": [], "tags": ["customer-private"]},
                )
            return schema.model_validate(result)
        except Exception:
            # Provider/schema exceptions can contain messages or model output.
            raise ValueError("Không thể xử lý dữ liệu khách lúc này. Bản đã lưu được giữ nguyên.") from None
