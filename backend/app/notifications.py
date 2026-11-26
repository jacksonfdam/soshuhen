"""Record what a discovery run found new, and tell the browser.

One row is one series and one run: a source coming back after a week offline
is still one notification with a wide range, not forty popups.

Read rows are pruned here rather than on a schedule. There is no maintenance
cron to hang it on, and the only writer of this table is already running.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import NotificationKind
from app.queue.repo import NOTIFY_CHANNEL

EVENT = "notification.new"
READ_EVENT = "notification.read"
RETENTION = timedelta(days=30)


async def record(
    session: AsyncSession,
    series_id: int,
    kind: NotificationKind,
    numbers: Sequence[Decimal],
    *,
    volume_number: Decimal | None = None,
) -> int | None:
    """Write one notification for `numbers` and announce it on commit.

    Commits nothing: the caller's transaction holds the rows that are new, and
    a notification must not outlive a run that rolls them back.
    """
    if not numbers:
        return None
    notification_id = (
        await session.execute(
            text(
                """
                insert into notification
                       (series_id, kind, count, first_number, last_number, volume_number)
                values (:series_id, :kind, :count, :first, :last,
                        cast(:volume_number as numeric))
                returning id
                """
            ),
            {
                "series_id": series_id,
                "kind": str(kind),
                "count": len(numbers),
                "first": min(numbers),
                "last": max(numbers),
                "volume_number": volume_number,
            },
        )
    ).scalar_one()
    await session.execute(
        # Gone once everyone it was news to has read it, and the last of them
        # did so long enough ago. Someone who has yet to read it keeps it.
        text(
            """
            delete from notification n
             where exists (select 1 from notification_read r where r.notification_id = n.id)
               and not exists (
                   select 1 from notification_read r
                    where r.notification_id = n.id
                      and r.read_at >= now() - make_interval(days => :days))
               and not exists (
                   select 1 from profile p
                    where (exists (select 1 from list_entry le
                                    where le.series_id = n.series_id and le.profile_id = p.id)
                           or (p.is_manager
                               and not exists (select 1 from list_entry le
                                                where le.series_id = n.series_id)))
                      and not exists (select 1 from notification_read r
                                       where r.notification_id = n.id
                                         and r.profile_id = p.id))
            """
        ),
        {"days": RETENTION.days},
    )
    # A nudge, not the content: the browser re-reads the list, so the API stays
    # the one answer to what a notification says.
    payload = json.dumps(
        {
            "event": EVENT,
            "notification_id": notification_id,
            "series_id": series_id,
            "kind": str(kind),
            "ts": datetime.now(UTC).isoformat(),
        }
    )
    await _notify(session, payload)
    return int(notification_id)


async def announce_read(session: AsyncSession, notification_id: int | None) -> None:
    """Tell every open tab that a row, or with None every row, has been read.

    The tab that marked it knows already; without this the others keep a badge
    for news the user has seen until the next notification arrives, which can
    be days.
    """
    payload = json.dumps(
        {
            "event": READ_EVENT,
            "notification_id": notification_id,
            "ts": datetime.now(UTC).isoformat(),
        }
    )
    await _notify(session, payload)


async def _notify(session: AsyncSession, payload: str) -> None:
    await session.execute(
        text("select pg_notify(:channel, :payload)"),
        {"channel": NOTIFY_CHANNEL, "payload": payload},
    )
