import hashlib
import re
from typing import Optional

class SpecScoutError(Exception):
    """Base exception for SpecScout CLI."""
    pass

class FileProcessingError(SpecScoutError):
    """Raised when a file cannot be processed."""
    pass

def get_file_hash(filepath: str) -> str:
    """
    Generate a SHA-256 hash to identify duplicate files by content.
    
    Args:
        filepath: Path to the file.
        
    Returns:
        The SHA-256 hash string.
        
    Raises:
        FileProcessingError: If the file cannot be read.
    """
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
    except OSError as e:
        raise FileProcessingError(f"Could not read file {filepath}: {e}")
    return hasher.hexdigest()

def normalize_to_grams(value_str: str) -> Optional[float]:
    """
    Parses strings like '1.2 kg' or '500 g' and returns weight in grams.
    
    Args:
        value_str: The string containing the weight specification.
        
    Returns:
        Weight in grams as a float, or None if no valid weight/unit is found.
    """
    # Regex to capture number and unit (g or kg)
    # Supports integers and decimals
    match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g)\b', value_str.lower())
    if not match:
        return None
    
    try:
        value = float(match.group(1))
        unit = match.group(2)
        
        if unit == 'kg':
            return value * 1000
        return value
    except (ValueError, IndexError):
        return None
