"""Shared owner-triggered local draft service; provider send remains separate."""

import json
import re

from .contracts import MailError
from .inference import LocalModel
from .private import config, locked
from .provider import Gmail
from .state import MailState
from .viewer import allowed_source
from .workflows import reply_draft


def generate(store, mid, language):
    if (
        not isinstance(mid, str)
        or not re.fullmatch("[a-fA-F0-9]{1,64}", mid)
        or language not in {"ar", "en"}
    ):
        raise MailError("invalid_reply_request")
    with locked(store):
        cfg = config(store)
        if allowed_source(store, cfg.account.casefold(), mid) is None:
            raise MailError("reply_manual_review_required")
        api = Gmail.open(store, cfg)
        model = LocalModel(cfg)
        try:
            instruction = (
                "Draft a concise professional Egyptian Arabic reply. "
                if language == "ar"
                else "Draft a concise professional English reply. "
            )
            instruction += "Do not invent any commitments, dates or prices. No send; owner will inspect and edit."
            draft_id = reply_draft(store, cfg, api, model, mid, instruction)
            saved = json.loads(MailState(store).draft(draft_id)["payload"])
            return {
                "status": "draft_saved_local_only",
                "draft_id": draft_id,
                "recipient": saved["recipient"],
                "subject": saved["subject"],
                "body": saved["body"],
                "sent": False,
                "owner_review_required": True,
            }
        finally:
            model.close()
            api.close()
