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
        text("delete from notification where read_at < now() - make_interval(days => :days)"),
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
    await session.execute(
        text("select pg_notify(:channel, :payload)"),
        {"channel": NOTIFY_CHANNEL, "payload": payload},
    )
    return int(notification_id)
