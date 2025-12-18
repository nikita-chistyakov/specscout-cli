import os
import re
import json
import argparse
import hashlib
import time
from pathlib import Path
from typing import List, Optional
import fitz  # PyMuPDF
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from rich.console import Console
from rich.theme import Theme

# Load environment variables
load_dotenv()

# Initialize Rich Console with a custom theme
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "header": "bold blue underline"
})
console = Console(theme=custom_theme)

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

def get_file_hash(filepath):
    """Generate a SHA-256 hash to identify duplicate files by content."""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def normalize_to_grams(value_str):
    """
    Parses strings like '1.2 kg' or '500 g' and returns weight in grams.
    Returns None if no valid weight/unit is found.
    """
    # Regex to capture number and unit (g or kg)
    match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g)\b', value_str.lower())
    if not match:
        return None
    
    value = float(match.group(1))
    unit = match.group(2)
    
    if unit == 'kg':
        return value * 1000
    return value

def has_weight_spec(text: str) -> bool:
    """
    Quickly check if the text contains weight or mass keywords using regex.
    This helps avoid unnecessary LLM calls.
    """
    # Look for "weight" or "mass" followed by some text and a number/unit
    pattern = r'(weight|mass)\s*[:\-]?\s*[<>]?\s*[\d\.]+\s*(kg|g)\b'
    return bool(re.search(pattern, text, re.IGNORECASE))

def extract_product_data_llm(text: str, filename: str) -> List[Product]:
    """
    Use OpenAI to parse product specifications from raw text.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        console.print("[error]OPENAI_API_KEY not found or not set in environment variables![/error]")
        return []

    client = OpenAI(api_key=api_key)

    # Optimization: Truncate text to a reasonable size for extraction
    truncated_text = text[:8000]

    prompt = f"""
    You are an expert technical data extractor. 
    Analyze the following text from an antenna datasheet and extract EVERY technical characteristic described.
    
    The text may contain multiple products. For EACH product found:
    1. Identify the product name.
    2. Extract ALL technical characteristics listed (Frequency, Gain, VSWR, Dimensions, Weight, Mass, Connector, Materials, Temperature, etc.) as key-value pairs.
    3. Ensure "Weight" or "Mass" is extracted if present.
    
    Input Text:
    {truncated_text}
    """

    base_delay = 2
    while True:
        try:
            console.print(f"[dim]Requesting OpenAI extraction for {filename}...[/dim]")
            completion = client.beta.chat.completions.parse(
                model="gpt-4o-mini",
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
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                 console.print(f"[yellow]Rate limit exceeded for {filename}. Waiting 60s...[/yellow]")
                 time.sleep(60)
                 continue
            
            if "503" in error_str or "overloaded" in error_str.lower():
                console.print(f"[yellow]Model overloaded. Retrying in {base_delay}s...[/yellow]")
                time.sleep(base_delay)
                base_delay *= 2 # Exponential backoff
                continue

            console.print(f"[error]LLM Extraction failed for {filename}: {e}[/error]")
            return []

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from all pages of a PDF."""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text("text") + "\n"
        doc.close()
    except Exception as e:
        console.print(f"[error]Error reading {pdf_path.name}: {e}[/error]")
    return text

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
    console.print(f"Scanning directory: [info]{args.dir}[/info]")

    # --- Step 2: Sanity Check (Only PDFs & Remove Duplicates) ---
    seen_hashes = set()
    unique_files = []
    
    all_files = sorted([f for f in os.listdir(args.dir) if f.lower().endswith('.pdf')])
    
    for filename in all_files:
        path = os.path.join(args.dir, filename)
        f_hash = get_file_hash(path)
        if f_hash not in seen_hashes:
            seen_hashes.add(f_hash)
            unique_files.append(path)
    
    console.print(f"[success]Found {len(unique_files)} unique PDFs.[/success]")

    if args.test and unique_files:
        # Optimization for test mode: find the first file that actually has weight specs
        test_file = None
        for path in unique_files:
            text = extract_text_from_pdf(Path(path))
            if has_weight_spec(text):
                test_file = path
                break
        
        if test_file:
            unique_files = [test_file]
            console.print(f"[warning]--- TEST MODE ACTIVE: Processing {os.path.basename(test_file)} (contains weight specs) ---[/warning]")
        else:
            unique_files = unique_files[:1]
            console.print(f"[warning]--- TEST MODE ACTIVE: No file with weight specs found, processing {os.path.basename(unique_files[0])} ---[/warning]")

    # --- Step 3 & 4: Extraction and Filtering ---
    filtered_products = []

    for pdf_path in unique_files:
        filename = os.path.basename(pdf_path)
        console.print(f"[info]Processing {filename}...[/info]")
        text = extract_text_from_pdf(Path(pdf_path))
        if not text:
            continue

        # Optimization: Pre-filter using regex
        if not has_weight_spec(text):
            console.print(f"  [dim]Skipping {filename}: No weight/mass specifications found via pre-scan.[/dim]")
            continue

        # LLM Extraction
        products = extract_product_data_llm(text, filename)
        
        for product in products:
            weight_in_grams = None
            # Semantic weight matching: look for characteristics containing "Weight" or "Mass"
            for char in product.characteristics:
                char_name_lower = char.name.lower()
                if "weight" in char_name_lower or "mass" in char_name_lower:
                    grams = normalize_to_grams(char.value)
                    if grams is not None:
                        weight_in_grams = grams
                        # If we find a weight, we can stop looking for this product
                        break
            
            if weight_in_grams is not None and weight_in_grams < args.weight_limit:
                console.print(f"  [success]MATCH:[/success] {product.name} ({weight_in_grams}g)")
                
                # Transform characteristics to the requested format: [{"Key": "Value"}, ...]
                refined_characteristics = []
                for char in product.characteristics:
                    refined_characteristics.append({char.name: char.value})

                filtered_products.append({
                    "name": product.name,
                    "file": product.file,
                    "characteristics": refined_characteristics
                })

        # Small delay to be nice to the API
        time.sleep(1)

    # Output final results
    console.print(f"\n[header]--- Processed Results (Lighter than {args.weight_limit}g) ---[/header]")
    formatted_json = json.dumps(filtered_products, indent=4)
    console.print(formatted_json)

    # Summary message
    match_count = len(filtered_products)
    if match_count > 0:
        console.print(f"\n[success]Found {match_count} antenna(s) matching the weight requirement.[/success]")
    else:
        console.print(f"\n[warning]No antennas found matching the weight requirement.[/warning]")

    # Save to a file
    output_file = "BONUS/filtered_products_llm.json"
    with open(output_file, "w") as f:
        f.write(formatted_json)
    
    console.print(f"\n[info]Results saved to: {os.path.abspath(output_file)}[/info]")

if __name__ == "__main__":
    main()
