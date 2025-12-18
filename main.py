import os
import re
import json
import argparse
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF
from rich.console import Console
from rich.theme import Theme

from utils import get_file_hash, normalize_to_grams, FileProcessingError

# --- Configuration & Constants ---
CUSTOM_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "header": "bold blue underline"
})

CHAR_PATTERN = re.compile(r'^([\w\s/().-]+):\s*(.*)$', re.MULTILINE)
WEIGHT_KEYWORDS = ["weight", "mass"]
DEFAULT_OUTPUT_FILE = "filtered_products.json"

# Initialize Rich Console
console = Console(theme=CUSTOM_THEME)

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts all text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file.
        
    Returns:
        The extracted text as a string.
        
    Raises:
        FileProcessingError: If the PDF cannot be opened or read.
    """
    try:
        doc = fitz.open(pdf_path)
        text = "".join(page.get_text("text") + "\n" for page in doc)
        doc.close()
        return text
    except Exception as e:
        raise FileProcessingError(f"Failed to extract text from {pdf_path}: {e}")

def parse_characteristics(text: str) -> List[Dict[str, str]]:
    """
    Parses 'Key: Value' pairs from text.
    
    Args:
        text: The text to parse.
        
    Returns:
        A list of dictionaries, each containing a single key-value pair.
    """
    matches = CHAR_PATTERN.findall(text)
    return [{key.strip(): val.strip()} for key, val in matches]

def find_weight_fallback(text: str) -> Optional[float]:
    """
    Attempts to find weight/mass values if not found in standard key-value format.
    
    Args:
        text: The text to search.
        
    Returns:
        Weight in grams if found, else None.
    """
    for keyword in WEIGHT_KEYWORDS:
        for m in re.finditer(re.escape(keyword), text, re.IGNORECASE):
            # Look at the 100 characters following the keyword
            look_ahead = text[m.end():m.end() + 100]
            grams = normalize_to_grams(look_ahead)
            if grams is not None:
                return grams
    return None

def extract_product_data(pdf_path: str) -> Optional[Dict[str, Any]]:
    """
    Extracts product name, characteristics, and weight from a PDF.
    
    Args:
        pdf_path: Path to the PDF file.
        
    Returns:
        A dictionary with product data, or None if processing fails.
    """
    try:
        full_text = extract_text_from_pdf(pdf_path)
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        if not lines:
            return None

        product_name = lines[0]
        characteristics = parse_characteristics(full_text)
        
        # Identify weight from characteristics
        weight_grams = None
        for char_dict in characteristics:
            key = list(char_dict.keys())[0]
            if any(kw in key.lower() for kw in WEIGHT_KEYWORDS):
                weight_grams = normalize_to_grams(char_dict[key])
                if weight_grams is not None:
                    break
        
        # Fallback if not found in structured characteristics
        if weight_grams is None:
            weight_grams = find_weight_fallback(full_text)
            if weight_grams is not None:
                characteristics.append({"Weight (Extracted)": f"{weight_grams}g"})

        return {
            "name": product_name,
            "file": os.path.basename(pdf_path),
            "characteristics": characteristics,
            "weight_grams": weight_grams
        }
    except FileProcessingError as e:
        console.print(f"[error]{e}[/error]")
        return None
    except Exception as e:
        console.print(f"[error]Unexpected error processing {pdf_path}: {e}[/error]")
        return None

def get_unique_pdfs(directory: str) -> List[str]:
    """
    Scans a directory for unique PDF files based on content hash.
    
    Args:
        directory: The directory to scan.
        
    Returns:
        A list of paths to unique PDF files.
    """
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
    parser = argparse.ArgumentParser(description="Antenna PDF Spec Processor")
    parser.add_argument("dir", help="Directory containing PDF files")
    parser.add_argument("-w", "--weight_limit", type=float, required=True, help="Upper bound weight in grams")
    parser.add_argument("-t", "--test", action="store_true", help="Process only 1 PDF for testing")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        console.print(f"[error]Error: {args.dir} is not a valid directory.[/error]")
        return

    console.print(f"[header]Scanning directory:[/header] [info]{args.dir}[/info]")

    unique_files = get_unique_pdfs(args.dir)
    console.print(f"[success]Found {len(unique_files)} unique PDFs.[/success]")

    if args.test and unique_files:
        unique_files = unique_files[:1]
        console.print(f"[warning]--- TEST MODE ACTIVE: Processing {os.path.basename(unique_files[0])} ---[/warning]")

    filtered_products = []

    for pdf_path in unique_files:
        filename = os.path.basename(pdf_path)
        console.print(f"[info]Processing {filename}...[/info]")
        
        data = extract_product_data(pdf_path)
        if not data:
            continue

        if data["weight_grams"] is not None and data["weight_grams"] < args.weight_limit:
            console.print(f"  [success]MATCH:[/success] {data['name']} ({data['weight_grams']}g)")
            filtered_products.append({
                "name": data["name"],
                "file": data["file"],
                "characteristics": data["characteristics"]
            })

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
    try:
        with open(DEFAULT_OUTPUT_FILE, "w") as f:
            f.write(formatted_json)
        console.print(f"\n[info]Results saved to: {os.path.abspath(DEFAULT_OUTPUT_FILE)}[/info]")
    except OSError as e:
        console.print(f"[error]Failed to save results to {DEFAULT_OUTPUT_FILE}: {e}[/error]")

if __name__ == "__main__":
    main()