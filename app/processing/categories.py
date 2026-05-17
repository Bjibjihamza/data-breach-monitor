from __future__ import annotations

INFORMATIONAL_MENTION = "informational_mention"
EXPOSURE_SIGNAL = "exposure_signal"
SECRET_EXPOSURE = "secret_exposure"

STORABLE_CATEGORIES = frozenset({EXPOSURE_SIGNAL, SECRET_EXPOSURE})
