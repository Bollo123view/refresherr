"""
Repair runner module for executing cinesync and ARR repairs.

This module provides functions to run repairs from different sources:
- Cinesync: Uses the cinesync_repair tool to fix broken symlinks
- ARR: Uses the queue_repairs and process_actions tools to trigger Sonarr/Radarr searches

After each repair run, it triggers a scan to update the database.
"""

from __future__ import annotations
import os
import sys
import sqlite3
import logging
import subprocess
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from . import db
from . import orchestrator

logger = logging.getLogger(__name__)


def run_cinesync_repair(
    trigger: str = "manual",
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Run a cinesync repair operation.
    
    This executes the cinesync_repair.py tool to attempt repairs using
    the CineSync library as a source for replacement files.
    
    Args:
        trigger: How the repair was triggered ("manual", "auto", "scheduled")
        conn: Optional database connection
        
    Returns:
        Dictionary with run results:
        - run_id: ID of the repair run
        - status: "completed" or "failed"
        - broken_found: Number of broken symlinks found
        - repaired: Number successfully repaired
        - skipped: Number skipped
        - failed: Number that failed repair
        - error_message: Error message if failed
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        # Create repair run record
        run_id = orchestrator.create_repair_run(
            repair_source="cinesync",
            trigger=trigger,
            run_type="repair",
            conn=conn
        )
        
        logger.info(f"Starting cinesync repair run {run_id} (trigger={trigger})")
        
        # Get broken symlinks count before repair
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM symlinks WHERE COALESCE(last_status, status) = 'broken'")
        broken_before = cur.fetchone()[0] or 0
        
        orchestrator.update_repair_run(
            run_id=run_id,
            broken_found=broken_before,
            conn=conn
        )
        
        # Execute cinesync repair tool
        try:
            # Build environment for cinesync repair
            env = os.environ.copy()
            env["CINESYNC_DRY_RUN"] = "0"  # Disable dry run for actual repair
            
            # Path to cinesync_repair tool
            tools_dir = Path(__file__).parent.parent / "tools"
            cinesync_script = tools_dir / "cinesync_repair.py"
            
            if not cinesync_script.exists():
                raise FileNotFoundError(f"Cinesync repair script not found: {cinesync_script}")
            
            # Run the cinesync repair
            result = subprocess.run(
                [sys.executable, str(cinesync_script)],
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            # Parse output to get stats (cinesync_repair logs repair counts)
            repaired = 0
            skipped = 0
            failed = 0
            
            # Try to parse output for stats
            for line in result.stdout.splitlines():
                if "repaired:" in line.lower():
                    try:
                        repaired = int(line.split(":")[-1].strip())
                    except (ValueError, IndexError):
                        pass
                elif "skipped:" in line.lower():
                    try:
                        skipped = int(line.split(":")[-1].strip())
                    except (ValueError, IndexError):
                        pass
                elif "failed:" in line.lower():
                    try:
                        failed = int(line.split(":")[-1].strip())
                    except (ValueError, IndexError):
                        pass
            
            # If we couldn't parse, estimate from broken count change
            if repaired == 0 and skipped == 0:
                cur.execute("SELECT COUNT(*) FROM symlinks WHERE COALESCE(last_status, status) = 'broken'")
                broken_after = cur.fetchone()[0] or 0
                repaired = max(0, broken_before - broken_after)
                skipped = broken_after
            
            # Update repair run with results
            orchestrator.update_repair_run(
                run_id=run_id,
                status="completed",
                repaired=repaired,
                skipped=skipped,
                failed=failed,
                conn=conn
            )
            
            logger.info(
                f"Cinesync repair run {run_id} completed: "
                f"repaired={repaired}, skipped={skipped}, failed={failed}"
            )
            
            # Trigger post-repair scan
            _trigger_post_repair_scan(conn)
            
            return {
                "run_id": run_id,
                "status": "completed",
                "broken_found": broken_before,
                "repaired": repaired,
                "skipped": skipped,
                "failed": failed,
                "error_message": None
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Cinesync repair run {run_id} failed: {error_msg}")
            
            orchestrator.update_repair_run(
                run_id=run_id,
                status="failed",
                error_message=error_msg,
                conn=conn
            )
            
            return {
                "run_id": run_id,
                "status": "failed",
                "broken_found": broken_before,
                "repaired": 0,
                "skipped": 0,
                "failed": broken_before,
                "error_message": error_msg
            }
    finally:
        if close_after:
            conn.close()


def run_arr_repair(
    trigger: str = "manual",
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Run an ARR (Sonarr/Radarr) repair operation.
    
    This queues repair actions and processes them via the relay service.
    
    Args:
        trigger: How the repair was triggered ("manual", "auto", "scheduled")
        conn: Optional database connection
        
    Returns:
        Dictionary with run results (same structure as run_cinesync_repair)
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        # Create repair run record
        run_id = orchestrator.create_repair_run(
            repair_source="arr",
            trigger=trigger,
            run_type="repair",
            conn=conn
        )
        
        logger.info(f"Starting ARR repair run {run_id} (trigger={trigger})")
        
        # Get broken symlinks count
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM symlinks WHERE COALESCE(last_status, status) = 'broken'")
        broken_before = cur.fetchone()[0] or 0
        
        orchestrator.update_repair_run(
            run_id=run_id,
            broken_found=broken_before,
            conn=conn
        )
        
        # Execute ARR repair
        try:
            # Path to repair tools
            tools_dir = Path(__file__).parent.parent / "tools"
            queue_script = tools_dir / "queue_repairs.py"
            process_script = tools_dir / "process_actions.py"
            
            if not queue_script.exists():
                raise FileNotFoundError(f"Queue repairs script not found: {queue_script}")
            
            if not process_script.exists():
                raise FileNotFoundError(f"Process actions script not found: {process_script}")
            
            # Build environment
            env = os.environ.copy()
            env["ACTIONS_DRY_RUN"] = "0"  # Disable dry run for actual repair
            
            # Step 1: Queue repairs
            logger.info(f"Queuing repairs for run {run_id}")
            queue_result = subprocess.run(
                [sys.executable, str(queue_script)],
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if queue_result.returncode != 0:
                raise RuntimeError(f"Queue repairs failed: {queue_result.stderr}")
            
            # Step 2: Process actions
            logger.info(f"Processing queued actions for run {run_id}")
            process_result = subprocess.run(
                [sys.executable, str(process_script)],
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if process_result.returncode != 0:
                raise RuntimeError(f"Process actions failed: {process_result.stderr}")
            
            # Parse results from process_actions output
            repaired = 0
            failed = 0
            
            for line in process_result.stdout.splitlines():
                if "sent:" in line.lower():
                    try:
                        repaired = int(line.split(":")[-1].strip())
                    except (ValueError, IndexError):
                        pass
                elif "failed:" in line.lower():
                    try:
                        failed = int(line.split(":")[-1].strip())
                    except (ValueError, IndexError):
                        pass
            
            # Estimate if we couldn't parse
            if repaired == 0:
                cur.execute("SELECT COUNT(*) FROM actions WHERE status = 'sent'")
                repaired = cur.fetchone()[0] or 0
            
            cur.execute("SELECT COUNT(*) FROM symlinks WHERE COALESCE(last_status, status) = 'broken'")
            broken_after = cur.fetchone()[0] or 0
            skipped = broken_after
            
            # Update repair run
            orchestrator.update_repair_run(
                run_id=run_id,
                status="completed",
                repaired=repaired,
                skipped=skipped,
                failed=failed,
                conn=conn
            )
            
            logger.info(
                f"ARR repair run {run_id} completed: "
                f"repaired={repaired}, skipped={skipped}, failed={failed}"
            )
            
            # Trigger post-repair scan
            _trigger_post_repair_scan(conn)
            
            return {
                "run_id": run_id,
                "status": "completed",
                "broken_found": broken_before,
                "repaired": repaired,
                "skipped": skipped,
                "failed": failed,
                "error_message": None
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"ARR repair run {run_id} failed: {error_msg}")
            
            orchestrator.update_repair_run(
                run_id=run_id,
                status="failed",
                error_message=error_msg,
                conn=conn
            )
            
            return {
                "run_id": run_id,
                "status": "failed",
                "broken_found": broken_before,
                "repaired": 0,
                "skipped": 0,
                "failed": broken_before,
                "error_message": error_msg
            }
    finally:
        if close_after:
            conn.close()


def _trigger_post_repair_scan(conn: sqlite3.Connection):
    """
    Trigger a scan after repair to update database with current symlink status.
    
    This imports and calls the scanner to update the database immediately after
    a repair run completes.
    """
    try:
        logger.info("Triggering post-repair scan")
        
        # Import scanner
        from refresher.core.scanner import scan_once
        from refresher.config import load_config
        
        # Load config
        config_path = os.environ.get("CONFIG_FILE", "/config/config.yaml")
        try:
            config = load_config(config_path)
            # Note: dryrun=True is correct here - it updates symlink status in DB
            # but doesn't enqueue new repair actions (we just finished repairs)
            result = scan_once(config, dryrun=True)
        except Exception:
            # Fallback to path-based loading
            result = scan_once(config_path, dryrun=True)
        
        logger.info(f"Post-repair scan completed: {result.get('summary', {})}")
        
    except Exception as e:
        logger.error(f"Post-repair scan failed: {e}")
        # Don't fail the repair run if scan fails


def run_orchestrated_repair(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Run the full orchestrated repair sequence: cinesync → arr.
    
    This is the main entry point for automatic repairs. It attempts cinesync
    first, then falls back to ARR for any remaining broken symlinks.
    
    Args:
        conn: Optional database connection
        
    Returns:
        Dictionary with combined results from both repair attempts
    """
    close_after = False
    if conn is None:
        conn = db.get_connection()
        close_after = True
    
    try:
        logger.info("Starting orchestrated repair sequence")
        
        # Step 1: Try cinesync repair
        cinesync_result = run_cinesync_repair(trigger="auto", conn=conn)
        
        # Step 2: Try ARR repair for remainders
        arr_result = run_arr_repair(trigger="auto", conn=conn)
        
        # Combine results
        total_broken = cinesync_result["broken_found"]
        total_repaired = cinesync_result["repaired"] + arr_result["repaired"]
        total_skipped = arr_result["skipped"]  # Use final count from ARR
        total_failed = cinesync_result["failed"] + arr_result["failed"]
        
        logger.info(
            f"Orchestrated repair completed: "
            f"total_broken={total_broken}, repaired={total_repaired}, "
            f"skipped={total_skipped}, failed={total_failed}"
        )
        
        return {
            "cinesync": cinesync_result,
            "arr": arr_result,
            "total": {
                "broken_found": total_broken,
                "repaired": total_repaired,
                "skipped": total_skipped,
                "failed": total_failed
            }
        }
        
    finally:
        if close_after:
            conn.close()
