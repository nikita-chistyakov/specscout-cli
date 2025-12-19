# SpecScout CLI

SpecScout CLI is a powerful tool designed to scan PDF datasheets for antennas and extract technical specifications, specifically focusing on weight requirements. It offers two modes of operation: a fast, local regex-based extraction and an advanced, LLM-enhanced semantic extraction.

## Features

- **PDF Text Extraction**: Efficiently extracts text from PDF documents using PyMuPDF.
- **Duplicate Detection**: Uses SHA-256 hashing to identify and skip duplicate files.
- **Rich Terminal Output**: Provides stylized and colored console output using the `rich` library.
- **Regex-Based Extraction**: Fast, local extraction of product names and weights using flexible regex patterns.
- **LLM-Enhanced Extraction (Bonus)**: Uses OpenAI's GPT-4o-mini to semantically understand and extract *all* technical characteristics from datasheets.
- **Pre-filtering Optimization**: The LLM version includes a regex pre-scan to skip irrelevant files, saving API quota.
- **Structured JSON Output**: Generates a clean JSON file containing matched products and their characteristics.
- **Modular Architecture**: Clean and well-structured code with logic separated into specialized modules.
- **Centralized Utilities**: Common logic (hashing, normalization) and custom exceptions are centralized in `utils.py` for better maintainability.
- **Robust Error Handling**: Comprehensive error handling with custom exceptions and informative feedback.
- **Type Safety**: Fully type-hinted codebase for better developer experience and reliability.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/nikita-chistyakov/specscout-cli.git
   cd specscout-cli
   ```

2. Set up a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Set up OpenAI API Key for the LLM version:
   Create a `.env` file in the root directory and add your key:
   ```text
   OPENAI_API_KEY=your_api_key_here
   ```

## Usage

### Standard Version (Regex)
Fast and local extraction.
```bash
python3 main.py data -w 50
```

### LLM Version (OpenAI)
Advanced semantic extraction.
```bash
python3 BONUS/main_llm.py data -w 50
```

### Arguments
- `dir`: Directory containing PDF files.
- `-w`, `--weight_limit`: Upper bound weight in grams for filtering.
- `-t`, `--test`: (LLM version only) Process only 1 relevant PDF for testing.

## Output Format
The results are saved to `filtered_products.json` (standard) or `BONUS/filtered_products_llm.json` (LLM) in the following format:
```json
[
    {
        "name": "Product Name",
        "file": "source_file.pdf",
        "characteristics": [
            { "Frequency": "2.4 GHz" },
            { "Weight": "45g" }
        ]
    }
]
```
