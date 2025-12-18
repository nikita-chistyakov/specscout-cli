import sys
import os
import re
import json
import argparse
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import fitz  # PyMuPDF
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from rich.console import Console
from rich.theme import Theme

# Add the project root to sys.path to allow importing utils
sys.path.append(str(Path(__file__).parent.parent))

from utils import get_file_hash, normalize_to_grams, FileProcessingError, SpecScoutError

# Load environment variables
load_dotenv()

# --- Configuration & Constants ---
CUSTOM_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "header": "bold blue underline"
})

OPENAI_MODEL = "gpt-4o-mini"
TEXT_TRUNCATION_LIMIT = 8000
WEIGHT_PREFILTER_PATTERN = r'(weight|mass)\s*[:\-]?\s*[<>]?\s*[\d\.]+\s*(kg|g)\b'
DEFAULT_OUTPUT_FILE = "BONUS/filtered_products_llm.json"

# Initialize Rich Console
console = Console(theme=CUSTOM_THEME)

# --- Data Models ---
class Characteristic(BaseModel):
    name: str = Field(description="The name of the technical characteristic (e.g., Frequency, Gain, Weight, Mass)")
    value: str = Field(description="The value of the characteristic as found in the text")

class Product(BaseModel):
    name: str = Field(description="The name of the product/antenna")
    file: str = Field(description="The source filename")
    characteristics: List[Characteristic] = Field(description="List of all technical characteristics found")

class ProductList(BaseModel):
    products: List[Product]

# --- Core Logic ---

class SpecExtractor:
    """Handles LLM-based extraction of product specifications."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            raise SpecScoutError("OPENAI_API_KEY not found or not set correctly.")
        
        self.client = OpenAI(api_key=self.api_key)

    def extract_from_text(self, text: str, filename: str) -> List[Product]:
        """
        Use OpenAI to parse product specifications from raw text.
        """
        truncated_text = text[:TEXT_TRUNCATION_LIMIT]
        prompt = self._build_prompt(truncated_text)

        base_delay = 2
        while True:
            try:
                console.print(f"[dim]Requesting OpenAI extraction for {filename}...[/dim]")
                completion = self.client.beta.chat.completions.parse(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a technical data extraction assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=ProductList,
                )
                
                product_list = completion.choices[0].message.parsed
                
                # Ensure the filename is correctly set for each product
                for product in product_list.products:
                    product.file = filename
                    
                return product_list.products

            except Exception as e:
                if self._should_retry(str(e), base_delay):
                    time.sleep(base_delay)
                    base_delay *= 2
                    continue
                
                console.print(f"[error]LLM Extraction failed for {filename}: {e}[/error]")
                return []

    def _build_prompt(self, text: str) -> str:
        return f"""
        You are an expert technical data extractor. 
        Analyze the following text from an antenna datasheet and extract EVERY technical characteristic described.
        
        The text may contain multiple products. For EACH product found:
        1. Identify the product name.
        2. Extract ALL technical characteristics listed (Frequency, Gain, VSWR, Dimensions, Weight, Mass, Connector, Materials, Temperature, etc.) as key-value pairs.
        3. Ensure "Weight" or "Mass" is extracted if present.
        
        Input Text:
        {text}
        """

    def _should_retry(self, error_msg: str, delay: int) -> bool:
        """Determines if an error is retryable and logs the wait."""
        if "429" in error_msg or "rate_limit" in error_msg.lower():
            console.print(f"[yellow]Rate limit exceeded. Waiting 60s...[/yellow]")
            time.sleep(60)
            return True
        
        if "503" in error_msg or "overloaded" in error_msg.lower():
            console.print(f"[yellow]Model overloaded. Retrying in {delay}s...[/yellow]")
            return True
            
        return False

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from all pages of a PDF."""
    try:
        doc = fitz.open(pdf_path)
        text = "".join(page.get_text("text") + "\n" for page in doc)
        doc.close()
        return text
    except Exception as e:
        console.print(f"[error]Error reading {pdf_path.name}: {e}[/error]")
        return ""

def has_weight_spec(text: str) -> bool:
    """Quickly check if the text contains weight or mass keywords using regex."""
    return bool(re.search(WEIGHT_PREFILTER_PATTERN, text, re.IGNORECASE))

def get_unique_pdfs(directory: str) -> List[str]:
    """Scans a directory for unique PDF files based on content hash."""
    seen_hashes = set()
    unique_files = []
    
    all_files = sorted([f for f in os.listdir(directory) if f.lower().endswith('.pdf')])
    
    for filename in all_files:
        path = os.path.join(directory, filename)
        try:
            f_hash = get_file_hash(path)
            if f_hash not in seen_hashes:
                seen_hashes.add(f_hash)
                unique_files.append(path)
        except FileProcessingError as e:
            console.print(f"[warning]Skipping {filename}: {e}[/warning]")
            
    return unique_files

def main():
    parser = argparse.ArgumentParser(description="Antenna PDF Spec Processor (OpenAI Version)")
    parser.add_argument("dir", help="Directory containing PDF files")
    parser.add_argument("-w", "--weight_limit", type=float, required=True, help="Upper bound weight in grams")
    parser.add_argument("-t", "--test", action="store_true", help="Process only 1 PDF for testing")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        console.print(f"[error]Error: {args.dir} is not a valid directory.[/error]")
        return

    console.print(f"[header]Starting Optimized OpenAI-Enhanced SpecScout CLI[/header]")
    
    try:
        extractor = SpecExtractor()
    except Exception as e:
        console.print(f"[error]{e}[/error]")
        return

    unique_files = get_unique_pdfs(args.dir)
    console.print(f"[success]Found {len(unique_files)} unique PDFs.[/success]")

    if args.test and unique_files:
        # Find the first file that actually has weight specs for a better test
        test_file = next((f for f in unique_files if has_weight_spec(extract_text_from_pdf(Path(f)))), unique_files[0])
        unique_files = [test_file]
        console.print(f"[warning]--- TEST MODE ACTIVE: Processing {os.path.basename(test_file)} ---[/warning]")

    filtered_products = []

    for pdf_path in unique_files:
        filename = os.path.basename(pdf_path)
        console.print(f"[info]Processing {filename}...[/info]")
        
        text = extract_text_from_pdf(Path(pdf_path))
        if not text or not has_weight_spec(text):
            if text:
                console.print(f"  [dim]Skipping {filename}: No weight/mass specifications found via pre-scan.[/dim]")
            continue

        products = extractor.extract_from_text(text, filename)
        
        for product in products:
            weight_grams = None
            for char in product.characteristics:
                if any(kw in char.name.lower() for kw in ["weight", "mass"]):
                    weight_grams = normalize_to_grams(char.value)
                    if weight_grams is not None:
                        break
            
            if weight_grams is not None and weight_grams < args.weight_limit:
                console.print(f"  [success]MATCH:[/success] {product.name} ({weight_grams}g)")
                filtered_products.append({
                    "name": product.name,
                    "file": product.file,
                    "characteristics": [{c.name: c.value} for c in product.characteristics]
                })

        time.sleep(1) # API politeness

    # Output final results
    console.print(f"\n[header]--- Processed Results (Lighter than {args.weight_limit}g) ---[/header]")
    formatted_json = json.dumps(filtered_products, indent=4)
    console.print(formatted_json)

    # Summary message
    match_count = len(filtered_products)
    console.print(f"\n[{'success' if match_count > 0 else 'warning'}]Found {match_count} antenna(s) matching the weight requirement.[/{'success' if match_count > 0 else 'warning'}]")

    # Save to a file
    try:
        os.makedirs(os.path.dirname(DEFAULT_OUTPUT_FILE), exist_ok=True)
        with open(DEFAULT_OUTPUT_FILE, "w") as f:
            f.write(formatted_json)
        console.print(f"\n[info]Results saved to: {os.path.abspath(DEFAULT_OUTPUT_FILE)}[/info]")
    except OSError as e:
        console.print(f"[error]Failed to save results: {e}[/error]")

if __name__ == "__main__":
    main()
