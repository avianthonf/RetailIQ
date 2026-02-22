import pytest
from app.nlp.router import resolve_intent
from app.nlp.templates import format_percentage, format_currency, format_unit

def test_resolve_intent_precedence():
    # forecast > inventory > revenue > profit > top_products
    
    # Matching forecast
    assert resolve_intent("What is the expected demand?") == "forecast"
    assert resolve_intent("PREDICT sales for next week") == "forecast"
    
    # Matching inventory
    assert resolve_intent("Do we need to restock?") == "inventory"
    
    # Conflict: "predict inventory" -> forecast wins over inventory
    assert resolve_intent("Predict the inventory levels") == "forecast"
    
    # Conflict: "revenue profit" -> revenue wins over profit
    assert resolve_intent("Show me revenue and profit") == "revenue"
    
    # Conflict: "best products by margin" -> profit wins over top_products
    assert resolve_intent("Show best items by margin") == "profit"
    
    # Fallback
    assert resolve_intent("Hello there") == "default"
    assert resolve_intent("") == "default"
    
def test_resolve_too_long():
    long_query = "What is the forecast? " * 50 # > 200 chars
    assert resolve_intent(long_query) == "default"

def test_format_percentage():
    assert format_percentage(5.678) == "5.7%"
    assert format_percentage(-10.12) == "-10.1%"
    assert format_percentage(1.2) == "Stable (<2% change)"
    assert format_percentage(-1.9) == "Stable (<2% change)"
    assert format_percentage(0.0) == "0.0%"

def test_format_currency():
    assert format_currency(1234567.89) == "₹12,34,567.89"
    assert format_currency(500.0) == "₹500.00"
    assert format_currency(1000.5) == "₹1,000.50"
    assert format_currency(150000.0) == "₹1,50,000.00"

def test_format_unit():
    assert format_unit(1.0) == "1 unit"
    assert format_unit(5.0) == "5 units"
    assert format_unit(0.0) == "0 units"
    assert format_unit(1.0, "day") == "1 day"
    assert format_unit(7.0, "day") == "7 days"
