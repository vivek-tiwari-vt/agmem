"""
Remote sync for agmem - file-based push/pull/clone.

Supports file:// URLs for local or mounted directories.
"""

import json
import shutil
from pathlib import Path
from typing import Optional, Set
from urllib.parse import urlparse

from .objects import ObjectStore, Commit, Tree, Blob, _valid_object_hash
from .refs import RefsManager, _ref_path_under_root


def parse_remote_url(url: str) -> Path:
    """Parse remote URL to local path. Supports file:// only. Rejects path traversal."""
    parsed = urlparse(url)
    if parsed.scheme == "file" or parsed.scheme == "":
        path = parsed.path or parsed.netloc or url
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise ValueError(f"Remote path does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Remote path is not a directory: {resolved}")
        return resolved
    raise ValueError(f"Unsupported remote URL scheme: {parsed.scheme}. Use file://")


def _collect_objects_from_commit(store: ObjectStore, commit_hash: str) -> Set[str]:
    """Recursively collect all object hashes reachable from a commit."""
    seen = set()
    todo = [commit_hash]

    while todo:
        h = todo.pop()
        if h in seen:
            continue
        seen.add(h)

        # Try commit
        content = store.retrieve(h, "commit")
        if content:
            data = json.loads(content)
            todo.extend(data.get("parents", []))
            if "tree" in data:
                todo.append(data["tree"])
            continue

        # Try tree
        content = store.retrieve(h, "tree")
        if content:
            data = json.loads(content)
            for e in data.get("entries", []):
                if "hash" in e:
                    todo.append(e["hash"])
            continue

        # Blob - no follow

    return seen


def _list_local_objects(objects_dir: Path) -> Set[str]:
    """List all object hashes in a .mem/objects directory."""
    hashes = set()
    for obj_type in ["blob", "tree", "commit"]:
        type_dir = objects_dir / obj_type
        if not type_dir.exists():
            continue
        for prefix_dir in type_dir.iterdir():
            if prefix_dir.is_dir():
                for suffix_file in prefix_dir.iterdir():
                    hash_id = prefix_dir.name + suffix_file.name
                    hashes.add(hash_id)
    return hashes


def _get_object_path(objects_dir: Path, hash_id: str) -> Optional[Path]:
    """Get path for an object. Returns path if found, else None. Validates hash_id."""
    if not _valid_object_hash(hash_id):
        return None
    for otype in ["blob", "tree", "commit"]:
        p = objects_dir / otype / hash_id[:2] / hash_id[2:]
        if p.exists():
            return p
    return None


def _copy_object(src_dir: Path, dst_dir: Path, hash_id: str) -> bool:
    """Copy a single object. Returns True if copied. Validates hash_id."""
    if not _valid_object_hash(hash_id):
        return False
    src = _get_object_path(src_dir, hash_id)
    if not src or not src.exists():
        return False
    # Infer type from path (e.g. .../blob/xx/yy)
    obj_type = src.parent.parent.name
    dst = dst_dir / obj_type / hash_id[:2] / hash_id[2:]
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dst)
        return True
    return False


class Remote:
    """Remote repository for push/pull operations."""

    def __init__(self, repo_path: Path, name: str = "origin"):
        self.repo_path = Path(repo_path)
        self.mem_dir = self.repo_path / ".mem"
        self.objects_dir = self.mem_dir / "objects"
        self.name = name
        self._config = self._load_config()

    def _load_config(self) -> dict:
        config_file = self.mem_dir / "config.json"
        if config_file.exists():
            return json.loads(config_file.read_text())
        return {}

    def _save_config(self, config: dict):
        config_file = self.mem_dir / "config.json"
        config_file.write_text(json.dumps(config, indent=2))

    def get_remote_url(self) -> Optional[str]:
        """Get remote URL for the given name."""
        remotes = self._config.get("remotes", {})
        return remotes.get(self.name, {}).get("url")

    def set_remote_url(self, url: str):
        """Set remote URL."""
        if "remotes" not in self._config:
            self._config["remotes"] = {}
        if self.name not in self._config["remotes"]:
            self._config["remotes"][self.name] = {}
        self._config["remotes"][self.name]["url"] = url
        self._save_config(self._config)

    def push(self, branch: Optional[str] = None) -> str:
        """
        Push objects and refs to remote.
        Returns status message.
        """
        url = self.get_remote_url()
        if not url:
            raise ValueError(f"Remote '{self.name}' has no URL configured")

        remote_path = parse_remote_url(url)
        remote_mem = remote_path / ".mem"
        remote_objects = remote_mem / "objects"
        remote_refs = remote_mem / "refs"

        if not remote_path.exists():
            raise ValueError(f"Remote path does not exist: {remote_path}")

        remote_mem.mkdir(parents=True, exist_ok=True)
        remote_objects.mkdir(parents=True, exist_ok=True)
        (remote_refs / "heads").mkdir(parents=True, exist_ok=True)
        (remote_refs / "tags").mkdir(parents=True, exist_ok=True)

        refs = RefsManager(self.mem_dir)
        store = ObjectStore(self.objects_dir)

        # Push conflict detection: remote tip must be ancestor of local tip (non-fast-forward reject)
        remote_heads = remote_refs / "heads"
        for b in refs.list_branches():
            if branch and b != branch:
                continue
            local_ch = refs.get_branch_commit(b)
            if not local_ch:
                continue
            remote_branch_file = remote_heads / b
            if remote_branch_file.exists():
                remote_ch = remote_branch_file.read_text().strip()
                if remote_ch and _valid_object_hash(remote_ch):
                    from .merge import MergeEngine
                    from .repository import Repository
                    repo = Repository(self.repo_path)
                    engine = MergeEngine(repo)
                    if not engine.find_common_ancestor(remote_ch, local_ch) == remote_ch:
                        raise ValueError(
                            "Push rejected: remote has diverged. Pull and merge first."
                        )

        # Collect objects to push
        to_push = set()
        for b in refs.list_branches():
            if branch and b != branch:
                continue
            ch = refs.get_branch_commit(b)
            if ch:
                to_push.update(_collect_objects_from_commit(store, ch))
        for t in refs.list_tags():
            ch = refs.get_tag_commit(t)
            if ch:
                to_push.update(_collect_objects_from_commit(store, ch))

        remote_has = _list_local_objects(remote_objects)
        missing = to_push - remote_has

        # Copy objects
        copied = 0
        for h in missing:
            if _copy_object(self.objects_dir, remote_objects, h):
                copied += 1

        # Copy refs (validate names so remote path stays under refs/heads and refs/tags)
        remote_heads = remote_refs / "heads"
        remote_tags_dir = remote_refs / "tags"
        for b in refs.list_branches():
            if branch and b != branch:
                continue
            if not _ref_path_under_root(b, remote_heads):
                continue
            ch = refs.get_branch_commit(b)
            if ch:
                (remote_heads / b).parent.mkdir(parents=True, exist_ok=True)
                (remote_heads / b).write_text(ch + "\n")
        for t in refs.list_tags():
            if not _ref_path_under_root(t, remote_tags_dir):
                continue
            ch = refs.get_tag_commit(t)
            if ch:
                (remote_tags_dir / t).parent.mkdir(parents=True, exist_ok=True)
                (remote_tags_dir / t).write_text(ch + "\n")

        try:
            from .audit import append_audit
            append_audit(self.mem_dir, "push", {"remote": self.name, "branch": branch, "copied": copied})
        except Exception:
            pass
        return f"Pushed {copied} object(s) to {self.name}"

    def fetch(self, branch: Optional[str] = None) -> str:
        """
        Fetch objects and refs from remote into local.
        Returns status message.
        """
        url = self.get_remote_url()
        if not url:
            raise ValueError(f"Remote '{self.name}' has no URL configured")

        remote_path = parse_remote_url(url)
        remote_objects = remote_path / ".mem" / "objects"
        remote_refs = remote_path / ".mem" / "refs"

        if not remote_objects.exists():
            raise ValueError(f"Remote is not an agmem repository: {remote_path}")

        refs = RefsManager(self.mem_dir)
        remote_store = ObjectStore(remote_objects)

        # Collect remote refs to fetch (traverse remote's objects)
        to_fetch = set()
        heads_dir = remote_refs / "heads"
        if heads_dir.exists():
            for f in heads_dir.rglob("*"):
                if f.is_file():
                    branch_name = str(f.relative_to(heads_dir))
                    if branch is not None and branch_name != branch:
                        continue
                    ch = f.read_text().strip()
                    if ch and _valid_object_hash(ch):
                        to_fetch.update(_collect_objects_from_commit(remote_store, ch))
        tags_dir = remote_refs / "tags"
        if tags_dir.exists() and branch is None:
            for f in tags_dir.rglob("*"):
                if f.is_file():
                    ch = f.read_text().strip()
                    if ch and _valid_object_hash(ch):
                        to_fetch.update(_collect_objects_from_commit(remote_store, ch))

        local_has = _list_local_objects(self.objects_dir)
        missing = to_fetch - local_has

        copied = 0
        for h in missing:
            if _copy_object(remote_objects, self.objects_dir, h):
                copied += 1

        # Update remote-tracking refs (refs/remotes/<name>/<branch>), not local heads
        if heads_dir.exists():
            for f in heads_dir.rglob("*"):
                if f.is_file():
                    branch_name = str(f.relative_to(heads_dir))
                    if not _ref_path_under_root(branch_name, refs.heads_dir):
                        continue
                    ch = f.read_text().strip()
                    if ch:
                        refs.set_remote_branch_commit(self.name, branch_name, ch)
        if tags_dir.exists():
            for f in tags_dir.rglob("*"):
                if f.is_file():
                    tag_name = str(f.relative_to(tags_dir))
                    if not _ref_path_under_root(tag_name, refs.tags_dir):
                        continue
                    ch = f.read_text().strip()
                    if ch:
                        refs.create_tag(tag_name, ch)

        try:
            from .audit import append_audit
            append_audit(self.mem_dir, "fetch", {"remote": self.name, "branch": branch, "copied": copied})
        except Exception:
            pass
        return f"Fetched {copied} object(s) from {self.name}"
