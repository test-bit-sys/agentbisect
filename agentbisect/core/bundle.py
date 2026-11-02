"""
Portable Evidence Bundle system for AgentBisect:
Allows exporting and importing full agent trajectory bundles (including shadow git objects and session logs)
for reproducible collaboration and issue reporting.
"""

from __future__ import annotations

import json
import os
import shutil
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
                    rel_p = full_p.relative_to(ws_path)
                    zip_f.write(full_p, arcname=str(rel_p))

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
            # Pre-validation pass: check all members before extracting anything
            for info in zip_f.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        f"Bundle exceeds maximum allowed uncompressed size ({MAX_BUNDLE_UNCOMPRESSED_BYTES} bytes)."
                    )

                # Check for symlink attribute
                is_symlink = (info.external_attr >> 16) & 0o120000 == 0o120000
                if is_symlink:
                    raise ValueError(f"Unsafe symlink entry detected in bundle: {info.filename}")

                norm_name = os.path.normpath(info.filename)
                if os.path.isabs(norm_name) or norm_name.startswith("..") or ("../" in info.filename) or ("..\\" in info.filename):
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

            # Safe extraction
            for info in zip_f.infolist():
                dest = (target_ws / os.path.normpath(info.filename)).resolve()
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zip_f.open(info) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        session_file = target_ws / ".agentbisect" / "current_session.json"
        if not session_file.exists():
            raise ValueError("Imported bundle did not contain a valid session.")

        session = AgentSession.load_json(session_file)
        # Update workspace root to current machine
        session.metadata.workspace_root = str(target_ws)
        session.save_json(session_file)
        return session
