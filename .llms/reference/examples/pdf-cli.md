# PDF CLI

## Source References

- `examples/pdf_cli.py`
- `genai_processors/core/pdf.py`
- `genai_processors/content_api.py`

## Entrypoint

- Run with `python3 examples/pdf_cli.py <pdf_file>`.

## Pipeline / Data Flow

- Reads the PDF file as bytes.
- Wraps bytes in `content_api.ProcessorPart(content, mimetype=pdf.PDF_MIMETYPE,
  metadata={'original_file_name': filename})`.
- Runs `pdf.PDFExtract()` over that single part.
- Prints each extracted part with a timestamp.

## Dependencies / Env

- No model API key required.
- Requires whatever PDF extraction dependencies are installed for
  `genai_processors.core.pdf`.

## Demonstrated Processor Contracts

- Binary input is carried as a `ProcessorPart` with explicit MIME type.
- File identity is preserved as metadata, not inferred from bytes.
- `PDFExtract` is a plain processor over content parts and can be inserted
  before a model, as in `chat.py`.

## Gotchas

- The script uses `open(..., 'rb')` and loads the full PDF into memory.
- Extraction output shape depends on `PDFExtract`; the CLI is for inspection.
