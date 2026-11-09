"""The documentation pages hang together: tutorials are linked and their pictures exist."""
import re
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / 'demos'))
from tutorial_screenshots import SHOTS  # noqa: E402

TUTORIAL = ROOT / 'mindmap-editor' / 'tutorials' / 'first-mind-map.md'


def pictures(page):
    return re.findall(r'!\[[^\]]*\]\(([^)]+)\)', page.read_text())


def test_the_landing_page_links_to_the_tutorial():
    assert '(tutorials/first-mind-map.md)' in (ROOT / 'mindmap-editor' / 'index.md').read_text()


def test_every_picture_in_the_tutorial_exists():
    missing = [p for p in pictures(TUTORIAL) if not (TUTORIAL.parent / p).exists()]
    assert missing == []


def test_the_tutorial_uses_every_screenshot_the_script_makes():
    assert sorted(f'images/{name}.png' for name in SHOTS) == sorted(pictures(TUTORIAL))


def test_the_tutorials_links_to_other_pages_exist():
    links = re.findall(r'(?<!!)\[[^\]]*\]\(([^)#]+)\)', TUTORIAL.read_text())
    missing = [l for l in links if not l.startswith('http') and not (TUTORIAL.parent / l).exists()]
    assert missing == []
