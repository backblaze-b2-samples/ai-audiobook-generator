import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.repo import TTSError
from app.service.books import (
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
from app.service.narration import create_book, list_voices, run_narration
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
        return list_voices()
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None


@router.get("/books", response_model=list[BookSummary])
async def list_books_endpoint():
    return list_books()


@router.get("/books/stats", response_model=BookStats)
async def book_stats_endpoint():
    return book_stats()


@router.get("/books/stats/activity", response_model=list[DailyNarrationHours])
async def book_activity_endpoint(days: int = 7):
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 90")
    return book_activity(days=days)


@router.post("/books", response_model=BookDetail, status_code=202)
async def create_book_endpoint(
    request: CreateBookRequest, background_tasks: BackgroundTasks
):
    try:
        book = create_book(request)
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    # Render in the background; the client polls GET /books/{id} for progress.
    background_tasks.add_task(run_narration, book.id)
    logger.info("Audiobook created: id=%s chapters=%d", book.id, book.chapter_count)
    return get_book(book.id)


@router.get("/books/{book_id}", response_model=BookDetail)
async def get_book_endpoint(book_id: str):
    try:
        return get_book(book_id)
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except BookNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None


@router.delete("/books/{book_id}")
async def delete_book_endpoint(book_id: str):
    try:
        deleted = delete_book(book_id)
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except BookNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    logger.info("Audiobook deleted: id=%s objects=%d", book_id, deleted)
    return {"deleted": True, "id": book_id, "objects_removed": deleted}


@router.get("/books/{book_id}/master/download")
async def download_master_endpoint(book_id: str):
    try:
        url = master_download_url(book_id)
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except BookNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    return {"url": url}


@router.get("/books/{book_id}/chapters/{index}/stream")
async def stream_chapter_endpoint(book_id: str, index: int):
    try:
        url = chapter_stream_url(book_id, index)
    except BookKeyError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except BookNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    return {"url": url}
