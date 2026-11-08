"""Isolated test workspaces with inherited Windows workspace permissions."""
from contextlib import contextmanager
import shutil
import uuid

from src.collect.common import REPO_ROOT


@contextmanager
def temporary_workspace():
    # Python 3.12's TemporaryDirectory uses mkdir(mode=0o700), whose Windows
    # ACL is inaccessible to this restricted desktop runner. Inherit the
    # writable workspace ACL instead; every test owns a unique directory.
    parent = (REPO_ROOT / "outputs/a2_cvpr2024").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / ("a2test_" + uuid.uuid4().hex)
    path.mkdir(mode=0o755)
    try:
        yield path
    finally:
        target = path.resolve()
        if target.parent != parent or not target.name.startswith("a2test_"):
            raise ValueError("Refusing to remove a directory outside the test workspace")
        shutil.rmtree(target)
