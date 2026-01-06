"""
Auto-repair orchestrator for Refresherr.

This module manages the automatic repair workflow:
1. Monitors symlink scan results
2. Coordinates repair attempts (cinesync → arr → manual)
3. Tracks repair statistics and history
4. Provides toggle control (OFF by default)

The orchestrator is controlled by a database-backed state that can be toggled
via API or CLI. When enabled, it automatically attempts repairs for broken
symlinks discovered by the scanner.
"""

from __future__ import annotations
import os
import sqlite3
import datetime as dt
import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from . import db

logger = logging.getLogger(__name__)


# ============================================================================
# Orchestrator State Management
# ============================================================================

def get_orchestrator_state(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Get the current orchestrator state.
    
    Returns:
        Dictionary with keys:
        - enabled: bool - whether auto-repair is enabled
        - last_auto_run_utc: str - timestamp of last automatic run
        - updated_utc: str - when state was last modified
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        row = conn.execute(
            "SELECT enabled, last_auto_run_utc, updated_utc FROM orchestrator_state WHERE id = 1"
        ).fetchone()
        
        if row:
            return {
                "enabled": bool(row[0]),
                "last_auto_run_utc": row[1],
                "updated_utc": row[2]
            }
        else:
            # Initialize if not exists (shouldn't happen with migration)
            conn.execute(
                "INSERT OR IGNORE INTO orchestrator_state (id, enabled, updated_utc) VALUES (1, 0, ?)",
                (dt.datetime.utcnow().isoformat(),)
            )
            conn.commit()
            return {
                "enabled": False,
                "last_auto_run_utc": None,
                "updated_utc": dt.datetime.utcnow().isoformat()
            }
    finally:
        if close_after:
            conn.close()


def set_orchestrator_enabled(enabled: bool, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Enable or disable the auto-repair orchestrator.
    
    Args:
        enabled: True to enable auto-repair, False to disable
        conn: Optional database connection
        
    Returns:
        Updated orchestrator state
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        now = dt.datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE orchestrator_state SET enabled = ?, updated_utc = ? WHERE id = 1",
            (1 if enabled else 0, now)
        )
        conn.commit()
        
        logger.info(f"Orchestrator {'enabled' if enabled else 'disabled'}")
        
        return get_orchestrator_state(conn)
    finally:
        if close_after:
            conn.close()


def update_last_auto_run(conn: Optional[sqlite3.Connection] = None):
    """Update the last_auto_run_utc timestamp."""
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        now = dt.datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE orchestrator_state SET last_auto_run_utc = ? WHERE id = 1",
            (now,)
        )
        conn.commit()
    finally:
        if close_after:
            conn.close()


# ============================================================================
# Repair Run Management
# ============================================================================

def create_repair_run(
    repair_source: str,
    trigger: str = "manual",
    run_type: str = "repair",
    conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Create a new repair run record.
    
    Args:
        repair_source: Source of repair (e.g., "cinesync", "arr", "manual")
        trigger: How the run was triggered ("manual", "auto", "scheduled")
        run_type: Type of run ("repair", "scan")
        conn: Optional database connection
        
    Returns:
        ID of the created repair run
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        now = dt.datetime.utcnow().isoformat()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO repair_runs 
            (run_type, repair_source, status, trigger, started_utc)
            VALUES (?, ?, 'running', ?, ?)
            """,
            (run_type, repair_source, trigger, now)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close_after:
            conn.close()


def update_repair_run(
    run_id: int,
    status: Optional[str] = None,
    broken_found: Optional[int] = None,
    repaired: Optional[int] = None,
    skipped: Optional[int] = None,
    failed: Optional[int] = None,
    error_message: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None
):
    """
    Update a repair run with new statistics or status.
    
    Args:
        run_id: ID of the repair run to update
        status: New status ("running", "completed", "failed")
        broken_found: Number of broken symlinks found
        repaired: Number successfully repaired
        skipped: Number skipped
        failed: Number that failed repair
        error_message: Error message if run failed
        conn: Optional database connection
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        updates = []
        params = []
        
        if status is not None:
            updates.append("status = ?")
            params.append(status)
            if status in ("completed", "failed"):
                updates.append("completed_utc = ?")
                params.append(dt.datetime.utcnow().isoformat())
        
        if broken_found is not None:
            updates.append("broken_found = ?")
            params.append(broken_found)
        
        if repaired is not None:
            updates.append("repaired = ?")
            params.append(repaired)
        
        if skipped is not None:
            updates.append("skipped = ?")
            params.append(skipped)
        
        if failed is not None:
            updates.append("failed = ?")
            params.append(failed)
        
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        
        if updates:
            params.append(run_id)
            conn.execute(
                f"UPDATE repair_runs SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()
    finally:
        if close_after:
            conn.close()


def add_repair_stat(
    run_id: int,
    symlink_path: str,
    result: str,
    details: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None
):
    """
    Add a repair statistic entry for a specific symlink.
    
    Args:
        run_id: ID of the repair run
        symlink_path: Path to the symlink being repaired
        result: Result of repair attempt ("repaired", "skipped", "failed")
        details: Additional details about the repair
        conn: Optional database connection
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        now = dt.datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO repair_stats (run_id, symlink_path, result, details, timestamp_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, symlink_path, result, details, now)
        )
        conn.commit()
    finally:
        if close_after:
            conn.close()


def get_repair_run(run_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """
    Get details of a specific repair run.
    
    Args:
        run_id: ID of the repair run
        conn: Optional database connection
        
    Returns:
        Dictionary with run details or None if not found
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        row = conn.execute(
            """
            SELECT id, run_type, repair_source, status, trigger, started_utc, completed_utc,
                   broken_found, repaired, skipped, failed, error_message
            FROM repair_runs
            WHERE id = ?
            """,
            (run_id,)
        ).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "run_type": row[1],
            "repair_source": row[2],
            "status": row[3],
            "trigger": row[4],
            "started_utc": row[5],
            "completed_utc": row[6],
            "broken_found": row[7],
            "repaired": row[8],
            "skipped": row[9],
            "failed": row[10],
            "error_message": row[11]
        }
    finally:
        if close_after:
            conn.close()


def get_repair_history(
    limit: int = 50,
    offset: int = 0,
    conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """
    Get repair run history.
    
    Args:
        limit: Maximum number of runs to return
        offset: Offset for pagination
        conn: Optional database connection
        
    Returns:
        List of repair run dictionaries, newest first
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        rows = conn.execute(
            """
            SELECT id, run_type, repair_source, status, trigger, started_utc, completed_utc,
                   broken_found, repaired, skipped, failed, error_message
            FROM repair_runs
            ORDER BY started_utc DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        ).fetchall()
        
        return [
            {
                "id": row[0],
                "run_type": row[1],
                "repair_source": row[2],
                "status": row[3],
                "trigger": row[4],
                "started_utc": row[5],
                "completed_utc": row[6],
                "broken_found": row[7],
                "repaired": row[8],
                "skipped": row[9],
                "failed": row[10],
                "error_message": row[11]
            }
            for row in rows
        ]
    finally:
        if close_after:
            conn.close()


def get_current_repair_run(conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """
    Get the currently running repair run, if any.
    
    Args:
        conn: Optional database connection
        
    Returns:
        Dictionary with run details or None if no run is active
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        row = conn.execute(
            """
            SELECT id, run_type, repair_source, status, trigger, started_utc, completed_utc,
                   broken_found, repaired, skipped, failed, error_message
            FROM repair_runs
            WHERE status = 'running'
            ORDER BY started_utc DESC
            LIMIT 1
            """,
        ).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "run_type": row[1],
            "repair_source": row[2],
            "status": row[3],
            "trigger": row[4],
            "started_utc": row[5],
            "completed_utc": row[6],
            "broken_found": row[7],
            "repaired": row[8],
            "skipped": row[9],
            "failed": row[10],
            "error_message": row[11]
        }
    finally:
        if close_after:
            conn.close()
