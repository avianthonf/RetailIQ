"""
WebSocket streaming service for real-time market signals.
"""

import logging
from typing import Any, Dict, Optional

# flask-socketio handles WS upgrades, pub/sub, and reconnections
try:
    from flask_socketio import SocketIO, emit, join_room, leave_room

    has_socketio = True
except ImportError:
    has_socketio = False

logger = logging.getLogger(__name__)

# This will be initialized in app/__init__.py
socketio: Any | None = None


def init_websockets(app):
    """Initialize SocketIO with the Flask app"""
    global socketio
    if not has_socketio:
        logger.warning("flask-socketio not installed. WebSocket streaming disabled.")
        return

    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="threading",  # safe default for dev
        logger=False,
        engineio_logger=False,
    )

    # Register event handlers
    @socketio.on("connect", namespace="/market")
    def handle_connect():
        # In a real app, validate token here
        logger.info("Client connected to /market websocket namespace")
        emit("connection_status", {"status": "connected", "message": "Welcome to Real-Time Intelligence Stream"})

    @socketio.on("disconnect", namespace="/market")
    def handle_disconnect():
        logger.info("Client disconnected from /market websocket")

    @socketio.on("subscribe", namespace="/market")
    def handle_subscribe(data):
        """
        Subscribe to a specific topic channel (e.g. category updates).
        Data should contain {'topic': 'category_1' or 'global_alerts'}
        """
        topic = data.get("topic")
        if topic:
            join_room(topic)
            logger.info(f"Client subscribed to topic: {topic}")
            emit("subscription_status", {"topic": topic, "status": "subscribed"})

    @socketio.on("unsubscribe", namespace="/market")
    def handle_unsubscribe(data):
        topic = data.get("topic")
        if topic:
            leave_room(topic)
            logger.info(f"Client unsubscribed from topic: {topic}")
            emit("subscription_status", {"topic": topic, "status": "unsubscribed"})


def broadcast_signal_update(signal_data: dict[str, Any]):
    """
    Push a new market signal to all subscribed clients.
    Called from ingestion pipelines.
    """
    if not socketio:
        return

    category_id = signal_data.get("category_id")

    # Broadcast to generic namespace channel
    socketio.emit("signal_update", signal_data, namespace="/market")

    # Broadcast to specific category channel if applicable
    if category_id:
        room = f"category_{category_id}"
        socketio.emit("signal_update", signal_data, room=room, namespace="/market")


def broadcast_alert_fired(alert_data: dict[str, Any], merchant_id: int | None = None):
    """
    Push an alert event immediately to connected dashboards.
    """
    if not socketio:
        return

    # Typically broadcast locally or to single merchant
    room = f"merchant_{merchant_id}" if merchant_id else "global_alerts"
    socketio.emit("alert_fired", alert_data, room=room, namespace="/market")
