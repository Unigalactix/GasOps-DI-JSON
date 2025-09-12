# GasOps-DI-JSON — Architecture & Workflow

This document summarizes the architecture, responsibilities, and runtime workflow for the GasOps-DI-JSON project (PDF → structured JSON using Azure Document Intelligence + LLMs).

## High-level overview

The project converts PDF Material Test Reports (MTRs) into a structured JSON format using two main technologies:

- Azure Document Intelligence (Form Recognizer) for OCR and document analysis.
- A conversational LLM (Azure OpenAI or OpenAI) to parse the extracted text and populate a JSON template.

Main components (in code):

- `DocumentIntelligenceOCR` — handles submission of a PDF to Azure Document Intelligence, polls for completion, and extracts raw text from the returned analysis JSON.
- `AITemplateProcessor` — builds the prompts (system + user), calls the LLM API (Azure OpenAI or OpenAI), parses the LLM response, and extracts JSON that matches the template.
- `PDFProcessor` — orchestrates reading PDFs, running OCR, loading the template, invoking AI processing, and saving the generated JSON.

There is also:
- a sample JSON template at `Sample json/sample.json` (used as the schema to populate)
- environment configuration via a `.env` file (loaded with dotenv)

## File map (key files)

- `pdf_processor_new prompt.py` — main implementation (classes above + CLI interactive loop)
- `Sample json/sample.json` — JSON template used for structure and defaults
- `old_scripts/pdf_processor.py` — earlier implementation (reference/backwards compat)
- `TESTS/` — contains some tests and sample JSON files

## Data shapes

Primary output: a single JSON object per PDF with this top-level shape (example):

{
  "CompanyMTRFileID": null,
  "HeatNumber": "E3L146",
  "CertificationDate": "MM/DD/YYYY",
  "MatlFacilityDetails": { ... },
  "HNPipeDetails": [
    {
      "PipeNumber": "...",
      "HNPipeHeatChemicalResults": { /* heat-level chemistry */ },
      "HNPipeChemicalCompResults": { /* product-level chemistry */ },
      "HNPipeChemicalEquivResults": { /* CE Pcm / CE IIW */ },
      "HNPipeTensileTestResults": { /* YS, UTS, Y/T, seam weld */ },
      ...
    }
  ]
}

All numeric values are represented as strings in the output JSON (project convention).

## Workflow (step-by-step)

1. User runs the script (interactive or batch mode) and provides PDF path(s).
2. `PDFProcessor.process_pdf` reads the PDF bytes from disk.
3. `DocumentIntelligenceOCR._call_document_intelligence_api` sends the PDF to the Document Intelligence endpoint and receives an operation location (or immediate JSON). It polls until `status == 'succeeded'`.
4. `DocumentIntelligenceOCR._parse_ocr_result` recursively traverses the returned JSON to collect string content fields (content/text/value) into a single large OCR text blob.
5. `AITemplateProcessor.load_template` loads and cleans the JSON template, producing a blank/zeroed template for the LLM to populate.
6. `AITemplateProcessor._build_system_message` and `_build_user_message` produce a strict system prompt and a user prompt that includes the template and the OCR text. The system prompt enforces rules for CE mapping, tensile field extraction, normalization (leading zero normalization), units handling, date format, and ambiguity policy.
7. `AITemplateProcessor` calls the configured LLM (`_call_azure_openai` or `_call_openai`) with the messages payload.
8. The LLM returns content. `AITemplateProcessor._extract_json_from_response` tries to locate the JSON object/array inside the response (robust bracket depth search) and parses it.
9. `PDFProcessor` receives the generated JSON, performs a final save to disk (same directory as PDF unless overridden).
10. Batch/summary reporting prints success/fail counts.

## Prompt design notes (what is enforced)

- Output must be a single JSON object matching the provided template exactly.
- Numeric values must be strings; leading decimals must be normalized to include a leading zero ('.354' -> '0.354').
- Units must not be appended to numeric fields — instead populate the `*Unit` fields.
- CE mapping rules (Chemical Equivalency): prefer explicit labels; if not labeled, use nearest-label / table-row proximity; do not swap Product1/Product2; if ambiguous, leave null.
- Tensile mapping rules: prefer explicit labels (YS/UTS), map units separately, normalize numeric formatting, do not invent seam-weld results.
- Ambiguity policy: prefer nulls over guessing; optionally include a short `ExtractionNotes` top-level key if a human-readable note is needed.

## Environment variables

The script uses these env vars (set in a `.env` file or system env):

- Azure Document Intelligence
  - `AZURE_DI_ENDPOINT` (or `AZURE_FORM_RECOGNIZER_ENDPOINT`)
  - `AZURE_DI_KEY` (or `AZURE_FORM_RECOGNIZER_KEY`)
  - `AZURE_DI_MODEL_ID` (optional, default `prebuilt-document`)
  - `AZURE_DI_API_VERSION` (optional)

- AI provider
  - Azure OpenAI: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY` (or `AZURE_OPENAI_API_KEY`), `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`
  - OpenAI: `OPENAI_API_KEY` (the code prefers Azure OpenAI when both configs exist)

- Other: `DOTENV` handled automatically by python-dotenv via `load_dotenv()`

## Error handling & resilience

- OCR API errors: `_handle_api_error` surfaces helpful hints for 403s (VNet/firewall) and raises runtime errors for other codes.
- Polling: the OCR poll has a max retry loop and raises on timeout.
- AI call errors: `_call_azure_openai` and `_call_openai` raise an exception if the response code is not 200/201.
- Parsing fallback: `_extract_json_from_response` attempts several strategies (object-first, array-first, full-parse fallback).

## Testing & validation suggestions

- Unit tests: add tests for `_extract_json_from_response` with varied LLM outputs (wrapped text, markdown, code fences, multiple objects).
- Prompt-safety tests: mock the AI response to ensure the code only accepts well-formed JSON and leaves ambiguous fields null.
- Integration test: record a sample OCR output and run the full pipeline with a mocked LLM that returns a known JSON payload; assert saved JSON equals expected output.

## How to run (developer)

1. Create a `.env` with the env vars described above.
2. Install dependencies (if needed):

```powershell
python -m pip install -r requirements.txt
```

3. Run interactively:

```powershell
python "pdf_processor_new prompt.py"
```

4. Or call from Python to process a file programmatically (example in REPL):

```python
from pdf_processor_new_prompt import PDFProcessor
p = PDFProcessor()
p.process_pdf(r"C:\path\to\file.pdf")
```

(Adjust import path/filename if needed.)

## Future improvements

- Persist system/user prompt text in external files for easier editing and versioning.
- Add explicit unit/format validators after AI output to auto-correct obvious unit mismatches.
- Add a dedicated test suite with mocking for Azure/OpenAI and a CI job to validate prompt and parsing changes.
- Consider using structured output tools (e.g., function calling or JSON Schema enforced by model) when using newer model APIs that support structured responses.

## Contact & notes

If you want, I can:
- Move the prompts into `prompts/` and update code to load them.
- Add a minimal test harness that mocks AI responses and validates CE/tensile mapping rules.
- Batch-process your `MTR-PIPE-SINGLE` folder and produce a report of ambiguous fields.

---

Generated by editing the repository to document architecture and workflow. Feel free to request additional diagrams (Mermaid), example prompt files, or automated tests.