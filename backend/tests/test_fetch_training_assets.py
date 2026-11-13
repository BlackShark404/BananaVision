"""Release fetch, verification and safe extraction with a fake HTTP opener and a fake gh.

No network, no real dataset or weights: archives are built in tmp_path.
"""

import fnmatch
import hashlib
import http.client
import io
import json
import lzma
import random
import shutil
import stat
import struct
import subprocess
import tarfile
import traceback
import urllib.error
import zipfile
import zlib
from pathlib import Path

import pytest

from scripts import fetch_training_assets as fetch
from scripts.fetch_training_assets import FetchError, Limits
from scripts.prepare_yolo_dataset import EXPECTED_NAMES
from scripts.train_finger_model import TrainingError, check_names, check_split_paths

SENTINEL = "ghp_SENTINEL0token0value0never0shown0123"
REPO = "acme/bananas"
TAG = "v1.2"
API = f"https://api.github.com/repos/{REPO}"
RELEASE_URL = f"{API}/releases/tags/{TAG}"
WEIGHTS = b"not a real checkpoint"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_files(prefix: str = "") -> dict[str, bytes]:
    """A tiny Roboflow-style YOLO export with the 12 expected classes."""
    yaml = (
        "train: ../train/images\nval: ../valid/images\ntest: ../test/images\n"
        f"nc: 12\nnames: {json.dumps(EXPECTED_NAMES)}\n"
    )
    files = {f"{prefix}data.yaml": yaml.encode(), f"{prefix}README.roboflow.txt": b"export"}
    for split in ("train", "valid", "test"):
        stem = f"B1_Lakatan_0000{len(split)}_top_jpg.rf.abc"
        files[f"{prefix}{split}/images/{stem}.jpg"] = b"\xff\xd8 fake jpeg"
        files[f"{prefix}{split}/labels/{stem}.txt"] = b"4 0.5 0.5 0.2 0.3\n"
    return files


def zip_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(zipfile.ZipInfo(name, (2026, 11, 13, 9, 0, 0)), data)
    return stream.getvalue()


def write_zip(path: Path, entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, data in entries:
            if isinstance(info, str):
                info = zipfile.ZipInfo(info, (2026, 11, 13, 9, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return path


def write_tar(path: Path, entries: list[tuple[tarfile.TarInfo, bytes | None]]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for info, data in entries:
            if data is None:
                archive.addfile(info)
            else:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return path


def tar_info(name: str, kind: bytes = tarfile.REGTYPE, **fields) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = kind
    for key, value in fields.items():
        setattr(info, key, value)
    return info


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers: dict | None = None):
        super().__init__(body)
        self.status = 200
        self.headers = {"Content-Length": str(len(body))} if headers is None else headers


class CutOffResponse(FakeResponse):
    """The connection drops after the first chunk."""

    def read(self, size=-1):
        if self.tell():
            raise http.client.IncompleteRead(b"partial", 10)
        return super().read(4)


class FakeOpener:
    """Serves one release; records every request so tests can inspect headers."""

    def __init__(
        self, assets: dict[str, bytes], *, sizes=None, urls=None, fail=None,
        release_url=RELEASE_URL, own_url=None, cut_off=(),
    ):
        self.assets = assets
        self.sizes = sizes or {}
        self.urls = urls or {}
        self.fail = fail or {}
        self.release_url, self.own_url, self.cut_off = release_url, own_url, cut_off
        self.requests = []

    def release(self) -> dict:
        own = {"url": self.own_url} if self.own_url else {}
        return {"tag_name": TAG, **own, "assets": [
            {
                "name": name, "size": self.sizes.get(name, len(data)),
                "url": self.urls.get(name, f"{API}/releases/assets/{index}"),
                "browser_download_url": f"https://github.com/{REPO}/releases/download/x/{name}",
            }
            for index, (name, data) in enumerate(self.assets.items(), 1)
        ]}

    def open(self, request, timeout=None):
        assert timeout and timeout > 0
        self.requests.append(request)
        url = request.full_url
        if url in self.fail:
            raise self.fail[url]
        if url == self.release_url:
            return FakeResponse(json.dumps(self.release()).encode())
        index = int(url.rsplit("/", 1)[1])
        name, data = list(self.assets.items())[index - 1]
        return (CutOffResponse if name in self.cut_off else FakeResponse)(data, headers={})


def release(**extra) -> dict[str, bytes]:
    archive = zip_bytes(export_files())
    sums = f"{sha(archive)}  export.zip\n{sha(WEIGHTS)} *best.pt\n".encode()
    return {"export.zip": archive, "best.pt": WEIGHTS, "SHA256SUMS": sums, **extra}


def api_fetch(dest: Path, assets: dict[str, bytes], **kwargs):
    opener = kwargs.pop("opener", None) or FakeOpener(assets)
    report = fetch.fetch_github(REPO, TAG, dest, method="api", opener=opener, **kwargs)
    return report, opener


def tree(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def write_tree(root: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return root


@pytest.fixture(autouse=True)
def no_ambient_tokens(monkeypatch):
    """Only tokens a test sets itself are visible to the script."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "BV_RELEASE_TOKEN"):
        monkeypatch.delenv(name, raising=False)


# ── GitHub API path ────────────────────────────────────────────────────────────


def test_api_download_verifies_extracts_and_reports_layout(tmp_path):
    dest = tmp_path / "assets"
    report, opener = api_fetch(dest, release())

    assert report["source"]["method"] == "api"
    assert report["source"]["authenticated"] is False
    assert report["fetched_at"].endswith("+08:00")
    assert report["checksums"]["verified"] == ["best.pt", "export.zip"]
    assert {item["name"]: item["sha256"] for item in report["files"]}["best.pt"] == sha(WEIGHTS)
    assert [item["into"] for item in report["extracted"]] == [str(dest / "export")]
    assert (dest / "export" / "valid" / "labels").is_dir()

    [export] = report["layout"]["yolo_exports"]
    assert export["path"] == str(dest / "export")
    assert export["kind"] == "yolo_export" and export["roboflow"] is True
    assert export["missing_splits"] == []
    assert export["splits"]["train"] == {"images": 1, "labels": 1, "images_without_labels": 0}
    assert export["matches_expected_classes"] and export["expected_class_order"]
    assert report["layout"]["weights"] == [
        {"path": str(dest / "best.pt"), "bytes": len(WEIGHTS), "sha256": sha(WEIGHTS)}
    ]
    prepared = dest / "prepared"
    assert report["next_commands"] == [
        f"python scripts/prepare_yolo_dataset.py --source {dest / 'export'} --output {prepared}",
        f"python scripts/evaluate_finger_count.py visible --weights {dest / 'best.pt'} "
        f"--split {prepared / 'valid'} --output finger-count-prepared-valid.json",
        f"python scripts/train_finger_model.py --data {prepared} "
        f"--weights {dest / 'best.pt'} --dry-run",
    ]
    # Release metadata first, then each asset through its API URL as a byte stream.
    assert opener.requests[0].full_url == RELEASE_URL
    assert {request.get_header("Accept") for request in opener.requests[1:]} == {
        "application/octet-stream"
    }
    assert all(not request.has_header("Authorization") for request in opener.requests)
    assert not any(name.endswith(".part") for name in tree(dest))
    assert report["warnings"] == [
        "Weights are pickles: load them only from a source you trust."
    ]


def test_api_pattern_limits_assets_and_always_fetches_checksums(tmp_path):
    assets = release(**{"notes.txt": b"hello"})
    report, _ = api_fetch(tmp_path / "dest", assets, patterns=["*.zip"])
    assert sorted(item["name"] for item in report["files"]) == ["SHA256SUMS", "export.zip"]
    assert report["checksums"]["entries_not_downloaded"] == ["best.pt"]
    assert not (tmp_path / "dest" / "best.pt").exists()

    with pytest.raises(FetchError, match="matches"):
        api_fetch(tmp_path / "other", assets, patterns=["*.tar.gz"])


@pytest.mark.parametrize(
    ("sums", "message"),
    [
        (lambda a: f"{'0' * 64}  export.zip\n{sha(WEIGHTS)}  best.pt\n", "SHA-256 mismatch"),
        (lambda a: f"{sha(WEIGHTS)}  best.pt\n", "No SHA256SUMS entry for export.zip"),
        (lambda a: f"{sha(a)} export.zip\n", "Malformed SHA256SUMS line 1"),
        (lambda a: "", "lists no files"),
    ],
    ids=["mismatch", "missing-entry", "malformed", "empty"],
)
def test_checksum_failure_removes_downloads_and_extracts_nothing(tmp_path, sums, message):
    assets = release()
    assets["SHA256SUMS"] = sums(assets["export.zip"]).encode()
    dest = tmp_path / "dest"
    with pytest.raises(FetchError, match=message):
        api_fetch(dest, assets)
    assert tree(dest) == []


def test_missing_checksums_are_reported_or_refused(tmp_path):
    assets = release()
    del assets["SHA256SUMS"]
    report, _ = api_fetch(tmp_path / "open", assets)
    assert report["checksums"] is None
    assert any("not verified" in warning for warning in report["warnings"])

    with pytest.raises(FetchError, match="No SHA256SUMS"):
        api_fetch(tmp_path / "strict", assets, require_checksums=True)
    assert tree(tmp_path / "strict") == []


def test_incomplete_download_leaves_no_partial_file(tmp_path):
    assets = release()
    opener = FakeOpener(assets, sizes={"best.pt": len(WEIGHTS) + 5})
    with pytest.raises(FetchError, match="Incomplete download of best.pt"):
        api_fetch(tmp_path / "dest", assets, opener=opener)
    assert tree(tmp_path / "dest") == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"urls": {"best.pt": "https://evil.example/best.pt"}}, "Unexpected download URL"),
        ({"urls": {"best.pt": f"{API}/releases/assets/1/../2"}}, "Unexpected download URL"),
        ({"sizes": {"best.pt": -1}}, "Missing size"),
    ],
)
def test_untrusted_release_metadata_is_refused_before_any_download(tmp_path, change, message):
    opener = FakeOpener(release(), **change)
    with pytest.raises(FetchError, match=message):
        api_fetch(tmp_path / "dest", {}, opener=opener, token=SENTINEL)
    assert [request.full_url for request in opener.requests] == [RELEASE_URL]


def test_unsafe_asset_name_is_refused(tmp_path):
    opener = FakeOpener({"../escape.zip": b"x"})
    with pytest.raises(FetchError, match="Unsafe asset name"):
        api_fetch(tmp_path / "dest", {}, opener=opener)
    assert not (tmp_path / "escape.zip").exists()


@pytest.mark.parametrize("command", ["github", "local"])
def test_non_empty_or_file_destination_is_refused(tmp_path, command, capsys):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("user data")
    archive = tmp_path / "export.zip"
    archive.write_bytes(zip_bytes(export_files()))
    opener = FakeOpener(release())
    for dest, message in ((occupied, "not empty"), (occupied / "keep.txt", "not a directory")):
        argv = (
            ["github", "--repo", REPO, "--tag", TAG, "--method", "api"]
            if command == "github" else ["local", "--archive", str(archive)]
        )
        with pytest.raises(SystemExit) as exit_info:
            fetch.main([*argv, "--dest", str(dest)], opener=opener)
        assert exit_info.value.code == 2
        assert message in capsys.readouterr().err
    assert opener.requests == []
    assert tree(occupied) == ["keep.txt"]
    assert (occupied / "keep.txt").read_text() == "user data"


# ── The token ──────────────────────────────────────────────────────────────────


def _all_bytes(root: Path) -> bytes:
    return b"".join(path.read_bytes() for path in root.rglob("*") if path.is_file())


def test_token_goes_only_in_an_unredirected_authorization_header(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", SENTINEL)
    opener = FakeOpener(release())
    dest = tmp_path / "dest"
    assert fetch.main(
        ["github", "--repo", REPO, "--tag", TAG, "--dest", str(dest), "--method", "api"],
        opener=opener,
    ) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["source"]["authenticated"] is True
    assert report["source"]["token_env"] == "GITHUB_TOKEN"
    assert SENTINEL not in captured.out + captured.err
    assert SENTINEL.encode() not in _all_bytes(dest)
    assert len(opener.requests) == 4
    for request in opener.requests:
        assert request.unredirected_hdrs == {"Authorization": f"Bearer {SENTINEL}"}
        assert all(SENTINEL not in value for value in request.headers.values())
        assert SENTINEL not in request.full_url


def test_redirects_drop_the_token_and_must_stay_on_https():
    request = fetch.api_request(f"{API}/releases/assets/7", SENTINEL, "application/octet-stream")
    handler = fetch.HttpsOnlyRedirect()
    followed = handler.redirect_request(
        request, io.BytesIO(), 302, "Found", {}, "https://objects.example.net/signed?sig=1"
    )
    assert followed.full_url == "https://objects.example.net/signed?sig=1"
    assert followed.get_header("Accept") == "application/octet-stream"
    assert all(SENTINEL not in value for _, value in followed.header_items())
    with pytest.raises(FetchError, match="leaves HTTPS"):
        handler.redirect_request(request, io.BytesIO(), 302, "Found", {}, "http://plain.example/")


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    # A hostile or echoing server: the token is in the reason, headers and body.
    return urllib.error.HTTPError(
        url, code, f"Bad credentials {SENTINEL}", {"X-Echo": SENTINEL},
        io.BytesIO(f'{{"token": "{SENTINEL}"}}'.encode()),
    )


@pytest.mark.parametrize("failing", ["release", "asset"])
def test_token_never_appears_in_errors(tmp_path, monkeypatch, capsys, failing):
    monkeypatch.setenv("BV_RELEASE_TOKEN", SENTINEL)
    url = RELEASE_URL if failing == "release" else f"{API}/releases/assets/1"
    opener = FakeOpener(release(), fail={url: _http_error(url, 401)})
    with pytest.raises(SystemExit) as exit_info:
        fetch.main(
            ["github", "--repo", REPO, "--tag", TAG, "--dest", str(tmp_path / "cli"),
             "--method", "api", "--token-env", "BV_RELEASE_TOKEN"],
            opener=opener,
        )
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "HTTP 401" in captured.err
    assert SENTINEL not in captured.out + captured.err

    with pytest.raises(FetchError) as error:
        api_fetch(tmp_path / "direct", {}, opener=opener, token=SENTINEL)
    text = "".join(traceback.format_exception(error.value))
    assert "HTTP 401" in text and "token can read" in text
    assert SENTINEL not in text and SENTINEL not in repr(error.value)
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert tree(tmp_path / "direct") == []


def test_token_never_appears_in_network_errors(tmp_path):
    error = urllib.error.URLError(f"proxy refused Authorization: Bearer {SENTINEL}")
    opener = FakeOpener(release(), fail={RELEASE_URL: error})
    with pytest.raises(FetchError, match="Cannot reach GitHub") as raised:
        api_fetch(tmp_path / "dest", {}, opener=opener, token=SENTINEL)
    assert SENTINEL not in "".join(traceback.format_exception(raised.value))


# ── gh CLI path ────────────────────────────────────────────────────────────────


class FakeGh:
    def __init__(self, assets: dict[str, bytes], returncode: int = 0, stderr: str = ""):
        self.assets, self.returncode, self.stderr = assets, returncode, stderr
        self.calls = []

    def __call__(self, command: list[str], env: dict[str, str]):
        self.calls.append((command, env))
        if self.returncode == 0:
            [directory] = [arg.split("=", 1)[1] for arg in command if arg.startswith("--dir=")]
            for name, data in self.assets.items():
                (Path(directory) / name).write_bytes(data)
        return subprocess.CompletedProcess(command, self.returncode, "", self.stderr)


def test_gh_cli_is_preferred_and_gets_the_token_only_in_its_environment(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("BV_RELEASE_TOKEN", SENTINEL)
    runner = FakeGh(release())
    dest = tmp_path / "dest"
    assert fetch.main(
        ["github", "--repo", REPO, "--tag", TAG, "--dest", str(dest), "--asset", "*.zip",
         "--asset", "*.pt", "--token-env", "BV_RELEASE_TOKEN"],
        runner=runner, which=lambda name: "/usr/bin/gh" if name == "gh" else None,
    ) == 0
    [(command, env)] = runner.calls
    assert command[:4] == ["/usr/bin/gh", "release", "download", TAG]
    assert f"--repo={REPO}" in command and f"--dir={dest.absolute()}" in command
    assert {"--pattern=*.zip", "--pattern=*.pt"} <= set(command)
    assert {f"--pattern={glob}" for glob in fetch.CHECKSUM_GLOBS} <= set(command)
    assert all(SENTINEL not in arg for arg in command)
    assert env["GH_TOKEN"] == SENTINEL and env["GH_PROMPT_DISABLED"] == "1"
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["source"]["method"] == "gh"
    assert report["checksums"]["verified"] == ["best.pt", "export.zip"]
    assert report["layout"]["yolo_exports"][0]["kind"] == "yolo_export"
    assert SENTINEL not in captured.out + captured.err


def test_gh_failure_output_is_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", SENTINEL)
    runner = FakeGh({}, returncode=1, stderr=f"HTTP 401: Bad credentials ({SENTINEL})\n")
    with pytest.raises(SystemExit):
        fetch.main(
            ["github", "--repo", REPO, "--tag", TAG, "--dest", str(tmp_path / "dest"),
             "--method", "gh"],
            runner=runner, which=lambda name: "/usr/bin/gh",
        )
    err = capsys.readouterr().err
    assert "exit code 1" in err and "HTTP 401" in err
    assert SENTINEL not in err


def test_gh_method_without_gh_and_bad_arguments_are_refused(tmp_path):
    with pytest.raises(FetchError, match="not installed"):
        fetch.fetch_github(REPO, TAG, tmp_path / "a", method="gh", which=lambda name: None)
    for repo, tag, patterns, message in (
        ("acme", TAG, (), "OWNER/NAME"),
        ("acme/../x", TAG, (), "OWNER/NAME"),
        (REPO, "--help", (), "valid release tag"),
        (REPO, TAG, ("dir/*.zip",), "Invalid --asset"),
    ):
        with pytest.raises(FetchError, match=message):
            fetch.fetch_github(repo, tag, tmp_path / "b", patterns=patterns, method="api",
                               opener=FakeOpener({}))
    assert not (tmp_path / "b").exists()


# ── Safe extraction ────────────────────────────────────────────────────────────


def _zip_link(path: Path) -> Path:
    info = zipfile.ZipInfo("data/link", (2026, 11, 13, 9, 0, 0))
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return write_zip(path.with_suffix(".zip"), [(info, b"/etc/passwd")])


def _zip_fifo(path: Path) -> Path:
    info = zipfile.ZipInfo("data/pipe", (2026, 11, 13, 9, 0, 0))
    info.external_attr = (stat.S_IFIFO | 0o644) << 16
    return write_zip(path.with_suffix(".zip"), [(info, b"")])


def _zip_duplicate(path: Path) -> Path:
    with pytest.warns(UserWarning, match="Duplicate name"):
        return write_zip(path.with_suffix(".zip"), [("a.txt", b"1"), ("a.txt", b"2")])


UNSAFE = {
    "zip-slip": (lambda p: write_zip(p.with_suffix(".zip"), [("../evil.txt", b"x")]),
                 "Parent-directory"),
    "zip-nested-slip": (lambda p: write_zip(p.with_suffix(".zip"), [("ok/../../evil.txt", b"x")]),
                        "Parent-directory"),
    "zip-absolute": (lambda p: write_zip(p.with_suffix(".zip"), [("/tmp/evil.txt", b"x")]),
                     "Absolute path"),
    "zip-drive": (lambda p: write_zip(p.with_suffix(".zip"), [("C:/evil.txt", b"x")]),
                  "Absolute path"),
    "zip-backslash": (lambda p: write_zip(p.with_suffix(".zip"), [("..\\evil.txt", b"x")]),
                      "Unsafe archive member name"),
    "zip-symlink": (_zip_link, "Symbolic link"),
    "zip-special": (_zip_fifo, "Special file"),
    "zip-duplicate": (_zip_duplicate, "Duplicate archive member"),
    "tar-slip": (lambda p: write_tar(p.with_suffix(".tar.gz"), [(tar_info("../evil"), b"x")]),
                 "Parent-directory"),
    "tar-absolute": (lambda p: write_tar(p.with_suffix(".tar.gz"),
                                         [(tar_info("/tmp/evil"), b"x")]), "Absolute path"),
    "tar-symlink": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("data/link", tarfile.SYMTYPE, linkname="/etc/passwd"), None)
    ]), "Symbolic link"),
    "tar-symlink-then-write": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("data", tarfile.SYMTYPE, linkname="/tmp"), None),
        (tar_info("data/evil"), b"x"),
    ]), "Symbolic link"),
    "tar-hardlink": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("data/hard", tarfile.LNKTYPE, linkname="/etc/passwd"), None)
    ]), "Hard link"),
    "tar-fifo": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("data/pipe", tarfile.FIFOTYPE), None)
    ]), "Device or special file"),
    "tar-char-device": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("data/null", tarfile.CHRTYPE, devmajor=1, devminor=3), None)
    ]), "Device or special file"),
    "tar-block-device": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("data/sda", tarfile.BLKTYPE, devmajor=8, devminor=0), None)
    ]), "Device or special file"),
    "tar-file-under-file": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("data"), b"x"), (tar_info("data/evil"), b"y"),
    ]), "below a file"),
    "zip-bomb-member": (lambda p: write_zip(p.with_suffix(".zip"), [
        ("zeros.bin", bytes(8 << 20))
    ]), "Compression ratio"),
    "tar-gz-bomb": (lambda p: write_tar(p.with_suffix(".tar.gz"), [
        (tar_info("zeros.bin"), bytes(8 << 20))
    ]), "expands over"),
    "not-an-archive": (lambda p: (p.with_suffix(".zip")).write_bytes(b"plain") and
                       p.with_suffix(".zip"), "Cannot read archive"),
}


@pytest.mark.parametrize("case", list(UNSAFE), ids=list(UNSAFE))
def test_unsafe_archives_are_refused_before_anything_is_written(tmp_path, case):
    build, message = UNSAFE[case]
    source = tmp_path / "source"
    source.mkdir()
    archive = build(source / "bad")
    dest = tmp_path / "dest"
    dest.mkdir()
    before = tree(tmp_path)
    with pytest.raises(FetchError, match=message):
        fetch.extract_archive(archive, dest / "bad")
    assert tree(tmp_path) == before
    assert not (dest / "bad").exists()


def test_total_size_limit_is_enforced(tmp_path):
    archive = write_zip(tmp_path / "big.zip", [("a.bin", b"12345678"), ("b.bin", b"12345678")])
    with pytest.raises(FetchError, match="over the 10-byte limit"):
        fetch.extract_archive(archive, tmp_path / "big", Limits(max_total_bytes=10))
    with pytest.raises(FetchError, match="more than 1 members"):
        fetch.extract_archive(archive, tmp_path / "big", Limits(max_members=1))
    assert not (tmp_path / "big").exists()


def test_member_larger_than_declared_is_refused_and_cleaned_up(tmp_path, monkeypatch):
    archive = write_zip(tmp_path / "lie.zip", [("a.txt", b"0123456789")])
    real = fetch._zip_members

    def understated(handle, limits):
        members = real(handle, limits)
        for member in members:
            member.size = 4
        return members

    monkeypatch.setattr(fetch, "_zip_members", understated)
    with pytest.raises(FetchError, match="larger than declared"):
        fetch.extract_archive(archive, tmp_path / "lie")
    assert not (tmp_path / "lie").exists()


def test_tar_extraction_ignores_archive_modes_and_owners(tmp_path):
    entries = [(tar_info(f"export/{name}", mode=0o6777, uid=0, gid=0), data)
               for name, data in export_files().items()]
    entries.insert(0, (tar_info("./", tarfile.DIRTYPE, mode=0o777), None))
    archive = write_tar(tmp_path / "export.tar.gz", entries)
    result = fetch.extract_archive(archive, tmp_path / "out")
    assert result["format"] == "tar" and result["files"] == len(export_files())
    written = tmp_path / "out" / "export" / "data.yaml"
    assert written.read_bytes() == export_files()["data.yaml"]
    assert not written.stat().st_mode & (stat.S_ISUID | stat.S_ISGID)


def test_macos_resource_forks_are_skipped(tmp_path):
    archive = write_zip(tmp_path / "mac.zip", [
        ("export/data.yaml", b"nc: 12\n"), ("__MACOSX/export/._data.yaml", b"fork"),
    ])
    result = fetch.extract_archive(archive, tmp_path / "mac")
    assert result["skipped_members"] == 1
    assert tree(tmp_path / "mac") == ["export", "export/data.yaml"]


# ── Local files ────────────────────────────────────────────────────────────────


def test_local_archive_is_verified_extracted_and_reported(tmp_path, capsys):
    archive = tmp_path / "attachments" / "BananaVision export (1).zip"
    archive.parent.mkdir()
    archive.write_bytes(zip_bytes(export_files("BananaVision.v3/")))
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(f"{sha(archive.read_bytes())}  {archive.name}\n")
    dest = tmp_path / "dest"
    assert fetch.main([
        "local", "--archive", str(archive), "--dest", str(dest),
        "--sha256", sha(archive.read_bytes()).upper(), "--checksums", str(sums),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    target = dest / "BananaVision_export_1_" / "BananaVision.v3"
    assert report["mode"] == "local" and report["fetched_at"].endswith("+08:00")
    assert report["checksums"] == {"verified_by": ["--sha256", "SHA256SUMS"]}
    assert report["files"][0]["name"] == archive.name
    [export] = report["layout"]["yolo_exports"]
    assert export["path"] == str(target) and export["kind"] == "yolo_export"
    assert report["layout"]["weights"] == []
    assert report["next_commands"][0] == (
        f"python scripts/prepare_yolo_dataset.py --source {target} --output {dest / 'prepared'}"
    )
    assert f"--weights {fetch.WEIGHTS_PLACEHOLDER}" in report["next_commands"][1]
    assert archive.read_bytes() == zip_bytes(export_files("BananaVision.v3/"))


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (lambda a, s: ["--sha256", "0" * 64], "SHA-256 mismatch"),
        (lambda a, s: ["--sha256", "abc"], "64 hexadecimal"),
        (lambda a, s: ["--checksums", str(s)], "No SHA256SUMS entry"),
    ],
)
def test_local_verification_failure_creates_nothing(tmp_path, capsys, options, message):
    archive = tmp_path / "export.zip"
    archive.write_bytes(zip_bytes(export_files()))
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(f"{sha(b'other')}  other.zip\n")
    dest = tmp_path / "dest"
    with pytest.raises(SystemExit):
        fetch.main(["local", "--archive", str(archive), "--dest", str(dest),
                    *options(archive, sums)])
    assert message in capsys.readouterr().err
    assert not dest.exists()


def test_local_weights_are_copied_and_hashed(tmp_path):
    weights = tmp_path / "best.pt"
    weights.write_bytes(WEIGHTS)
    report = fetch.fetch_local(weights, tmp_path / "dest", sha256=sha(WEIGHTS))
    assert report["layout"]["weights"] == [
        {"path": str(tmp_path / "dest" / "best.pt"), "bytes": len(WEIGHTS),
         "sha256": sha(WEIGHTS)}
    ]
    assert any("pickles" in warning for warning in report["warnings"])
    with pytest.raises(FetchError, match="must be a .zip"):
        other = tmp_path / "notes.txt"
        other.write_text("x")
        fetch.fetch_local(other, tmp_path / "dest2")


# ── Layout detection ───────────────────────────────────────────────────────────


def test_prepared_dataset_needs_no_prepare_step(tmp_path):
    root = tmp_path / "dest" / "prepared-v1"
    for name, data in export_files().items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    (root / "manifest.json").write_text("{}")
    (root / "train" / "images" / "unlabeled.jpg").write_bytes(b"x")
    layout = fetch.detect_layout(tmp_path / "dest")
    [export] = layout["yolo_exports"]
    assert export["kind"] == "prepared" and export["roboflow"] is True
    assert export["splits"]["train"]["images_without_labels"] == 1
    commands = fetch.next_commands(tmp_path / "dest", layout)
    assert [command.split()[1] for command in commands] == [
        "scripts/evaluate_finger_count.py", "scripts/train_finger_model.py",
    ]
    assert f"--data {root} " in commands[1]


def test_layout_flags_wrong_classes_and_incomplete_exports(tmp_path):
    good = tmp_path / "a"
    for name, data in export_files().items():
        (good / name).parent.mkdir(parents=True, exist_ok=True)
        (good / name).write_bytes(data)
    names = list(reversed(EXPECTED_NAMES))
    (good / "data.yaml").write_text(f"nc: 12\nnames: {json.dumps(names)}\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "data.yaml").write_text("names: {0: banana}\n")
    layout = fetch.detect_layout(tmp_path)
    by_path = {Path(item["path"]).name: item for item in layout["yolo_exports"]}
    assert by_path["a"]["matches_expected_classes"] is True
    assert by_path["a"]["expected_class_order"] is False
    assert by_path["b"]["kind"] == "incomplete"
    assert by_path["b"]["class_names"] == ["banana"]
    assert by_path["b"]["matches_expected_classes"] is False
    commands = fetch.next_commands(tmp_path, layout)
    assert sum("prepare_yolo_dataset.py" in command for command in commands) == 1
    # prepare_yolo_dataset.py keeps the source order; train_finger_model.py refuses it.
    assert fetch.layout_warnings(layout) == [
        f"{good} lists the 12 classes in another order: prepare_yolo_dataset.py keeps it, "
        "and train_finger_model.py refuses any order but prepare_yolo_dataset.EXPECTED_NAMES."
    ]
    with pytest.raises(TrainingError, match="EXPECTED_NAMES"):
        check_names({"names": names, "nc": 12})

    shutil.rmtree(good / "test")
    (good / "data.yaml").write_text("nc: 1\nnames: [banana]\n")
    warnings = fetch.layout_warnings(fetch.detect_layout(good))
    assert warnings == [
        f"{good} lacks test: prepare_yolo_dataset.py needs train, valid and test.",
        f"{good} does not have the 12 cultivar/ripeness classes that "
        "prepare_yolo_dataset.py expects.",
    ]


def test_two_downloads_extracting_into_one_directory_are_refused(tmp_path):
    archive = zip_bytes({"a.txt": b"a"})
    with pytest.raises(FetchError, match="extract into export/"):
        api_fetch(tmp_path / "dest", {"export.zip": archive, "export.tar.gz": b"x"})


# ── Review regressions ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [
    "ghp_FIRSTHALFsecret\nSECONDHALFsecret", "ghp_FIRSTHALFsecret\r\nSECONDHALFsecret",
    "ghp_FIRSTHALFsecret SECONDHALFsecret", "ghp_FIRSTHALFsecret\u00e9SECONDHALFsecret",
])
def test_a_token_that_is_not_one_ascii_word_is_refused_without_echo(tmp_path, monkeypatch,
                                                                     capsys, value):
    monkeypatch.setenv("BV_RELEASE_TOKEN", value)
    opener = FakeOpener(release())
    with pytest.raises(SystemExit) as exit_info:
        fetch.main(["github", "--repo", REPO, "--tag", TAG, "--dest", str(tmp_path / "d"),
                    "--method", "api", "--token-env", "BV_RELEASE_TOKEN"], opener=opener)
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "BV_RELEASE_TOKEN value is not a single token" in err
    assert "FIRSTHALF" not in err and "SECONDHALF" not in err
    assert opener.requests == [] and not (tmp_path / "d").exists()
    # Surrounding whitespace (a trailing newline from a file) is still accepted.
    monkeypatch.setenv("BV_RELEASE_TOKEN", f"  {SENTINEL}\n")
    assert fetch.read_token("BV_RELEASE_TOKEN") == SENTINEL


@pytest.mark.parametrize("error", [
    ValueError(f"Invalid header value b'Bearer {SENTINEL}\\nmore'"),
    http.client.BadStatusLine(f"Bearer {SENTINEL}"),
])
def test_any_other_request_error_is_reported_without_its_text(tmp_path, error):
    opener = FakeOpener(release(), fail={RELEASE_URL: error})
    with pytest.raises(FetchError, match=f"Cannot reach GitHub .*{type(error).__name__}") as raised:
        api_fetch(tmp_path / "dest", {}, opener=opener, token=SENTINEL)
    assert SENTINEL not in "".join(traceback.format_exception(raised.value))
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_a_dropped_connection_is_a_fetch_error_and_leaves_nothing(tmp_path, capsys):
    opener = FakeOpener(release(), cut_off=("best.pt",))
    with pytest.raises(SystemExit) as exit_info:
        fetch.main(["github", "--repo", REPO, "--tag", TAG, "--dest", str(tmp_path / "dest"),
                    "--method", "api"], opener=opener)
    assert exit_info.value.code == 2
    assert "Download of asset best.pt was cut off (IncompleteRead)" in capsys.readouterr().err
    assert tree(tmp_path / "dest") == []


def test_gh_error_is_redacted_before_it_is_shortened(tmp_path):
    for offset in (280, 285, 299, 300):
        runner = FakeGh({}, returncode=1, stderr="x" * offset + SENTINEL + " tail\n")
        with pytest.raises(FetchError) as raised:
            fetch.fetch_github(REPO, TAG, tmp_path / f"d{offset}", token=SENTINEL, method="gh",
                               runner=runner, which=lambda name: "/usr/bin/gh")
        message = str(raised.value)
        assert SENTINEL[:4] not in message, offset
        assert "--method api" in message


def test_gh_without_a_login_falls_back_to_the_api_in_auto_mode(tmp_path):
    login = "To get started with GitHub CLI, please run:  gh auth login\n"
    runner = FakeGh({"partial.zip": b"x"}, returncode=4, stderr=login)

    def writes_then_fails(command, env):
        directory = Path(next(a for a in command if a.startswith("--dir=")).split("=", 1)[1])
        (directory / "partial.zip").write_bytes(b"left behind")
        return runner(command, env)

    gh = {"which": lambda name: "/usr/bin/gh"}
    opener = FakeOpener(release())
    report = fetch.fetch_github(REPO, TAG, tmp_path / "auto", opener=opener,
                                runner=writes_then_fails, **gh)
    assert len(runner.calls) == 1 and opener.requests[0].full_url == RELEASE_URL
    assert report["source"]["method"] == "api"
    assert report["warnings"][0] == "gh is not logged in, so the GitHub REST API was used instead."
    assert report["checksums"]["verified"] == ["best.pt", "export.zip"]
    assert not (tmp_path / "auto" / "partial.zip").exists()

    with pytest.raises(FetchError, match="gh is not logged in.*--method api"):
        fetch.fetch_github(REPO, TAG, tmp_path / "strict", method="gh",
                           runner=writes_then_fails, **gh)
    assert tree(tmp_path / "strict") == []


def test_gh_failure_removes_what_gh_wrote(tmp_path):
    def fails_midway(command, env):
        directory = Path(next(a for a in command if a.startswith("--dir=")).split("=", 1)[1])
        (directory / "export.zip").write_bytes(b"half")
        (directory / "tmpdir").mkdir()
        return subprocess.CompletedProcess(command, 1, "", "connection reset\n")

    with pytest.raises(FetchError, match="exit code 1: connection reset"):
        fetch.fetch_github(REPO, TAG, tmp_path / "dest", method="auto", runner=fails_midway,
                           which=lambda name: "/usr/bin/gh")
    assert tree(tmp_path / "dest") == []


def test_gh_checksum_patterns_match_every_checksum_name_in_any_case():
    names = ["SHA256SUMS", "sha256sums", "Sha256Sums", "SHA256SUMS.txt", "SHA256SUMS.TXT",
             "sha256sums.txt"]
    for name in names:
        assert fetch.is_checksum_name(name)
        assert any(fnmatch.fnmatchcase(name, glob) for glob in fetch.CHECKSUM_GLOBS), name
    for name in ("SHA256SUMS.asc", "xSHA256SUMS", "SHA256SUMSxtxt", "export.zip"):
        assert not any(fnmatch.fnmatchcase(name, glob) for glob in fetch.CHECKSUM_GLOBS), name


def test_repository_case_and_renames_follow_githubs_answer(tmp_path):
    canonical = "https://api.github.com/repos/Acme/Bananas"
    urls = {name: f"{canonical}/releases/assets/{index}"
            for index, name in enumerate(release(), 1)}
    opener = FakeOpener(release(), urls=urls)
    report, _ = api_fetch(tmp_path / "case", {}, opener=opener)
    assert report["checksums"]["verified"] == ["best.pt", "export.zip"]

    renamed = "https://api.github.com/repos/acme-labs/plantains"
    urls = {name: f"{renamed}/releases/assets/{index}"
            for index, name in enumerate(release(), 1)}
    opener = FakeOpener(release(), urls=urls, own_url=f"{renamed}/releases/77")
    report, _ = api_fetch(tmp_path / "renamed", {}, opener=opener)
    assert report["checksums"]["verified"] == ["best.pt", "export.zip"]

    # Neither the requested repository nor the release's own: refused before any download.
    for number, own in enumerate((None, "https://evil.example/repos/other/x/releases/1",
                                  f"{renamed}/releases/77/../../../other/x/releases/1")):
        opener = FakeOpener(release(), urls=urls, own_url=own)
        with pytest.raises(FetchError, match="Unexpected download URL"):
            api_fetch(tmp_path / f"refused{number}", {}, opener=opener, token=SENTINEL)
        assert [request.full_url for request in opener.requests] == [RELEASE_URL]


def _corrupt_deflate(path: Path) -> Path:
    """Valid zip headers around a damaged deflate stream (zlib.error, not BadZipFile)."""
    data = b"".join(f"{i % 12} 0.{i:04d} 0.5 0.2 0.3\n".encode() for i in range(5000))
    raw = bytearray(write_zip(path, [("export/labels.txt", data)]).read_bytes())
    info = zipfile.ZipFile(io.BytesIO(bytes(raw))).infolist()[0]
    assert info.compress_type == zipfile.ZIP_DEFLATED
    offset = info.header_offset
    name_length, extra_length = struct.unpack("<HH", raw[offset + 26:offset + 30])
    start = offset + 30 + name_length + extra_length
    raw[start + 3:start + 40] = b"\xff" * 37
    path.write_bytes(bytes(raw))
    return path


def _corrupt_xz(path: Path) -> Path:
    """An xz stream that opens, then fails part-way (lzma.LZMAError while listing)."""
    data = random.Random(0).randbytes(400_000)  # incompressible: the stream stays long
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:xz") as archive:
        for name in ("export/a.bin", "export/b.bin"):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    raw = bytearray(stream.getvalue())
    at = len(raw) * 3 // 4
    raw[at:at + 64] = bytes(byte ^ 0xFF for byte in raw[at:at + 64])
    path.write_bytes(bytes(raw))
    return path


@pytest.mark.parametrize(("build", "cause"), [
    (lambda d: _corrupt_deflate(d / "export.zip"), zlib.error),
    (lambda d: _corrupt_xz(d / "export.tar.xz"), lzma.LZMAError),
], ids=["zip-deflate", "tar-xz"])
def test_corrupt_compressed_data_is_a_clean_failure(tmp_path, capsys, build, cause):
    source = tmp_path / "source"
    source.mkdir()
    archive = build(source)
    with pytest.raises(FetchError, match="archive export") as raised:
        fetch.extract_archive(archive, tmp_path / "direct")
    assert isinstance(raised.value.__cause__, cause)
    assert not (tmp_path / "direct").exists()
    with pytest.raises(SystemExit) as exit_info:
        fetch.main(["local", "--archive", str(archive), "--dest", str(tmp_path / "dest")])
    assert exit_info.value.code == 2
    assert "Fetch failed:" in capsys.readouterr().err
    assert tree(tmp_path / "dest") == []


def _prepared(root: Path, base: str | None) -> Path:
    files = export_files()
    yaml = ("train: train/images\nval: valid/images\ntest: test/images\n"
            f"nc: 12\nnames: {json.dumps(EXPECTED_NAMES)}\n")
    if base is not None:
        yaml = f"path: {json.dumps(base)}\n{yaml}"
    files["data.yaml"] = yaml.encode()
    write_tree(root, files)
    (root / "manifest.json").write_text("{}")
    return root


@pytest.mark.parametrize(("base", "relocate"), [
    ("/home/laptop/BananaVision/prepared", True), ("prepared", True),
    ("C:/Users/laptop/prepared", True), (None, False), ("<root>", False),
], ids=["foreign", "relative", "windows", "absent", "this-folder"])
def test_prepared_copy_from_another_machine_needs_relocation(tmp_path, base, relocate):
    # A long folder name: the comparison must use the whole path: value, not a shortened one.
    root = tmp_path / "dest" / ("prepared-v1-" + "x" * 220)
    _prepared(root, str(root) if base == "<root>" else base)
    layout = fetch.detect_layout(tmp_path / "dest")
    [export] = layout["yolo_exports"]
    assert export["kind"] == "prepared"
    assert export["needs_relocation"] is relocate
    path_warnings = [w for w in fetch.layout_warnings(layout) if "data.yaml path:" in w]
    if relocate:
        assert path_warnings == [
            f"{root}/data.yaml path: names {export['data_yaml_path']!r}, not this folder "
            f"(a copy moved from another machine): set path: to {root} or remove the line "
            "before running train_finger_model.py (prepare_ood_dataset.py merge-negatives "
            "also writes a relocated copy)."
        ]
    else:
        assert path_warnings == []
    # The same verdict as the script that would refuse it.
    import yaml

    data = yaml.safe_load((root / "data.yaml").read_text())
    try:
        check_split_paths(root, data)
        refused = False
    except TrainingError as exc:
        refused = "path:" in str(exc)
    assert refused is relocate


@pytest.mark.parametrize(("text", "reason"), [
    ("nc: 12\nnames:\n" + "".join(f"- {name}\n" for name in EXPECTED_NAMES),
     "Expected the 12 cultivar/ripeness names in data.yaml"),
    (f"names: {json.dumps(EXPECTED_NAMES)}\n", "Expected nc: 12 in data.yaml"),
    ("nc: 12\nnames: {" + ", ".join(f"{i}: {n}" for i, n in enumerate(EXPECTED_NAMES)) + "}\n",
     "Expected the 12 cultivar/ripeness names in data.yaml"),
], ids=["block-list", "no-nc", "index-mapping"])
def test_data_yaml_that_prepare_cannot_read_is_flagged(tmp_path, text, reason):
    root = write_tree(tmp_path / "export", export_files())
    (root / "data.yaml").write_text(text)
    [export] = fetch.detect_layout(root)["yolo_exports"]
    assert export["matches_expected_classes"] and export["expected_class_order"]
    assert export["prepare_compatible"] is False and export["prepare_error"] == reason
    assert fetch.layout_warnings({"weights": [], "yolo_exports": [export]}) == [
        f"{root}/data.yaml is not in the form prepare_yolo_dataset.py reads ({reason}): "
        "it needs an inline names: [...] line and nc: 12."
    ]
    [export] = fetch.detect_layout(write_tree(tmp_path / "ok", export_files()))["yolo_exports"]
    assert export["prepare_compatible"] is True and export["prepare_error"] is None


@pytest.mark.parametrize("names", [
    "{0: a, b: c}", "{1: a, 2: b}", "{0: a, 0.5: b}", "[1, 2]", "banana", "{0: [a]}",
])
def test_odd_names_in_data_yaml_are_reported_not_fatal(tmp_path, capsys, names):
    files = export_files("export/")
    files["export/data.yaml"] = f"nc: 2\nnames: {names}\n".encode()
    archive = tmp_path / "export.zip"
    archive.write_bytes(zip_bytes(files))
    assert fetch.main(["local", "--archive", str(archive), "--dest", str(tmp_path / "d")]) == 0
    [export] = json.loads(capsys.readouterr().out)["layout"]["yolo_exports"]
    assert export["class_names"] is None and export["matches_expected_classes"] is False


def test_several_weights_prefer_best_pt_and_say_so(tmp_path):
    dest = tmp_path / "dest"
    write_tree(dest, {"yolo26n.pt": b"coco", "model/weights/best.pt": WEIGHTS,
                      "model/weights/last.pt": b"last"})
    write_tree(dest / "a", export_files())
    write_tree(dest / "b", export_files())
    layout = fetch.detect_layout(dest)
    best = dest / "model" / "weights" / "best.pt"
    commands = fetch.next_commands(dest, layout)
    assert fetch.pick_weights(layout) == str(best)
    evaluate = [c for c in commands if "evaluate_finger_count.py" in c]
    assert all(f"--weights {best} " in c for c in commands if "--weights" in c)
    # One report per dataset: evaluate_finger_count.py never overwrites an existing file.
    assert [c.rsplit("--output ", 1)[1] for c in evaluate] == [
        "finger-count-prepared-valid.json", "finger-count-prepared-2-valid.json",
    ]
    warnings = fetch.layout_warnings(layout)
    assert (
        f"Found 3 .pt files ({dest / 'yolo26n.pt'}, {best}, {dest / 'model/weights/last.pt'}); "
        f"the commands use {best}; check that it is the finger model."
    ) in warnings

    (best).unlink()
    layout = fetch.detect_layout(dest)
    assert fetch.pick_weights(layout) is None
    assert all(f"--weights {fetch.WEIGHTS_PLACEHOLDER} " in c
               for c in fetch.next_commands(dest, layout) if "--weights" in c)
    assert any(w.startswith("Found 2 .pt files") and fetch.WEIGHTS_PLACEHOLDER in w
               for w in fetch.layout_warnings(layout))


def test_report_names_stay_unique_for_prepared_exports_with_one_name(tmp_path):
    dest = tmp_path / "dest"
    for parent in ("x", "y"):
        _prepared(dest / parent / "prepared v1", None)
    layout = fetch.detect_layout(dest)
    outputs = [c.rsplit("--output ", 1)[1] for c in fetch.next_commands(dest, layout)
               if "evaluate_finger_count.py" in c]
    assert outputs == ["finger-count-prepared_v1-valid.json",
                       "finger-count-prepared_v1-2-valid.json"]
