"""The documentation pages hang together: the tutorial's pages are linked in order and their pictures exist."""
import re
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / 'demos'))
from tutorial_screenshots import SHOTS  # noqa: E402

TUTORIAL = ROOT / 'mindmap-editor' / 'tutorials' / 'first-mind-map'
CONTENTS = TUTORIAL / 'index.md'
MAX_PICTURE_BYTES = 120_000


def steps():
    """The step pages, in the order the contents page lists them."""
    return [TUTORIAL / name for name in re.findall(r'^\d+\. \[[^\]]+\]\(([^)]+)\)', CONTENTS.read_text(), re.M)]


def pictures(page):
    return re.findall(r'!\[[^\]]*\]\(([^)]+)\)', page.read_text())


def links(page):
    return re.findall(r'(?<!!)\[[^\]]*\]\(([^)#]+)\)', page.read_text())


def nav(page):
    """The page's Previous, Contents and Next links (None where there isn't one)."""
    text = page.read_text()
    find = lambda word: (m.group(1) if (m := re.search(rf'\[[^\]]*{word}[^\]]*\]\(([^)]+)\)', text)) else None)
    return find('Previous'), find('Contents'), find('Next')


def test_the_landing_page_links_to_the_tutorial():
    assert '(tutorials/first-mind-map/index.md)' in (ROOT / 'mindmap-editor' / 'index.md').read_text()


def test_the_contents_page_lists_every_step_page():
    on_disk = sorted(p.name for p in TUTORIAL.glob('*.md') if p.name != 'index.md')
    assert len(steps()) == 11
    assert sorted(p.name for p in steps()) == on_disk


def test_each_step_links_to_the_previous_the_contents_and_the_next():
    pages = steps()
    for i, page in enumerate(pages):
        previous = pages[i - 1].name if i else None
        following = pages[i + 1].name if i + 1 < len(pages) else None
        assert nav(page) == (previous, 'index.md', following), page.name


def test_the_contents_page_starts_the_tutorial():
    assert f'({steps()[0].name})' in CONTENTS.read_text()


def test_every_picture_and_link_exists():
    for page in [CONTENTS, *steps()]:
        missing = [p for p in pictures(page) + links(page)
                   if not p.startswith('http') and not (page.parent / p).exists()]
        assert missing == [], page.name


def test_the_tutorial_uses_every_screenshot_the_script_makes():
    used = [p for page in [CONTENTS, *steps()] for p in pictures(page)]
    assert sorted(f'../images/{name}.png' for name in SHOTS) == sorted(used)


def test_the_screenshots_are_small():
    big = [p.name for p in (TUTORIAL.parent / 'images').glob('*.png') if p.stat().st_size > MAX_PICTURE_BYTES]
    assert big == []
