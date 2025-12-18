# Architecture Overview

SpecScout CLI is designed with a focus on efficiency and accuracy in technical data extraction from unstructured PDF documents.

## System Components

### 1. File Management & De-duplication
- **Hashing**: Every PDF is hashed (SHA-256) before processing. This ensures that identical files with different names are only processed once, saving both local compute and API costs.
- **Filtering**: Only files with the `.pdf` extension are considered.

### 2. Text Extraction Layer
- Uses **PyMuPDF (fitz)** for robust text extraction across various PDF layouts.
- Text is extracted page by page and aggregated for analysis.

### 3. Extraction Engines

#### Standard Engine (`main.py`)
- **Regex-Based**: Uses flexible regular expressions with look-aheads to find "Weight" or "Mass" keywords and their associated values.
- **Pros**: Extremely fast, runs locally, no cost.
- **Cons**: May miss data in highly complex or non-standard layouts.

#### LLM-Enhanced Engine (`BONUS/main_llm.py`)
- **Semantic Understanding**: Leverages OpenAI's `gpt-4o-mini` with **Structured Outputs** (JSON mode) to parse technical specs.
- **Pre-filtering Optimization**: A regex-based "pre-scan" checks for weight-related keywords before calling the API. If no keywords are found, the file is skipped, saving significant API quota.
- **Pydantic Validation**: Uses Pydantic models to ensure the LLM output conforms to the expected schema.
- **Pros**: High accuracy, understands context, extracts all characteristics.
- **Cons**: Requires API key, slower than regex, incurs costs.

## Data Flow

1. **Input**: User provides a directory and a weight limit.
2. **Scan**: System identifies unique PDFs.
3. **Extract**:
    - *Regex Mode*: Directly searches text for patterns.
    - *LLM Mode*: Pre-scans -> Truncates text -> Calls OpenAI API -> Validates JSON.
4. **Normalize**: Weights are converted to grams (e.g., "1.2 kg" -> 1200g) for uniform comparison.
5. **Filter**: Products exceeding the weight limit are discarded.
6. **Output**: Results are saved to a JSON file and displayed in a stylized terminal view.

## Design Decisions

- **Rich Console**: Integrated `rich` to provide a premium CLI experience with clear status indicators and summaries.
- **Truncation**: LLM input is truncated to 8,000 characters. This captures the essential specifications (usually on the first few pages) while staying within token limits and reducing latency.
- **Exponential Backoff**: Implemented for LLM calls to handle rate limits and model overloads gracefully.
