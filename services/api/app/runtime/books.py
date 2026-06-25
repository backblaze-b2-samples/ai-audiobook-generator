import logging

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.repo import JobQueueError, TTSError
from app.runtime.book_auth import BookPrincipal, require_book_principal
from app.service.books import (
    BookAccessError,
    BookKeyError,
    BookNotFoundError,
    book_activity,
    book_stats,
    chapter_stream_url,
    delete_book,
    get_book,
    list_books,
    master_download_url,
)
from app.service.narration import (
    cancel_narration_for_book,
    create_book,
    enqueue_narration_job,
    list_voices,
)
from app.types import (
    BookDetail,
    BookStats,
    BookSummary,
    CreateBookRequest,
    DailyNarrationHours,
    Voice,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/voices", response_model=list[Voice])
async def list_voices_endpoint():
    try:
        return await run_in_threadpool(list_voices)
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None


@router.get("/books", response_model=list[BookSummary])
async def list_books_endpoint(principal: BookPrincipal = Depends(require_book_principal)):
    return await run_in_threadpool(list_books, owner_id=principal.owner_id)


@router.get("/books/stats", response_model=BookStats)
async def book_stats_endpoint(principal: BookPrincipal = Depends(require_book_principal)):
    return await run_in_threadpool(book_stats, owner_id=principal.owner_id)


@router.get("/books/stats/activity", response_model=list[DailyNarrationHours])
async def book_activity_endpoint(
    days: int = 7,
    principal: BookPrincipal = Depends(require_book_principal),
):
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 90")
    return await run_in_threadpool(book_activity, days=days, owner_id=principal.owner_id)


@router.post("/books", response_model=BookDetail, status_code=202)
async def create_book_endpoint(
    request: CreateBookRequest,
    principal: BookPrincipal = Depends(require_book_principal),
):
    book = None
    try:
        book = await run_in_threadpool(create_book, request, principal.owner_id)
        await run_in_threadpool(enqueue_narration_job, book.id)
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except JobQueueError as e:
        if book:
            try:
                await run_in_threadpool(delete_book, book.id)
            except Exception:
                logger.exception("Failed to clean up audiobook after enqueue failure")
        logger.error(
            "Narration queue unavailable for book %s: error_type=%s",
            getattr(book, "id", None),
            type(e).__name__,
        )
        raise HTTPException(status_code=503, detail="Narration queue unavailable") from None
    # Render in the durable worker; the client polls GET /books/{id} for progress.
    logger.info("Audiobook created: id=%s chapters=%d", book.id, book.chapter_count)
    return await run_in_threadpool(get_book, book.id, principal.owner_id)


@router.get("/books/{book_id}", response_model=BookDetail)
async def get_book_endpoint(
    book_id: str,
    principal: BookPrincipal = Depends(require_book_principal),
):
    try:
        return await run_in_threadpool(get_book, book_id, principal.owner_id)
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except (BookNotFoundError, BookAccessError) as e:
        raise HTTPException(status_code=404, detail=e.detail) from None


@router.delete("/books/{book_id}")
async def delete_book_endpoint(
    book_id: str,
    principal: BookPrincipal = Depends(require_book_principal),
):
    try:
        book = await run_in_threadpool(get_book, book_id, principal.owner_id)
        if book.status not in {"complete", "failed"}:
            await run_in_threadpool(cancel_narration_for_book, book_id)
        deleted = await run_in_threadpool(delete_book, book_id, principal.owner_id)
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except (BookNotFoundError, BookAccessError) as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except JobQueueError as e:
        logger.error(
            "Narration cancellation failed for book %s: error_type=%s",
            book_id,
            type(e).__name__,
        )
        raise HTTPException(status_code=503, detail="Narration queue unavailable") from None
    logger.info("Audiobook deleted: id=%s objects=%d", book_id, deleted)
    return {"deleted": True, "id": book_id, "objects_removed": deleted}


@router.get("/books/{book_id}/master/download")
async def download_master_endpoint(
    book_id: str,
    principal: BookPrincipal = Depends(require_book_principal),
):
    try:
        url = await run_in_threadpool(master_download_url, book_id, principal.owner_id)
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except (BookNotFoundError, BookAccessError) as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    return {"url": url}


@router.get("/books/{book_id}/chapters/{index}/stream")
async def stream_chapter_endpoint(
    book_id: str,
    index: int,
    principal: BookPrincipal = Depends(require_book_principal),
):
    try:
        url = await run_in_threadpool(
            chapter_stream_url, book_id, index, principal.owner_id
        )
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except (BookNotFoundError, BookAccessError) as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    return {"url": url}
