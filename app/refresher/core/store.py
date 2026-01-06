"""
Store module - Database operations for symlinks and actions.

This module provides backward-compatible functions for database operations.
All actual database logic is now handled by the central db module.
"""
from __future__ import annotations
import urllib.parse
from . import db

def url_encode(s: str) -> str:
    """URL encode a string."""
    return urllib.parse.quote(s, safe="")

# Re-export functions from central db module for backward compatibility
record_symlink = db.record_symlink
enqueue_action = db.enqueue_action
update_symlink_status = db.update_symlink_status

def get_pending(limit: int = 25):
    """Get pending actions (backward compatibility wrapper)."""
    return db.get_pending_actions(limit)

def mark_sent(action_id: int, ok: bool):
    """Mark action as sent (backward compatibility wrapper)."""
    return db.mark_action_sent(action_id, ok)
