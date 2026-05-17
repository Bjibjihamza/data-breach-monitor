from __future__ import annotations

import re

from bs4 import BeautifulSoup


def clean_text(text: str | None) -> str:
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")
    plain_text = soup.get_text(separator=" ")
    plain_text = re.sub(r"\s+", " ", plain_text)
    return plain_text.strip()
