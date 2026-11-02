"""
Portable Evidence Bundle system for AgentBisect:
Allows exporting and importing full agent trajectory bundles (including shadow git objects and session logs)
for reproducible collaboration and issue reporting.
"""

from __future__ import annotations

import json
import ntpath
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from agentbisect.core.models import AgentSession

# Maximum allowed uncompressed size for safety (500 MB)
MAX_BUNDLE_UNCOMPRESSED_BYTES = 500 * 1024 * 1024


class BundleManager:
    """Manages packaging and safe un-packaging of portable .bisect bundles."""

    @staticmethod
    def export_bundle(workspace_root: Path | str, output_path: Optional[Path | str] = None) -> Path:
        ws_path = Path(workspace_root).resolve()
        dot_bisect = ws_path / ".agentbisect"

        if not dot_bisect.exists():
            raise FileNotFoundError(f"No .agentbisect directory found in {ws_path}")

        session_file = dot_bisect / "current_session.json"
        session_id = "unknown_session"
        if session_file.exists():
            try:
                session = AgentSession.load_json(session_file)
                session_id = session.metadata.session_id
            except Exception:
                pass

        if output_path:
            out_file = Path(output_path).resolve()
        else:
            out_file = ws_path / f"{session_id}.bisect.zip"

        out_file.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as zip_f:
            for root, _, files in shutil.os.walk(dot_bisect):
                for f in files:
                    full_p = Path(root) / f
                    # Skip the archive itself if created inside .agentbisect
                    if full_p.resolve() == out_file.resolve():
                        continue
                    # Exclude lock files and temporary files
                    if f.endswith(".lock") or f.endswith(".tmp") or f == "agentbisect.lock":
                        continue
                    rel_p = full_p.relative_to(ws_path)
                    zip_f.write(full_p, arcname=rel_p.as_posix())

        return out_file

    @staticmethod
    def import_bundle(bundle_path: Path | str, target_workspace: Path | str) -> AgentSession:
        b_path = Path(bundle_path).resolve()
        target_ws = Path(target_workspace).resolve()

        if not b_path.exists():
            raise FileNotFoundError(f"Bundle file not found: {b_path}")

        target_ws.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(b_path, "r") as zip_f:
            total_uncompressed = 0
            seen_entries = set()

            # Pre-validation pass: check all members before extracting anything
            for info in zip_f.infolist():
                if info.filename in seen_entries:
                    raise ValueError(f"Duplicate entry detected in bundle: {info.filename}")
                seen_entries.add(info.filename)

                total_uncompressed += info.file_size
                if total_uncompressed > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        f"Bundle exceeds maximum allowed uncompressed size ({MAX_BUNDLE_UNCOMPRESSED_BYTES} bytes)."
                    )

                # Check for symlink attribute
                is_symlink = (info.external_attr >> 16) & 0o120000 == 0o120000
                if is_symlink:
                    raise ValueError(f"Unsafe symlink entry detected in bundle: {info.filename}")

                norm_name = os.path.normpath(info.filename.replace("\\", "/"))
                # Disallow Windows drive letters (e.g. C:foo, C:\foo) and path traversals across all platforms
                has_drive = bool(
                    ntpath.splitdrive(norm_name)[0]
                    or ntpath.splitdrive(info.filename)[0]
                    or os.path.splitdrive(norm_name)[0]
                )
                if (
                    has_drive
                    or os.path.isabs(norm_name)
                    or norm_name.startswith("..")
                    or ("../" in info.filename)
                    or ("..\\" in info.filename)
                ):
                    raise ValueError(f"Path traversal detected in bundle entry: {info.filename}")

                dest = (target_ws / norm_name).resolve()
                try:
                    dest.relative_to(target_ws)
                except ValueError:
                    raise ValueError(f"Target destination outside workspace for entry: {info.filename}")

                # Verify entry is strictly scoped to .agentbisect
                rel_to_target = dest.relative_to(target_ws)
                parts = rel_to_target.parts
                if not parts or parts[0] != ".agentbisect":
                    raise ValueError(f"Bundle contains file outside .agentbisect: {info.filename}")

            # Transactional extraction via temporary directory to prevent corrupting workspace on error
            parent_dir = target_ws.parent if target_ws.parent.exists() else None
            with tempfile.TemporaryDirectory(dir=parent_dir) as tmp_dir:
                tmp_path = Path(tmp_dir)
                for info in zip_f.infolist():
                    dest = (tmp_path / os.path.normpath(info.filename.replace("\\", "/"))).resolve()
                    if info.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zip_f.open(info) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)

                session_file = tmp_path / ".agentbisect" / "current_session.json"
                if not session_file.exists():
                    raise ValueError("Imported bundle did not contain a valid session.")

                # Clean up any stale lock files from imported bundle
                for lock_file in (tmp_path / ".agentbisect").rglob("*.lock"):
                    try:
                        lock_file.unlink()
                    except OSError:
                        pass

                session = AgentSession.load_json(session_file)
                # Update workspace root to current machine
                session.metadata.workspace_root = str(target_ws)
                session.save_json(session_file)

                # Atomically sync .agentbisect into target workspace with safe rollback
                target_dot_bisect = target_ws / ".agentbisect"
                backup_dot_bisect = target_ws / ".agentbisect_backup"
                if backup_dot_bisect.exists():
                    shutil.rmtree(backup_dot_bisect)

                has_existing = target_dot_bisect.exists()
                if has_existing:
                    shutil.move(str(target_dot_bisect), str(backup_dot_bisect))

                try:
                    shutil.copytree(tmp_path / ".agentbisect", target_dot_bisect)
                    if has_existing and backup_dot_bisect.exists():
                        shutil.rmtree(backup_dot_bisect)
                except Exception:
                    # Roll back to preserved original data
                    if target_dot_bisect.exists():
                        shutil.rmtree(target_dot_bisect)
                    if has_existing and backup_dot_bisect.exists():
                        shutil.move(str(backup_dot_bisect), str(target_dot_bisect))
                    raise

                return session
