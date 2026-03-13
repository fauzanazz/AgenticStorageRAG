# Documents Domain

Handles file upload, processing, and lifecycle management.

## Responsibilities
- File upload to Supabase Storage
- Document processing (text + metadata extraction)
- Chunking for downstream KG and vector ingestion
- 7-day TTL lifecycle management
- Expiry cleanup (storage + graph + vector)

## Key Files
- `interfaces.py` — `AbstractDocumentProcessor` ABC
- `service.py` — DocumentService (upload, process, expire)
- `processors/base.py` — Base processor class
- `processors/pdf.py` — PdfProcessor
- `processors/docx.py` — DocxProcessor
- `models.py` — SQLAlchemy Document model
- `schemas.py` — Pydantic request/response schemas
- `router.py` — Upload, list, get, delete endpoints
- `exceptions.py` — Typed document errors

## Adding a New File Format
1. Create `processors/your_format.py`
2. Implement `YourFormatProcessor(AbstractDocumentProcessor)`
3. Register it in `processors/__init__.py`
4. Write tests in `tests/test_your_format_processor.py`
5. No changes needed to service, router, or models
