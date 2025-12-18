import os
import re
import json
import argparse
import hashlib
import fitz  # PyMuPDF
from rich.console import Console
from rich.theme import Theme

# Initialize Rich Console with a custom theme
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "header": "bold blue underline"
})
console = Console(theme=custom_theme)

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

def extract_product_data(pdf_path):
    """Extracts text and parses characteristics from a PDF."""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + "\n"
        doc.close()

        # Split text into lines for parsing
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        # Simple heuristic: First line is often the Product Name
        product_name = lines[0] if lines else "Unknown Product"
        
        # Identify characteristics using a Key: Value pattern
        char_pattern = re.compile(r'^([\w\s/().-]+):\s*(.*)$', re.MULTILINE)
        matches = char_pattern.findall(full_text)
        
        characteristics = []
        weight_in_grams = None
        keywords = ["weight", "mass"]

        for key, val in matches:
            key_strip = key.strip()
            val_strip = val.strip()
            characteristics.append({key_strip: val_strip})
            
            # Check if this characteristic is weight/mass
            if any(kw in key_strip.lower() for kw in keywords):
                grams = normalize_to_grams(val_strip)
                if grams is not None and weight_in_grams is None:
                    weight_in_grams = grams

        # Fallback for weight if not found in "Key: Value" format
        if weight_in_grams is None:
            for keyword in keywords:
                for m in re.finditer(re.escape(keyword), full_text, re.IGNORECASE):
                    look_ahead = full_text[m.end():m.end() + 100]
                    grams = normalize_to_grams(look_ahead)
                    if grams is not None:
                        weight_in_grams = grams
                        characteristics.append({keyword.capitalize(): look_ahead.strip().split('\n')[0]})
                        break
                if weight_in_grams is not None:
                    break

        return {
            "name": product_name,
            "file": os.path.basename(pdf_path),
            "characteristics": characteristics,
            "weight_grams": weight_in_grams
        }
    except Exception as e:
        console.print(f"[error]Error processing {pdf_path}: {e}[/error]")
        return None

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
        unique_files = unique_files[:1]
        console.print(f"[warning]--- TEST MODE ACTIVE: Processing {os.path.basename(unique_files[0])} ---[/warning]")

    # --- Step 3 & 4: Extraction and Filtering ---
    filtered_products = []

    for pdf_path in unique_files:
        console.print(f"[info]Processing {os.path.basename(pdf_path)}...[/info]")
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
    output_file = "filtered_products.json"
    with open(output_file, "w") as f:
        f.write(formatted_json)
    
    console.print(f"\n[info]Results saved to: {os.path.abspath(output_file)}[/info]")

if __name__ == "__main__":
    main()