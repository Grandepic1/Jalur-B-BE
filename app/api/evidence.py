import logging
from datetime import date
from uuid import uuid4

from anyio import to_thread
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.database import get_db
from app.core.storage import get_evidence_storage
from app.models.evidence import (
    EvidenceItem,
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceItemUpdate,
    EvidenceStatsResponse,
    EvidenceType,
)
from app.models.master import Page
from app.models.user import User


router = APIRouter(prefix="/api/evidence", tags=["evidence"])
logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ATTACHMENT_SIGNATURES = {
    "application/pdf": (b"%PDF-", ".pdf"),
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "image/webp": (b"RIFF", ".webp"),
}


def _contains(column, value: str):
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


async def _get_evidence(
    db: AsyncSession, user_id: int, evidence_id: int
) -> EvidenceItem:
    evidence = await db.scalar(
        select(EvidenceItem).where(
            EvidenceItem.id == evidence_id,
            EvidenceItem.user_id == user_id,
        )
    )
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence item not found",
        )
    return evidence


def detect_attachment_type(content: bytes) -> tuple[str, str] | None:
    for content_type, (signature, extension) in ATTACHMENT_SIGNATURES.items():
        if not content.startswith(signature):
            continue
        if content_type == "image/webp" and content[8:12] != b"WEBP":
            continue
        return content_type, extension
    return None


def evidence_response(evidence: EvidenceItem) -> EvidenceItemResponse:
    response = EvidenceItemResponse.model_validate(evidence)
    if not evidence.attachment_object_path:
        return response
    try:
        response.attachment_url = get_evidence_storage().signed_download_url(
            evidence.attachment_object_path
        )
    except (BotoCoreError, ClientError, RuntimeError):
        logger.exception("Could not sign evidence attachment URL")
        response.attachment_url = None
    return response


def storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Evidence attachment storage is unavailable",
    )


@router.get("", response_model=Page[EvidenceItemResponse])
async def list_evidence(
    evidence_type: EvidenceType | None = None,
    q: str | None = Query(None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Page[EvidenceItemResponse]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from cannot be after date_to",
        )
    filters = [EvidenceItem.user_id == user.id]
    if evidence_type is not None:
        filters.append(EvidenceItem.evidence_type == evidence_type)
    if q and q.strip():
        filters.append(
            or_(
                _contains(EvidenceItem.title, q),
                _contains(EvidenceItem.user_role, q),
                _contains(EvidenceItem.description, q),
                _contains(EvidenceItem.impact, q),
            )
        )
    if date_from is not None:
        filters.append(EvidenceItem.evidence_date >= date_from)
    if date_to is not None:
        filters.append(EvidenceItem.evidence_date <= date_to)

    total = await db.scalar(
        select(func.count()).select_from(EvidenceItem).where(*filters)
    )
    items = list(
        (
            await db.scalars(
                select(EvidenceItem)
                .where(*filters)
                .order_by(
                    EvidenceItem.evidence_date.desc().nulls_last(),
                    EvidenceItem.created_at.desc(),
                    EvidenceItem.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return Page[EvidenceItemResponse](
        items=[evidence_response(item) for item in items],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=EvidenceStatsResponse)
async def get_evidence_stats(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceStatsResponse:
    rows = (
        await db.execute(
            select(EvidenceItem.evidence_type, func.count())
            .where(EvidenceItem.user_id == user.id)
            .group_by(EvidenceItem.evidence_type)
        )
    ).all()
    by_type = {evidence_type: count for evidence_type, count in rows}
    human_authored = await db.scalar(
        select(func.count())
        .select_from(EvidenceItem)
        .where(EvidenceItem.user_id == user.id, EvidenceItem.ai_generated.is_(False))
    )
    total = sum(by_type.values())
    return EvidenceStatsResponse(
        total=total,
        by_type=by_type,
        human_authored=human_authored or 0,
        ai_generated=total - (human_authored or 0),
    )


@router.post(
    "",
    response_model=EvidenceItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evidence(
    payload: EvidenceItemCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceItemResponse:
    evidence = EvidenceItem(
        user_id=user.id,
        **payload.model_dump(exclude={"ai_generated"}),
        ai_generated=False,
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    return evidence_response(evidence)


@router.get("/{evidence_id}", response_model=EvidenceItemResponse)
async def get_evidence(
    evidence_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceItemResponse:
    return evidence_response(await _get_evidence(db, user.id, evidence_id))


@router.patch("/{evidence_id}", response_model=EvidenceItemResponse)
async def update_evidence(
    evidence_id: int,
    payload: EvidenceItemUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceItemResponse:
    evidence = await _get_evidence(db, user.id, evidence_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(evidence, field, value)
    await db.commit()
    await db.refresh(evidence)
    return evidence_response(evidence)


@router.post("/{evidence_id}/attachment", response_model=EvidenceItemResponse)
async def upload_evidence_attachment(
    evidence_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceItemResponse:
    evidence = await _get_evidence(db, user.id, evidence_id)
    content = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Attachment must be 10 MB or smaller",
        )
    detected_type = detect_attachment_type(content)
    if detected_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Attachment must be a PDF, PNG, JPG, or WEBP file",
        )

    content_type, extension = detected_type
    object_path = (
        f"users/{user.id}/evidence/{evidence.id}/{uuid4().hex}{extension}"
    )
    try:
        storage = get_evidence_storage()
        await to_thread.run_sync(storage.upload, object_path, content, content_type)
    except (BotoCoreError, ClientError, RuntimeError):
        logger.exception("Could not upload evidence attachment")
        raise storage_unavailable() from None

    previous_path = evidence.attachment_object_path
    evidence.attachment_object_path = object_path
    evidence.attachment_url = None
    try:
        await db.commit()
        await db.refresh(evidence)
    except Exception:
        await db.rollback()
        try:
            await to_thread.run_sync(storage.delete, object_path)
        except (BotoCoreError, ClientError):
            logger.exception("Could not clean up an uncommitted evidence attachment")
        raise

    if previous_path:
        try:
            await to_thread.run_sync(storage.delete, previous_path)
        except (BotoCoreError, ClientError):
            logger.exception("Could not remove the replaced evidence attachment")
    return evidence_response(evidence)


@router.delete("/{evidence_id}/attachment", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence_attachment(
    evidence_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    evidence = await _get_evidence(db, user.id, evidence_id)
    object_path = evidence.attachment_object_path
    if object_path is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        storage = get_evidence_storage()
        await to_thread.run_sync(storage.delete, object_path)
    except (BotoCoreError, ClientError, RuntimeError):
        logger.exception("Could not delete evidence attachment")
        raise storage_unavailable() from None
    evidence.attachment_object_path = None
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence(
    evidence_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    evidence = await _get_evidence(db, user.id, evidence_id)
    if evidence.attachment_object_path:
        try:
            storage = get_evidence_storage()
            await to_thread.run_sync(storage.delete, evidence.attachment_object_path)
        except (BotoCoreError, ClientError, RuntimeError):
            logger.exception("Could not delete evidence attachment")
            raise storage_unavailable() from None
    await db.execute(
        delete(EvidenceItem).where(
            EvidenceItem.id == evidence_id,
            EvidenceItem.user_id == user.id,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
