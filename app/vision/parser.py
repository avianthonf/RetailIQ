import contextlib
import re
from typing import List, Optional, TypedDict


class ParsedLineItem(TypedDict):
    raw_text: str
    product_name: str
    quantity: float | None
    unit_price: float | None
    unit: str | None


def parse_invoice_text(raw_text: str) -> list[ParsedLineItem]:
    """
    Parses OCR text of an invoice to extract line items.
    Looks for quantities (e.g. 5 pcs) and unit prices (e.g. ₹1,200).
    Handles multi-line items by accumulating text until a quantity or price is found.
    """
    MAX_OCR_TEXT_LENGTH = 50_000
    raw_text = raw_text[:MAX_OCR_TEXT_LENGTH]

    lines = raw_text.split("\n")
    results: list[ParsedLineItem] = []

    # Regex to capture things like: 5 pcs, 10.5 kg, 12 nos
    qty_regex = re.compile(r"\b(\d+(?:\.\d+)?)\s*(pcs|kg|units|nos|g|ml|l|ltrs?)\b", re.IGNORECASE)
    # Regex to capture things like: ₹1,200.50, Rs 500, Rs. 10
    price_regex = re.compile(r"(?:₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)

    pending_name_parts = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        qty_match = qty_regex.search(line)
        price_match = price_regex.search(line)

        if qty_match or price_match:
            # Found a line with quantity or price
            qty_val = None
            unit_val = None
            price_val = None

            clean_line = line

            if qty_match:
                try:
                    qty_val = float(qty_match.group(1))
                    unit_val = qty_match.group(2).lower()
                except ValueError:
                    pass
                clean_line = clean_line.replace(qty_match.group(0), "")

            if price_match:
                price_str = price_match.group(1).replace(",", "")
                with contextlib.suppress(ValueError):
                    price_val = float(price_str)
                clean_line = clean_line.replace(price_match.group(0), "")

            # Clean remaining text for the name
            name_on_line = re.sub(r"[^a-zA-Z0-9\s\-&]", " ", clean_line).strip()
            # Remove multiple spaces
            name_on_line = re.sub(r"\s+", " ", name_on_line)

            if name_on_line:
                pending_name_parts.append(name_on_line)

            final_name = " ".join(pending_name_parts).strip()
            # If we simply couldn't find a product name, mark as Unknown
            if not final_name:
                final_name = "Unknown Product"

            results.append(
                {
                    "raw_text": line,
                    "product_name": final_name,
                    "quantity": qty_val,
                    "unit_price": price_val,
                    "unit": unit_val,
                }
            )

            # Reset after consumption
            pending_name_parts = []
        else:
            # Line without qty/price — accumulate as product name
            clean_text = re.sub(r"[^a-zA-Z0-9\s\-&]", " ", line).strip()
            clean_text = re.sub(r"\s+", " ", clean_text)

            # Ignore very short noisy lines (e.g. single chars, strange puncs)
            if len(clean_text) >= 2:
                pending_name_parts.append(clean_text)

    return results
