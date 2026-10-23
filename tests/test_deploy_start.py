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
