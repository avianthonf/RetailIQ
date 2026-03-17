"""WebSocket routes for real-time data streaming."""

import json
import threading
import time

from flask import Flask, request

websocket_bp = None  # Will be initialized after app creation


def init_websocket(app: Flask):
    """Initialize WebSocket support."""
    global websocket_bp

    @app.route("/ws")
    def websocket_handler():
        """Simple WebSocket-like endpoint for development."""
        # For now, return a simple response
        # In production, this would be a proper WebSocket server
        return "", 200
