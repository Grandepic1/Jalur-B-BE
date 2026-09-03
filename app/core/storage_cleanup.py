import asyncio
import logging
from datetime import UTC, datetime, timedelta

from anyio import to_thread
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.storage import get_private_storage
from app.models.cv import UserCV
from app.models.storage import StorageDeletionJob

logger = logging.getLogger(__name__)


async def enqueue_storage_deletion(
    db: AsyncSession,
    object_path: str,
    delay: timedelta = timedelta(0),
) -> None:
    await db.execute(
        insert(StorageDeletionJob)
        .values(
            object_path=object_path,
            not_before=datetime.now(UTC) + delay,
        )
        .on_conflict_do_nothing(index_elements=[StorageDeletionJob.object_path])
    )


async def cancel_storage_deletion(db: AsyncSession, object_path: str) -> None:
    await db.execute(
        delete(StorageDeletionJob).where(
            StorageDeletionJob.object_path == object_path
        )
    )


async def process_storage_deletion_path(
    db: AsyncSession, object_path: str
) -> bool:
    job = await db.scalar(
        select(StorageDeletionJob)
        .where(StorageDeletionJob.object_path == object_path)
        .with_for_update()
    )
    if job is None:
        return True
    referenced = await db.scalar(
        select(UserCV.id).where(UserCV.storage_object_path == object_path)
    )
    if referenced is not None:
        await db.delete(job)
        await db.commit()
        return True
    try:
        storage = get_private_storage()
        await to_thread.run_sync(storage.delete, object_path)
    except (BotoCoreError, ClientError, RuntimeError):
        logger.exception("Could not process private storage deletion")
        return False
    await db.delete(job)
    await db.commit()
    return True


async def process_pending_storage_deletions() -> None:
    async with AsyncSessionLocal() as db:
        jobs = list(
            (
                await db.scalars(
                    select(StorageDeletionJob)
                    .where(StorageDeletionJob.not_before <= datetime.now(UTC))
                    .order_by(StorageDeletionJob.id)
                    .limit(25)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        if not jobs:
            return
        try:
            storage = get_private_storage()
        except RuntimeError:
            logger.exception("Private storage cleanup is not configured")
            return
        for job in jobs:
            referenced = await db.scalar(
                select(UserCV.id).where(
                    UserCV.storage_object_path == job.object_path
                )
            )
            if referenced is not None:
                await db.delete(job)
                continue
            try:
                await to_thread.run_sync(storage.delete, job.object_path)
            except (BotoCoreError, ClientError):
                job.attempts += 1
                logger.exception("Could not process queued private storage deletion")
            else:
                await db.delete(job)
        await db.commit()


async def storage_cleanup_worker() -> None:
    while True:
        try:
            await process_pending_storage_deletions()
        except Exception:
            logger.exception("Private storage cleanup worker failed")
        await asyncio.sleep(300)
