import pytest
from unittest.mock import patch, MagicMock

import app.market_intelligence.websocket as ws_module
from app.market_intelligence.websocket import (
    init_websockets,
    broadcast_signal_update,
    broadcast_alert_fired
)

@pytest.fixture(autouse=True)
def reset_socketio():
    """Reset the global socketio object before each test"""
    ws_module.socketio = None
    yield
    ws_module.socketio = None

def test_init_websockets_with_socketio():
    app = MagicMock()
    with patch('app.market_intelligence.websocket.SocketIO') as mock_socketio, \
         patch('app.market_intelligence.websocket.has_socketio', True):
        
        init_websockets(app)
        
        mock_socketio.assert_called_once()
        assert ws_module.socketio is not None

def test_init_websockets_without_socketio():
    app = MagicMock()
    with patch('app.market_intelligence.websocket.has_socketio', False):
        init_websockets(app)
        assert ws_module.socketio is None

def test_broadcast_signal_update_no_category():
    ws_module.socketio = MagicMock()
    signal_data = {"key": "value"}
    
    broadcast_signal_update(signal_data)
    
    ws_module.socketio.emit.assert_called_once_with("signal_update", signal_data, namespace="/market")

def test_broadcast_signal_update_with_category():
    ws_module.socketio = MagicMock()
    signal_data = {"key": "value", "category_id": 123}
    
    broadcast_signal_update(signal_data)
    
    assert ws_module.socketio.emit.call_count == 2
    ws_module.socketio.emit.assert_any_call("signal_update", signal_data, namespace="/market")
    ws_module.socketio.emit.assert_any_call("signal_update", signal_data, room="category_123", namespace="/market")

def test_broadcast_signal_update_no_socketio():
    ws_module.socketio = None
    broadcast_signal_update({"key": "value"}) # Should not raise error

def test_broadcast_alert_fired_global():
    ws_module.socketio = MagicMock()
    alert_data = {"alert": "test"}
    
    broadcast_alert_fired(alert_data)
    
    ws_module.socketio.emit.assert_called_once_with("alert_fired", alert_data, room="global_alerts", namespace="/market")

def test_broadcast_alert_fired_merchant():
    ws_module.socketio = MagicMock()
    alert_data = {"alert": "test"}
    merchant_id = 456
    
    broadcast_alert_fired(alert_data, merchant_id=merchant_id)
    
    ws_module.socketio.emit.assert_called_once_with("alert_fired", alert_data, room="merchant_456", namespace="/market")

def test_broadcast_alert_fired_no_socketio():
    ws_module.socketio = None
    broadcast_alert_fired({"alert": "test"}) # Should not raise error
