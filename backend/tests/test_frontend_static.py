import re
from pathlib import Path

from app.config import settings

_BANNED_SUBSTRINGS = (
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
    "Math.random",
)
_INNERHTML_RE = re.compile(r"innerHTML\s*=")
_INLINE_SCRIPT_RE = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
_STYLE_TAG_RE = re.compile(r"<style\b", re.IGNORECASE)
_ON_ATTR_RE = re.compile(r"\son\w+\s*=", re.IGNORECASE)
_STYLE_ATTR_RE = re.compile(r"\sstyle\s*=", re.IGNORECASE)
_EXTERNAL_REF_RE = re.compile(r"""(src|href)\s*=\s*["']https?://""", re.IGNORECASE)


def test_frontend_static_rules() -> None:
    root = Path(settings.frontend_dir)
    problems: list[str] = []
    scanned: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in (".js", ".html"):
            continue
        scanned.append(path)
        rel = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        for banned in _BANNED_SUBSTRINGS:
            if banned in source:
                problems.append(f"{rel}: запрещённый вызов {banned}")
        if _INNERHTML_RE.search(source):
            problems.append(f"{rel}: innerHTML=")
        if path.suffix == ".html":
            if _INLINE_SCRIPT_RE.search(source):
                problems.append(f"{rel}: инлайн <script>")
            if _STYLE_TAG_RE.search(source):
                problems.append(f"{rel}: тег <style>")
            if _ON_ATTR_RE.search(source):
                problems.append(f"{rel}: on*-атрибут")
            if _STYLE_ATTR_RE.search(source):
                problems.append(f"{rel}: атрибут style=")
            if _EXTERNAL_REF_RE.search(source):
                problems.append(f"{rel}: внешний src=/href=")
    assert any(p.as_posix().endswith("js/api.js") for p in scanned), (
        "тест не проверил js/api.js (пустой набор файлов?)"
    )
    assert not problems, "\n".join(problems)
