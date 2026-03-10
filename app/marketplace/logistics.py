def get_shipping_estimate(origin: str, destination: str, weight_kg: float) -> dict:
    """Stub for getting a shipping estimate from a 3PL partner like ShipBob or Flexport."""
    # In a real system, this would make an API call.
    return {
        "provider": "Flexport",
        "estimated_cost": 50.0 + (weight_kg * 2.5),
        "estimated_days": 5,
        "currency": "USD"
    }

def create_shipment(order_id: int, items: list, destination_address: str) -> dict:
    """Stub for creating a shipment."""
    return {
        "tracking_number": f"TRK-{order_id}-12345",
        "provider": "Flexport",
        "status": "LABEL_CREATED"
    }

def get_tracking_events(tracking_number: str) -> list:
    """Stub for getting tracking events."""
    from datetime import datetime, timezone
    return [
        {"status": "LABEL_CREATED", "timestamp": datetime.now(timezone.utc).isoformat(), "location": "Warehouse"}
    ]
