"""Server-side workspace selection. Not public signup or production authentication.

A caller must obtain the opaque tenant ID from a verified, server-side session.
Never use a request parameter, phone number or path supplied by the browser.
Each tenant gets a distinct Store, preserving the existing meeting logic without
letting a missed meeting-filter leak another tenant's transcript or outbox.
"""
from pathlib import Path
import os
import re
from .store import Store

TENANT = re.compile(r'^[0-9a-f]{32}$')


def tenant_store(root, verified_tenant_id):
    if not isinstance(verified_tenant_id, str) or not TENANT.fullmatch(verified_tenant_id):
        raise ValueError('Verified workspace required')
    base = Path(root).resolve()
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace = base / verified_tenant_id
    # Never follow a tenant directory or database symlink into another workspace.
    if workspace.is_symlink():
        raise ValueError('Workspace path refused')
    workspace.mkdir(mode=0o700, exist_ok=True)
    if workspace.resolve().parent != base:
        raise ValueError('Workspace path refused')
    os.chmod(workspace, 0o700)
    database = workspace / 'meeting.db'
    if database.is_symlink():
        raise ValueError('Workspace database path refused')
    return Store(database)
