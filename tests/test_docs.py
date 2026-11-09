"""The documentation pages hang together: the tutorial's pages are linked in order and their pictures exist."""
import re
import sys

import yaml

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


def front_matter(page):
    """The page's front matter, as a dict."""
    return yaml.safe_load(page.read_text().split('---\n')[1])


def nav(page):
    """The step a page says it is, and the pages it says come before and after it."""
    fm = front_matter(page)
    return fm.get('step'), fm.get('previous'), fm.get('next')


def test_the_landing_page_links_to_the_tutorial():
    assert '(tutorials/first-mind-map/index.md)' in (ROOT / 'mindmap-editor' / 'index.md').read_text()


def test_the_contents_page_lists_every_step_page():
    on_disk = sorted(p.name for p in TUTORIAL.glob('*.md') if p.name != 'index.md')
    assert len(steps()) == 11
    assert sorted(p.name for p in steps()) == on_disk


def test_every_tutorial_page_uses_the_tutorial_layout():
    for page in [CONTENTS, *steps()]:
        assert front_matter(page)['layout'] == 'tutorial', page.name
    assert (ROOT / '_layouts' / 'tutorial.html').exists()


def test_each_step_knows_its_number_and_its_neighbours():
    pages = steps()
    for i, page in enumerate(pages):
        previous = pages[i - 1].name if i else 'index.md'
        following = pages[i + 1].name if i + 1 < len(pages) else None
        assert nav(page) == (i + 1, previous, following), page.name
    assert nav(CONTENTS) == (None, None, pages[0].name)


def test_step_pages_have_no_heading_or_links_of_their_own():
    """The layout draws the title and the arrows, so the Markdown mustn't repeat them."""
    for page in steps():
        body = page.read_text().split('---\n', 2)[2]
        assert not body.lstrip().startswith('#'), page.name
        assert 'Previous' not in body and 'Next:' not in body, page.name


def test_the_layout_draws_arrows_and_the_page_title():
    layout = (ROOT / '_layouts' / 'tutorial.html').read_text()
    assert '{{ page.title }}' in layout
    assert 'aria-label="Previous step"' in layout and 'aria-label="Next step"' in layout
    assert 'site.title' not in layout


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
