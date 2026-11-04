"""deploy/start.py: copying the private data from a bucket keeps the folder layout and ignores folder placeholders and path tricks. No network."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("deploy_start", pathlib.Path("deploy") / "start.py")
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)


class Blob:
    def __init__(self, name):
        self.name = name

    def download_to_filename(self, path):
        pathlib.Path(path).write_text(self.name, encoding="utf-8")


class Client:
    def __init__(self, names):
        self.names, self.asked = names, []

    def list_blobs(self, bucket, prefix=None):
        self.asked.append((bucket, prefix))
        return [Blob(n) for n in self.names if prefix is None or n.startswith(prefix)]


def test_files_keep_their_relative_paths_and_placeholders_are_skipped(tmp_path):
    c = Client(["legal_store.sqlite", "search_index/", "search_index/tariff/emb.npy", "search_index/meta.json", "../escape.txt", "a/../../b.txt"])
    n = start.download_bucket(c, "my-bucket", "", tmp_path)
    assert n == 3 and c.asked == [("my-bucket", None)]
    assert (tmp_path / "legal_store.sqlite").exists() and (tmp_path / "search_index" / "tariff" / "emb.npy").exists()
    assert not (tmp_path.parent / "escape.txt").exists() and not (tmp_path / "b.txt").exists()


def test_a_prefix_is_stripped_from_the_local_paths(tmp_path):
    c = Client(["v1/legal_store.sqlite", "v1/search_index/notes/docs.jsonl", "other/x.txt"])
    assert start.download_bucket(c, "b", "v1", tmp_path) == 2 and c.asked == [("b", "v1/")]
    assert (tmp_path / "legal_store.sqlite").exists() and (tmp_path / "search_index" / "notes" / "docs.jsonl").exists()


# ---- data zip (Azure Blob SAS link, Google signed URL or any private file link) -------------------------------------------------------------
import hashlib
import io
import zipfile

import pytest


def make_zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_zip_keeps_the_layout_and_skips_path_tricks(tmp_path):
    z = tmp_path / "d.zip"
    z.write_bytes(make_zip({"legal_store.sqlite": b"a", "search_index/tariff/emb.npy": b"b", "../escape.txt": b"x", "a/../../b.txt": b"y", "/abs.txt": b"z", "C:/win.txt": b"w"}))
    dest = tmp_path / "out"
    assert start.extract_zip(z, dest) == 2
    assert (dest / "legal_store.sqlite").read_bytes() == b"a" and (dest / "search_index" / "tariff" / "emb.npy").read_bytes() == b"b"
    assert not (tmp_path / "escape.txt").exists() and not (dest / "b.txt").exists() and not (dest / "abs.txt").exists()


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def raise_for_status(self):
        return None

    def iter_content(self, n):
        for i in range(0, len(self.body), n):
            yield self.body[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_checks_the_sha256_and_never_unpacks_a_mismatch(tmp_path, monkeypatch):
    body = make_zip({"legal_store.sqlite": b"data"})
    monkeypatch.setattr("requests.get", lambda url, **kw: FakeResponse(body))
    assert start.download_zip("https://example.invalid/x?sig=SECRET", tmp_path / "ok", hashlib.sha256(body).hexdigest()) == 1
    assert (tmp_path / "ok" / "legal_store.sqlite").exists()
    with pytest.raises(SystemExit, match="does not match"):
        start.download_zip("https://example.invalid/x?sig=SECRET", tmp_path / "bad", "0" * 64)
    assert not (tmp_path / "bad").exists()


def test_the_azure_host_name_is_allowed_by_default():
    assert "*.azurecontainerapps.io" in start.PLATFORM_HOSTS


def test_pack_data_makes_a_zip_the_server_can_unpack(tmp_path):
    spec = importlib.util.spec_from_file_location("pack_data", pathlib.Path("deploy") / "pack_data.py")
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    src = tmp_path / "processed"
    (src / "search_index" / "tariff").mkdir(parents=True)
    (src / "legal_store.sqlite").write_bytes(b"db")
    (src / "search_index" / "tariff" / "emb.npy").write_bytes(b"np")
    (src / "search_index" / "meta.json").write_text("{}")
    size, sha, n = pack.pack(src, tmp_path / "out" / "d.zip")
    assert n == 3 and size > 0 and len(sha) == 64
    assert start.extract_zip(tmp_path / "out" / "d.zip", tmp_path / "dest") == 3 and (tmp_path / "dest" / "search_index" / "tariff" / "emb.npy").exists()
    with pytest.raises(SystemExit):
        pack.pack(tmp_path / "empty", tmp_path / "o2.zip")
