'Regression tests for write lock.'

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.kite.kite_writer import WriteLockTimeout, write_lock  # noqa: E402

WRITERS = 8
SEED = "<codebook>\n</codebook>\n"


def _append_session(path: Path, tag: str, settle: float = 0.01) -> None:

    text = path.read_text(encoding="utf-8")
    time.sleep(settle)
    text = text.replace("</codebook>", f"  <session id=\"{tag}\"/>\n</codebook>")
    path.write_text(text, encoding="utf-8")


def _run_concurrently(fn, count: int) -> None:
    threads = [threading.Thread(target=fn, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_unlocked_writes_lose_data(tmp_path):

    book = tmp_path / "codebook.xml"
    book.write_text(SEED, encoding="utf-8")

    _run_concurrently(lambda i: _append_session(book, f"s{i}"), WRITERS)

    survived = book.read_text(encoding="utf-8").count("<session ")
    assert survived < WRITERS, (
        f'\u9884\u671f\u51fa\u73b0\u4e22\u5931\u66f4\u65b0\uff0c\u4f46 {WRITERS} \u4e2a\u5199\u5165\u5168\u90e8\u5b58\u6d3b\u3002\u5e76\u53d1\u53ef\u80fd\u6ca1\u6709\u771f\u6b63\u91cd\u53e0\uff0c\u8c03\u5927 settle \u518d\u8bd5\u3002'
    )


def test_locked_writes_all_survive(tmp_path):

    book = tmp_path / "codebook.xml"
    book.write_text(SEED, encoding="utf-8")

    def writer(i: int) -> None:
        with write_lock(book, timeout=60):
            _append_session(book, f"s{i}")

    _run_concurrently(writer, WRITERS)

    text = book.read_text(encoding="utf-8")
    assert text.count("<session ") == WRITERS
    for i in range(WRITERS):
        assert f'id="s{i}"' in text, f's{i} \u4e22\u5931'


def test_lock_is_exclusive(tmp_path):

    book = tmp_path / "codebook.xml"
    book.write_text(SEED, encoding="utf-8")

    inside = 0
    overlaps = 0
    guard = threading.Lock()

    def writer(_i: int) -> None:
        nonlocal inside, overlaps
        with write_lock(book, timeout=60):
            with guard:
                inside += 1
                if inside > 1:
                    overlaps += 1
            time.sleep(0.02)
            with guard:
                inside -= 1

    _run_concurrently(writer, WRITERS)
    assert overlaps == 0


def test_different_codebooks_do_not_block(tmp_path):

    books = []
    for i in range(4):
        b = tmp_path / f"user{i}" / "codebook.xml"
        b.parent.mkdir(parents=True)
        b.write_text(SEED, encoding="utf-8")
        books.append(b)

    hold = 0.3

    def writer(i: int) -> None:
        with write_lock(books[i], timeout=30):
            time.sleep(hold)

    t0 = time.monotonic()
    _run_concurrently(writer, len(books))
    elapsed = time.monotonic() - t0

    assert elapsed < hold * len(books) * 0.6, (
        f'\u8017\u65f6 {elapsed:.2f}s\uff0c\u63a5\u8fd1\u4e32\u884c\u7684 {hold * len(books):.2f}s \u2014\u2014 \u4e0d\u540c codebook \u4e4b\u95f4\u4e0d\u8be5\u4e92\u76f8\u963b\u585e'
    )


def test_timeout_raises(tmp_path):

    book = tmp_path / "codebook.xml"
    book.write_text(SEED, encoding="utf-8")

    released = threading.Event()

    def holder() -> None:
        with write_lock(book, timeout=30):
            released.wait(2.0)

    t = threading.Thread(target=holder)
    t.start()
    time.sleep(0.2)

    try:
        with pytest.raises(WriteLockTimeout):
            with write_lock(book, timeout=0.3):
                pytest.fail('\u4e0d\u8be5\u62ff\u5230\u9501')
    finally:
        released.set()
        t.join()


CHILD = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app.database.kite.kite_writer import write_lock

book = Path(sys.argv[2])
with write_lock(book, timeout=60):
    text = book.read_text(encoding="utf-8")
    time.sleep(0.3)
    book.write_text(text.replace("</codebook>",
                    '  <session id="%s"/>\\n</codebook>' % sys.argv[3]),
                    encoding="utf-8")
"""


def test_cross_process_lock(tmp_path):

    book = tmp_path / "codebook.xml"
    book.write_text(SEED, encoding="utf-8")

    child = tmp_path / "child.py"
    child.write_text(CHILD, encoding="utf-8")
    app_root = str(Path(__file__).resolve().parent.parent)

    procs = [
        subprocess.Popen([sys.executable, str(child), app_root, str(book), f"p{i}"])
        for i in range(4)
    ]
    for p in procs:
        assert p.wait(timeout=120) == 0

    text = book.read_text(encoding="utf-8")
    assert text.count("<session ") == 4, '\u8de8\u8fdb\u7a0b\u5199\u5165\u53d1\u751f\u4e86\u4e22\u5931\u66f4\u65b0'
