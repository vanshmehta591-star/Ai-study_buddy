# AI Study Buddy — Implementation Plan

## Status: PENDING IMPLEMENTATION

---

## Top-Level Overview

**Goal:** Build a beginner-sized, locally-runnable AI Study Buddy that lets a student upload
a document (PDF or plain text), then:
- get plain-language topic explanations at a chosen reading level
- take a multiple-choice quiz generated from the document
- receive a spaced-repetition revision plan
- ask free-text doubt questions answered in context

**Stack:** Python 3.11+, Streamlit (UI), IBM Bob (AI calls), pdfplumber (PDF parsing),
pytest (tests), JSON flat-file persistence.

**Scope boundary (v1):**
- Single-user, local machine only — no auth, no database, no real-time sync.
- No Kahoot API, no real spaced-repetition algorithm — a simple date-ordered revision list.
- No image extraction from PDFs — text only.
- No streaming AI responses — blocking calls only.
- No multi-document sessions — one document at a time.

---

## Final Module / File Structure

```
ai-study-buddy/
├── app.py                          # Streamlit entry point — UI only
├── requirements.txt
├── data/                           # JSON persistence root (git-ignored)
│   ├── documents/                  # one JSON per uploaded document
│   ├── quizzes/                    # one JSON per quiz attempt
│   └── revision_plans/             # one JSON per revision plan
├── study_buddy/                    # all business logic (no Streamlit imports)
│   ├── __init__.py
│   ├── models.py                   # dataclasses: Document, Topic, Explanation,
│   │                               #   QuizQuestion, QuizAttempt, RevisionPlan, DoubtQuery
│   ├── exceptions.py               # custom exception hierarchy
│   ├── document_processor.py       # parsing, chunking, metadata extraction
│   ├── bob_client.py               # all IBM Bob calls — one function per agent role
│   ├── quiz_service.py             # quiz generation, scoring, persistence
│   ├── explanation_service.py      # explanation generation, level control
│   ├── revision_service.py         # revision plan generation and persistence
│   ├── doubt_service.py            # doubt/Q&A answering
│   └── persistence.py              # read/write JSON files in data/
└── tests/
    ├── conftest.py                 # shared fixtures
    ├── test_models.py
    ├── test_document_processor.py
    ├── test_bob_client.py          # monkeypatched — no real Bob calls
    ├── test_quiz_service.py
    ├── test_explanation_service.py
    ├── test_revision_service.py
    ├── test_doubt_service.py
    └── test_persistence.py
```

---

## Class Diagram (Plain Text)

```
+------------------+         +-------------------+
|    Document      |1      * |      Topic        |
+------------------+---------+-------------------+
| id: str          |         | id: str           |
| title: str       |         | document_id: str  |
| source_path: str |         | title: str        |
| file_type: str   |         | chunk_text: str   |
| uploaded_at: str |         | chunk_index: int  |
| chunks: list     |         | page_hint: int    |
+------------------+         +-------------------+
                                      |
                              uses chunk_text
                                      |
+----------------------+      +-------------------+
|    Explanation       |      |   QuizQuestion    |
+----------------------+      +-------------------+
| id: str              |      | id: str           |
| topic_id: str        |      | document_id: str  |
| document_id: str     |      | topic_id: str     |
| level: int  (1–5)    |      | question_text: str|
| text: str            |      | options: list[str]|
| generated_at: str    |      | correct_index: int|
+----------------------+      | explanation: str  |
                              +-------------------+
                                      |
                              +-------------------+
                              |   QuizAttempt     |
                              +-------------------+
                              | id: str           |
                              | document_id: str  |
                              | questions: list   |
                              | answers: list[int]|
                              | score: int        |
                              | attempted_at: str |
                              +-------------------+

+---------------------+        +-------------------+
|   RevisionPlan      |        |   DoubtQuery      |
+---------------------+        +-------------------+
| id: str             |        | id: str           |
| document_id: str    |        | document_id: str  |
| created_at: str     |        | question: str     |
| sessions: list      |        | context_chunk: str|
+---------------------+        | answer: str       |
| RevisionSession:    |        | asked_at: str     |
|   date: str         |        +-------------------+
|   topic_ids: list   |
|   completed: bool   |
+---------------------+

Relationships:
  Document  <>----  Topic            (Document owns many Topics/chunks)
  Topic     <>----  Explanation      (Topic can have multiple Explanations at diff levels)
  Document  <>----  QuizAttempt      (Document has many QuizAttempts)
  QuizAttempt <>-- QuizQuestion      (embedded list)
  Document  <>----  RevisionPlan     (one active plan per document, replaceable)
  Document  <>----  DoubtQuery       (Document has many DoubtQueries)
```

---

## Exact Data Models

All models are Python `@dataclass` with `to_dict()` / `from_dict()` for JSON round-trips.

### Document
| Field        | Type      | Notes                                      |
|--------------|-----------|--------------------------------------------|
| id           | str       | uuid4                                      |
| title        | str       | filename stem, validated non-empty         |
| source_path  | str       | absolute path after upload                 |
| file_type    | str       | "pdf" or "txt"                             |
| uploaded_at  | str       | ISO-8601 datetime                          |
| total_chunks | int       | set after chunking                         |
| chunks       | list[str] | NOT persisted to JSON (re-chunked on load) |

### Topic
| Field       | Type | Notes                                      |
|-------------|------|--------------------------------------------|
| id          | str  | uuid4                                      |
| document_id | str  | FK to Document.id                          |
| title       | str  | short label, set by Bob or heuristic       |
| chunk_text  | str  | the raw text chunk this topic is drawn from|
| chunk_index | int  | position in document (0-based)             |
| page_hint   | int  | page number if PDF, else -1                |

### Explanation
| Field        | Type | Notes                                                   |
|--------------|------|---------------------------------------------------------|
| id           | str  | uuid4                                                   |
| topic_id     | str  | FK to Topic.id                                          |
| document_id  | str  | FK to Document.id                                      |
| level        | int  | 1 = ELI5 (explain like I'm 5), 5 = university level    |
| text         | str  | Bob's explanation output                                |
| generated_at | str  | ISO-8601 datetime                                       |

### QuizQuestion
| Field         | Type      | Notes                                        |
|---------------|-----------|----------------------------------------------|
| id            | str       | uuid4                                        |
| document_id   | str       | FK to Document.id                            |
| topic_id      | str       | FK to Topic.id (nullable if full-doc quiz)   |
| question_text | str       | the question                                 |
| options       | list[str] | exactly 4 strings                            |
| correct_index | int       | 0–3                                          |
| explanation   | str       | why the correct answer is right (from Bob)   |

### QuizAttempt
| Field        | Type      | Notes                                         |
|--------------|-----------|-----------------------------------------------|
| id           | str       | uuid4                                         |
| document_id  | str       | FK to Document.id                             |
| questions    | list[dict]| serialised QuizQuestion list                  |
| answers      | list[int] | student's chosen index per question (-1=skipped)|
| score        | int       | count of correct answers                      |
| attempted_at | str       | ISO-8601 datetime                             |

### RevisionPlan
| Field       | Type              | Notes                             |
|-------------|-------------------|-----------------------------------|
| id          | str               | uuid4                             |
| document_id | str               | FK to Document.id                 |
| created_at  | str               | ISO-8601 datetime                 |
| sessions    | list[RevisionSession] | ordered list                  |

**RevisionSession** (nested dataclass):
| Field      | Type      | Notes                                           |
|------------|-----------|-------------------------------------------------|
| date       | str       | ISO-8601 date (YYYY-MM-DD)                      |
| topic_ids  | list[str] | FK to Topic.id list                             |
| completed  | bool      | default False                                   |

### DoubtQuery
| Field        | Type | Notes                                      |
|--------------|------|--------------------------------------------|
| id           | str  | uuid4                                      |
| document_id  | str  | FK to Document.id                          |
| question     | str  | student's free-text question               |
| context_chunk| str  | the most relevant chunk injected into Bob  |
| answer       | str  | Bob's answer                               |
| asked_at     | str  | ISO-8601 datetime                          |

---

## Where IBM Bob Is Called

All Bob calls live exclusively in `study_buddy/bob_client.py`.
No other module imports Bob directly.

| Function                        | Responsible for                         | Prompt strategy                                                                                                               |
|---------------------------------|-----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `generate_explanation(chunk, level)` | Turn a text chunk into an age-appropriate explanation | System: "You are a patient tutor." User: "Explain the following text at level {level}/5 where 1 is simplest. Text: {chunk}" |
| `generate_quiz_questions(chunk, n)` | Return N multiple-choice questions from a chunk | System: "You are a quiz writer." User: "Generate {n} multiple-choice questions from this text. Return JSON array." Format strictly enforced. |
| `generate_revision_plan(topics, days)` | Produce a spaced study schedule | System: "You are a study coach." User: "Given these {n} topics and {days} days, produce a JSON revision schedule." |
| `answer_doubt(question, context_chunk)` | Answer a student's free-text question using the document context | System: "You are a helpful tutor. Only answer from the provided context." User: "Context: {context_chunk}\nQuestion: {question}" |

**Prompt safety rules applied in `bob_client.py`:**
- All user-supplied text is passed as a `user` message only — never interpolated into the system prompt.
- `generate_quiz_questions` response is parsed with a strict JSON schema validator before use; on parse failure raises `QuizGenerationError`.
- `generate_revision_plan` response similarly JSON-validated before use; on failure raises `RevisionPlanError`.

---

## Document Parsing and Chunking

Module: `study_buddy/document_processor.py`

### Supported formats
| File type | Parser           | Notes                          |
|-----------|------------------|--------------------------------|
| `.pdf`    | `pdfplumber`     | text extraction page by page   |
| `.txt`    | built-in `open`  | UTF-8 read                     |
| others    | — raises `UnsupportedFileTypeError` | —            |

### Chunking strategy
1. Extract full text (PDF: concatenate all pages; TXT: whole file).
2. Split into sentences using a simple regex sentence splitter (no NLTK dependency).
3. Group sentences into chunks of **~500 tokens** (approximated as 500 words) with a
   **50-word overlap** between adjacent chunks to preserve context at boundaries.
4. Each chunk becomes one `Topic` object. `chunk_index` is the chunk's position;
   `page_hint` is the page the first sentence of that chunk came from (PDF only).
5. If the document produces **0 chunks** after stripping whitespace → raise `EmptyDocumentError`.
6. Maximum chunk count cap: **50 chunks** (≈ 25,000 words). Beyond that, only the first 50 are
   used and a warning is surfaced in the UI. Flagged as scope protection — a 200-page textbook
   is out of scope for v1.

### Why chunk instead of sending the whole file?
- Bob has a context limit; a 20-page PDF easily exceeds it.
- Chunking lets each explanation/quiz be grounded in one coherent passage.
- For doubt answering, a simple keyword-overlap search picks the single most relevant chunk
  to inject — keeping the prompt short and the answer focused.

---

## Explanation Level Control

Controlled by the `level` integer parameter (1–5) passed to `generate_explanation`.

| Level | Label shown in UI         | Instruction added to prompt                                     |
|-------|---------------------------|-----------------------------------------------------------------|
| 1     | Explain like I'm 10       | "Use very simple words, short sentences, fun analogies."        |
| 2     | Middle school             | "Avoid jargon. Use everyday examples."                          |
| 3     | High school               | "Introduce correct terminology with brief definitions."         |
| 4     | Undergraduate             | "Use subject-appropriate language; assume basic prior knowledge."|
| 5     | Expert / University       | "Be precise and technical; use field-standard terminology."     |

The mapping from integer to instruction string lives in `bob_client.py` as a module-level dict
`LEVEL_INSTRUCTIONS`. The Streamlit slider in `app.py` maps directly to this 1–5 integer.

---

## Validation Rules

All validation lives in each service module. If validation fails, a typed exception is raised
(never a bare `ValueError` exposed to the UI).

| Input                        | Rule                                                               | Exception raised         |
|------------------------------|--------------------------------------------------------------------|--------------------------|
| Uploaded file extension      | Must be `.pdf` or `.txt` (case-insensitive)                        | `UnsupportedFileTypeError` |
| Extracted document text      | After stripping whitespace, length > 0                             | `EmptyDocumentError`     |
| Explanation level            | Integer in range [1, 5]                                            | `InvalidLevelError`      |
| Quiz question count (n)      | Integer in range [1, 20]                                           | `InvalidQuizConfigError` |
| Doubt question text          | Non-empty string after strip; max 500 characters                   | `InvalidDoubtQueryError` |
| Revision plan days           | Integer in range [1, 90]                                           | `InvalidRevisionConfigError` |
| Bob JSON response (quiz)     | Must parse as a list of dicts with keys: question_text, options (len 4), correct_index (0–3), explanation | `QuizGenerationError`    |
| Bob JSON response (revision) | Must parse as a list of dicts with keys: date (YYYY-MM-DD), topic_ids (list)  | `RevisionPlanError`      |

---

## Custom Exception Hierarchy

```
StudyBuddyError (base)
├── DocumentError
│   ├── UnsupportedFileTypeError   # raised in document_processor.py on bad extension
│   └── EmptyDocumentError         # raised in document_processor.py when 0 chunks produced
├── BobError
│   ├── QuizGenerationError        # raised in bob_client.py when quiz JSON parse fails
│   └── RevisionPlanError          # raised in bob_client.py when plan JSON parse fails
├── ValidationError
│   ├── InvalidLevelError          # raised in explanation_service.py
│   ├── InvalidQuizConfigError     # raised in quiz_service.py
│   ├── InvalidDoubtQueryError     # raised in doubt_service.py
│   └── InvalidRevisionConfigError # raised in revision_service.py
└── PersistenceError               # raised in persistence.py on read/write failure
```

All defined in `study_buddy/exceptions.py`.
`app.py` catches only `StudyBuddyError` (the base) and displays a user-friendly message;
it never catches bare `Exception`.

---

## JSON Persistence Format

Root: `data/` (created on first run if missing).

### `data/documents/{document_id}.json`
```json
{
  "id": "uuid",
  "title": "Chapter 3 Notes",
  "source_path": "/tmp/uploaded/chapter3.pdf",
  "file_type": "pdf",
  "uploaded_at": "2025-01-15T10:30:00",
  "total_chunks": 12,
  "topics": [
    { "id": "uuid", "document_id": "uuid", "title": "...",
      "chunk_text": "...", "chunk_index": 0, "page_hint": 1 }
  ]
}
```
Note: `chunks` (raw list of strings) is NOT saved — it is derived from `topics[].chunk_text`
on load so there is no duplication.

### `data/quizzes/{attempt_id}.json`
```json
{
  "id": "uuid",
  "document_id": "uuid",
  "attempted_at": "2025-01-15T11:00:00",
  "score": 3,
  "questions": [
    { "id": "uuid", "document_id": "uuid", "topic_id": "uuid",
      "question_text": "...", "options": ["A","B","C","D"],
      "correct_index": 2, "explanation": "..." }
  ],
  "answers": [2, 1, 2, 0, 3]
}
```

### `data/revision_plans/{plan_id}.json`
```json
{
  "id": "uuid",
  "document_id": "uuid",
  "created_at": "2025-01-15T11:30:00",
  "sessions": [
    { "date": "2025-01-16", "topic_ids": ["uuid1","uuid2"], "completed": false },
    { "date": "2025-01-18", "topic_ids": ["uuid3"], "completed": false }
  ]
}
```

`DoubtQuery` objects are embedded inside the document JSON as `"doubt_history": [...]`
so all context for a document is in one place.

`persistence.py` exposes:
- `save_document(doc: Document) -> None`
- `load_document(doc_id: str) -> Document`
- `list_documents() -> list[Document]`
- `save_quiz_attempt(attempt: QuizAttempt) -> None`
- `load_quiz_attempt(attempt_id: str) -> QuizAttempt`
- `save_revision_plan(plan: RevisionPlan) -> None`
- `load_revision_plan(plan_id: str) -> RevisionPlan`

---

## Build Order

| Order | Module                         | Why first / prerequisite                                                              |
|-------|--------------------------------|---------------------------------------------------------------------------------------|
| 1     | `exceptions.py`                | No dependencies; everything else imports from here.                                   |
| 2     | `models.py`                    | Pure dataclasses; no imports from the project. All other modules depend on them.     |
| 3     | `persistence.py`               | Depends only on models + exceptions. Needed to save/load everything that follows.    |
| 4     | `document_processor.py`        | Depends on models + exceptions. Core pipeline: without parsed chunks, nothing works. |
| 5     | `bob_client.py`                | Depends on exceptions only. Isolated AI layer; can be tested with mocks independently.|
| 6     | `explanation_service.py`       | Depends on models, bob_client, exceptions. Simplest service — one chunk → one call. |
| 7     | `quiz_service.py`              | Depends on models, bob_client, persistence, exceptions. Builds on explanation pattern.|
| 8     | `doubt_service.py`             | Depends on models, bob_client, persistence, exceptions. Simple Q&A over a chunk.    |
| 9     | `revision_service.py`          | Depends on all services; needs topic list from processor + quiz scores optional input.|
| 10    | `app.py`                       | Depends on all services. UI is the last thing to wire up.                            |

---

## pytest Test Suite

All tests in `tests/`. External Bob calls are **always** monkeypatched — no real API calls in tests.

### `test_models.py`
1. `test_document_to_dict_roundtrip` — serialize then deserialize a Document, assert equality.
2. `test_topic_to_dict_roundtrip` — same for Topic.
3. `test_explanation_to_dict_roundtrip` — same for Explanation.
4. `test_quiz_question_to_dict_roundtrip` — same for QuizQuestion.
5. `test_quiz_attempt_to_dict_roundtrip` — same for QuizAttempt.
6. `test_revision_plan_to_dict_roundtrip` — same for RevisionPlan including nested sessions.
7. `test_doubt_query_to_dict_roundtrip` — same for DoubtQuery.

### `test_document_processor.py`
8. `test_parse_txt_file` — parse a known small .txt fixture, check chunk count and content.
9. `test_parse_pdf_file` — parse a small .pdf fixture (committed to tests/fixtures/), check chunks.
10. `test_unsupported_file_type_raises` — pass a `.docx` path, assert `UnsupportedFileTypeError`.
11. `test_empty_txt_raises` — pass a file containing only spaces, assert `EmptyDocumentError`.
12. `test_chunk_overlap` — verify adjacent chunks share the expected overlap text.
13. `test_chunk_count_cap` — document exceeding 50 chunks is capped at 50.
14. `test_page_hint_set_for_pdf` — confirm `page_hint` > 0 for at least one topic from the PDF fixture.
15. `test_page_hint_minus_one_for_txt` — confirm all topics from a TXT have `page_hint == -1`.

### `test_bob_client.py`
16. `test_generate_explanation_called_with_correct_prompt` — mock Bob, assert prompt contains chunk text and level instruction.
17. `test_generate_quiz_valid_json` — mock Bob returning valid JSON, assert correct QuizQuestion list returned.
18. `test_generate_quiz_invalid_json_raises` — mock Bob returning garbage, assert `QuizGenerationError`.
19. `test_generate_revision_plan_valid_json` — mock Bob returning valid JSON, assert RevisionPlan returned.
20. `test_generate_revision_plan_invalid_json_raises` — mock Bob returning garbage, assert `RevisionPlanError`.
21. `test_answer_doubt_returns_string` — mock Bob, assert a non-empty string is returned.

### `test_explanation_service.py`
22. `test_explanation_level_1` — request level 1, mock Bob, assert Explanation.level == 1.
23. `test_explanation_level_5` — request level 5, same check.
24. `test_invalid_level_raises` — pass level 0 or 6, assert `InvalidLevelError`.
25. `test_explanation_text_is_bob_output` — assert Explanation.text equals what the mock returned.

### `test_quiz_service.py`
26. `test_generate_quiz_returns_attempt` — mock Bob, assert QuizAttempt with correct question count.
27. `test_invalid_question_count_raises` — pass n=0 or n=25, assert `InvalidQuizConfigError`.
28. `test_score_calculation` — provide answers matching correct_index values, assert score is correct.
29. `test_score_with_skipped_answers` — `-1` answers counted as wrong, score reflects that.

### `test_doubt_service.py`
30. `test_doubt_answer_returned` — mock Bob, assert DoubtQuery.answer is set.
31. `test_empty_question_raises` — pass empty string, assert `InvalidDoubtQueryError`.
32. `test_question_too_long_raises` — pass 501-char string, assert `InvalidDoubtQueryError`.
33. `test_most_relevant_chunk_selected` — provide several topic chunks, verify the chunk injected into Bob is the one most lexically similar to the question.

### `test_revision_service.py`
34. `test_revision_plan_has_correct_session_count` — n topics over d days, assert correct session distribution.
35. `test_invalid_days_raises` — pass 0 or 100 days, assert `InvalidRevisionConfigError`.
36. `test_session_dates_are_future_dates` — assert all session dates are >= today.
37. `test_complete_session_marks_completed` — call `mark_session_complete()`, reload, assert `completed=True`.

### `test_persistence.py`
38. `test_save_and_load_document` — save a Document, load it by ID, assert equality.
39. `test_save_and_load_quiz_attempt` — same for QuizAttempt.
40. `test_save_and_load_revision_plan` — same for RevisionPlan.
41. `test_list_documents_returns_all` — save 3 documents, list, assert 3 returned.
42. `test_load_nonexistent_document_raises` — load unknown ID, assert `PersistenceError`.

---

## Assumptions

1. IBM Bob is available as a Python client importable as `bob` in the environment.
   The exact import path and call signature will be filled in when implementing `bob_client.py`.
2. `pdfplumber` is installable via pip and handles the test PDF fixtures correctly.
3. Single-user session — no concurrency issues, no file locking needed.
4. The student's machine has write access to the `data/` directory.
5. All Bob responses are in English; no multi-language support needed.

---

## Scope Creep — Cut for v1

The following ideas are explicitly out of scope for v1 and should not be implemented:

| Feature                              | Reason to cut                                                            |
|--------------------------------------|--------------------------------------------------------------------------|
| Real Kahoot API integration          | Requires API key, account, external dependency — use Streamlit MCQ UI instead |
| Actual spaced-repetition algorithm   | SM-2 complexity not needed; simple date-spaced schedule is sufficient    |
| Multi-document sessions              | Complicates data model significantly; one doc at a time is fine          |
| PDF image extraction (charts, diagrams) | Requires OCR (Tesseract) — out of scope                              |
| Streaming Bob responses              | Adds UI complexity; blocking calls are fine at this scale                |
| User authentication                  | Single-user local tool — no auth needed                                  |
| Flashcard export (Anki format)       | Separate tool concern                                                     |
| Progress analytics dashboard         | Nice to have; adds no core learning value for v1                         |
| Vector/semantic search for doubt chunking | Requires embedding model; keyword overlap is good enough for v1      |
| Multi-language document support      | Adds prompt complexity without core value for v1                         |
| Real-time collaboration              | Not a beginner feature                                                    |
| Database (SQLite, Postgres)          | JSON flat-files are sufficient for single-user v1                        |

---

## Sub-Tasks for Implementation

### Sub-Task 1 — Scaffold project structure and exceptions
- **Intent:** Create the directory layout, empty `__init__.py` files, `requirements.txt`,
  and the full exception hierarchy so all subsequent modules have a clean base.
- **Expected Outcomes:** All directories exist; `exceptions.py` defines the full hierarchy;
  `pytest` can be run (0 tests, no import errors).
- **Todo List:**
  - [ ] Create directory tree: `study_buddy/`, `tests/`, `data/documents/`, `data/quizzes/`, `data/revision_plans/`, `tests/fixtures/`
  - [ ] Write `requirements.txt` (streamlit, pdfplumber, pytest, bob client)
  - [ ] Write `study_buddy/exceptions.py` with full hierarchy
  - [ ] Write `study_buddy/__init__.py` (empty)
  - [ ] Write `tests/conftest.py` (empty for now)
- **Status:** [ ] pending

### Sub-Task 2 — Data models
- **Intent:** Implement all dataclasses with `to_dict` / `from_dict`.
- **Expected Outcomes:** `test_models.py` tests 1–7 all pass.
- **Todo List:**
  - [ ] Write `study_buddy/models.py` with all 7 dataclasses
  - [ ] Write `tests/test_models.py` with roundtrip tests 1–7
- **Status:** [ ] pending

### Sub-Task 3 — Persistence layer
- **Intent:** Implement JSON read/write for Document, QuizAttempt, RevisionPlan.
- **Expected Outcomes:** `test_persistence.py` tests 38–42 all pass.
- **Todo List:**
  - [ ] Write `study_buddy/persistence.py`
  - [ ] Write `tests/test_persistence.py`
- **Status:** [ ] pending

### Sub-Task 4 — Document processor
- **Intent:** Implement file parsing and chunking.
- **Expected Outcomes:** `test_document_processor.py` tests 8–15 all pass.
- **Todo List:**
  - [ ] Add small PDF and TXT fixtures to `tests/fixtures/`
  - [ ] Write `study_buddy/document_processor.py`
  - [ ] Write `tests/test_document_processor.py`
- **Status:** [ ] pending

### Sub-Task 5 — Bob client
- **Intent:** Implement all 4 Bob call functions with prompt templates and JSON validation.
- **Expected Outcomes:** `test_bob_client.py` tests 16–21 all pass (mocked).
- **Todo List:**
  - [ ] Write `study_buddy/bob_client.py`
  - [ ] Write `tests/test_bob_client.py`
- **Status:** [ ] pending

### Sub-Task 6 — Explanation service
- **Intent:** Wire chunk + level → Bob → Explanation object.
- **Expected Outcomes:** `test_explanation_service.py` tests 22–25 all pass.
- **Todo List:**
  - [ ] Write `study_buddy/explanation_service.py`
  - [ ] Write `tests/test_explanation_service.py`
- **Status:** [ ] pending

### Sub-Task 7 — Quiz service
- **Intent:** Generate quiz from document chunks, score attempts.
- **Expected Outcomes:** `test_quiz_service.py` tests 26–29 all pass.
- **Todo List:**
  - [ ] Write `study_buddy/quiz_service.py`
  - [ ] Write `tests/test_quiz_service.py`
- **Status:** [ ] pending

### Sub-Task 8 — Doubt service
- **Intent:** Match question to best chunk, call Bob, return DoubtQuery.
- **Expected Outcomes:** `test_doubt_service.py` tests 30–33 all pass.
- **Todo List:**
  - [ ] Write `study_buddy/doubt_service.py`
  - [ ] Write `tests/test_doubt_service.py`
- **Status:** [ ] pending

### Sub-Task 9 — Revision service
- **Intent:** Generate a date-spaced revision schedule from topic list.
- **Expected Outcomes:** `test_revision_service.py` tests 34–37 all pass.
- **Todo List:**
  - [ ] Write `study_buddy/revision_service.py`
  - [ ] Write `tests/test_revision_service.py`
- **Status:** [ ] pending

### Sub-Task 10 — Streamlit UI (app.py)
- **Intent:** Wire all services into a multi-page Streamlit UI.
- **Expected Outcomes:** App runs locally with `streamlit run app.py`, all features accessible.
- **Todo List:**
  - [ ] Write `app.py` with sidebar navigation (Upload, Explain, Quiz, Revision, Doubt)
  - [ ] Upload page: file picker, chunking trigger, document saved
  - [ ] Explain page: topic selector, level slider (1–5), display explanation
  - [ ] Quiz page: question count input, MCQ display, score display
  - [ ] Revision page: days input, plan display with date list and checkboxes
  - [ ] Doubt page: text input, answer display, history list
  - [ ] Error display: catch `StudyBuddyError`, show `st.error()`
- **Status:** [ ] pending
