"""Private local evidence snapshot; no OAuth calls, inference or schema writes."""

from .private import config


def snapshot(store):
    result = {
        "configuration": "absent",
        "authorization": "not_checked",
        "daily_at": None,
        "timezone": None,
        "local_send_enabled": False,
        "history": "not_checked",
        "sync_enabled": False,
        "sync": None,
        "latest_attempt": None,
        "latest_success": None,
    }
    path = store.directory / "mail" / "config.json"
    if not path.exists() and not path.is_symlink():
        return result
    try:
        cfg = config(store)
    except Exception:
        result["configuration"] = "invalid"
        return result
    result.update(
        configuration="configured",
        daily_at=cfg.daily_at,
        timezone=cfg.timezone,
        local_send_enabled=cfg.send_enabled,
        sync_enabled=cfg.sync_enabled,
    )
    from .history import local_status

    result["sync"] = local_status(store, cfg.account)
    try:
        with store.connect() as db:
            db.execute("BEGIN")
            tables = {
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "mail_jobs" not in tables and "mail_meta" not in tables:
                result["history"] = "available"
                return result
            version = db.execute(
                "SELECT value FROM mail_meta WHERE key='version'"
            ).fetchone()
            if version is None or version[0] != "1":
                result["history"] = "unavailable"
                return result
            for key, condition in (
                ("latest_attempt", ""),
                ("latest_success", " AND status='succeeded'"),
            ):
                row = db.execute(
                    "SELECT status,start,end,count,updated FROM mail_jobs WHERE account=?"
                    + condition
                    + " ORDER BY updated DESC,id DESC LIMIT 1",
                    (cfg.account.casefold(),),
                ).fetchone()
                if row:
                    result[key] = dict(row)
            result["history"] = "available"
    except Exception:
        result.update(history="unavailable", latest_attempt=None, latest_success=None)
    return result
