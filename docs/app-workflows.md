<!-- last_verified: 2026-06-25 -->
# App Workflows

User journeys inside the application.

## Create an Audiobook

- User navigates to `/create` (New Audiobook)
- Pastes a manuscript, or loads a `.txt`/`.md` file (its content fills the editor)
- The chapter preview shows how the text will split (estimate, mirrors backend rules)
- User picks a narrator voice from the provider catalog (`GET /voices`)
- Clicks **Generate** → `POST /books` splits the text, writes `source.txt` + an initial
  manifest, and enqueues a durable narration job
- User is redirected to `/library?book=<id>` to watch progress
- See: [Chapter Narration](features/narration.md), [Chapter Detection](features/chapter-detection.md)

## Listen and Manage in the Library

- User navigates to `/library`
- The grid lists their audiobooks (scoped to the `audiobooks/` prefix); cards show
  status, chapters rendered/total, duration, and created date
- While a book is narrating, its card and detail panel poll and update automatically
- Selecting a card opens the detail panel with a per-chapter list and an `<audio>` player
- **Play a chapter**: fetches a presigned inline URL; the browser streams the MP3 from
  B2 (Range reads)
- **Download master**: opens the presigned M4B attachment URL (enabled once assembled)
- **Delete**: removes the entire `audiobooks/<id>/` prefix after a confirm dialog
- See: [Library](features/library.md), [Master Assembly](features/master-assembly.md)

## View Dashboard

- User navigates to `/` (home)
- Hooks load book stats, recent audiobooks, and narration activity
- Stat cards: total audiobooks, chapters rendered, hours narrated, storage used
- Chart: audio hours generated per day (last 7 days)
- Recent audiobooks table: title, chapters, duration, status, created
- Empty states point to New Audiobook
- See: [Dashboard](features/dashboard.md)

## Upload and Browse Files (kept B2 scaffolding)

- `/upload`: drag-and-drop a file (≤ 100 MB) to the `uploads/` prefix; per-file progress
- `/files`: full-bucket tree view with preview / download / delete
- See: [File Upload](features/file-upload.md), [File Browser](features/file-browser.md)
