"""Local read/seen projections — independent of immutable Gmail AI evidence.

No provider writes. Explicit local opens are acknowledged with POST after a
successful native Gmail read, and Gmail UNREAD changes are persisted by sync.
"""
import re

MID = re.compile(r"^[a-fA-F0-9]{1,64}$")


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS mail_local_seen(
        account TEXT NOT NULL,message_id TEXT NOT NULL,viewed_at INTEGER NOT NULL,
        PRIMARY KEY(account,message_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS mail_gmail_unread(
        account TEXT NOT NULL,message_id TEXT NOT NULL,
        is_unread INTEGER NOT NULL CHECK(is_unread IN(0,1)),
        checked_at INTEGER NOT NULL,PRIMARY KEY(account,message_id)
    )""")


def mark_viewed(store, account, mid):
    if not isinstance(mid,str) or not MID.fullmatch(mid):
        raise ValueError("invalid_local_seen_message_id")
    # The source has to be part of the verified local inbox. Keep operation
    # private and idempotent; never request Gmail modify or trash.
    from .viewer import allowed_source
    allowed_source(store,account.casefold(),mid)
    with store.connect() as db,db:
        initialize(db)
        db.execute("""INSERT INTO mail_local_seen VALUES(?,?,?)
            ON CONFLICT(account,message_id) DO NOTHING""",
                   (account.casefold(),mid,int(store.clock())))
    return {"status":"viewed_locally","message_id":mid,
            "gmail_modified":False,"hidden_from_smart_inbox":True}


def restore_unread_view(store,account,mid):
    # An explicitly owner-approved Mark Unread action in Gmail may surface
    # an older previously viewed email in local Smart Inbox again.
    with store.connect() as db,db:
        initialize(db)
        db.execute("DELETE FROM mail_local_seen WHERE account=? AND message_id=?",
                   (account.casefold(),mid))


def upsert_unread(db,account,mid,value,now):
    if (not isinstance(mid,str) or not MID.fullmatch(mid)
            or type(value) is not bool):
        raise ValueError("invalid_gmail_unread_event")
    initialize(db)
    db.execute("""INSERT INTO mail_gmail_unread VALUES(?,?,?,?)
        ON CONFLICT(account,message_id) DO UPDATE SET
        is_unread=excluded.is_unread,checked_at=excluded.checked_at""",
        (account.casefold(),mid,int(value),now))


def excluded_sql(alias, tables):
    # Only read states are projected; saved insights never get deleted.
    where=""
    if "mail_local_seen" in tables:
        where+=f""" AND NOT EXISTS (SELECT 1 FROM mail_local_seen seen
            WHERE seen.account={alias}.account AND seen.message_id={alias}.message_id)"""
    if "mail_gmail_unread" in tables:
        where+=f""" AND NOT EXISTS (SELECT 1 FROM mail_gmail_unread unread
            WHERE unread.account={alias}.account AND unread.message_id={alias}.message_id
              AND unread.is_unread=0)"""
    return where
