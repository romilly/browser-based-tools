"""The logo in each editor's header links home: the server's /home page when the editor came from the server,
otherwise the GitHub Pages site. /home links to both tools on the server and to their documentation."""
import pytest

from conftest import LOCAL_LIBS, ROOT, _use_local_libs
from test_diagram import Diagram, dg  # noqa: F401 (dg is a fixture)
from test_diagram_server import sdg  # noqa: F401 (sdg is a fixture)
from test_mindmap import mm  # noqa: F401 (mm is a fixture)
from test_mindmap_server import call, maps, smm  # noqa: F401 (fixtures)

PAGES = 'https://romilly.github.io/browser-based-tools/'
TOOLS = [('mm', 'Mind Map Editor'), ('dg', 'Diagram Editor')]


def logo(editor):
    return editor.page.locator('header a#home')


# --- the home page on the server ---

def test_the_server_serves_the_home_page(maps):
    base, _ = maps
    status, headers, body = call(base + '/home')
    assert status == 200 and 'text/html' in headers['Content-Type']
    assert body == (ROOT / 'home.html').read_bytes()
    assert call(base + '/')[2] == (ROOT / 'mindmap-editor.html').read_bytes()     # the editor stays at the top


def test_the_home_page_links_to_both_tools_on_the_server_and_their_documentation(page, maps):
    base, _ = maps
    if LOCAL_LIBS:
        _use_local_libs(page)
    page.goto(base + '/home')
    page.get_by_role('link', name='Mind Map Editor').click()
    page.wait_for_url(base + '/')
    page.goto(base + '/home')
    page.get_by_role('link', name='Diagram Editor').click()
    page.wait_for_url(base + '/diagram-editor.html')
    page.goto(base + '/home')
    docs = [a.get_attribute('href') for a in page.get_by_role('link', name='Documentation').all()]
    assert docs == [PAGES + 'mindmap-editor/', PAGES + 'diagram-editor/']
    assert {t.inner_text() for t in page.locator('.logo').all()} == {'mm', 'dg'}


def test_the_documentation_landing_pages_exist():
    assert (ROOT / 'mindmap-editor' / 'index.md').is_file() and (ROOT / 'diagram-editor' / 'index.md').is_file()


# --- the logo in each editor ---

@pytest.mark.parametrize('tile, name', TOOLS)
def test_the_logo_shows_the_tile_and_the_tools_name(request, tile, name):
    ed = request.getfixturevalue('mm' if tile == 'mm' else 'dg')
    assert logo(ed).locator('.logo').inner_text() == tile
    assert ed.page.get_by_role('link', name=name).count() == 1


@pytest.mark.parametrize('fixture', ['mm', 'dg'])
def test_away_from_the_server_the_logo_links_to_the_github_pages_site(request, fixture):
    ed = request.getfixturevalue(fixture)
    ed.page.wait_for_timeout(200)                  # the server check has failed by now
    assert logo(ed).get_attribute('href') == PAGES


@pytest.mark.parametrize('fixture, came_from', [('smm', '/'), ('sdg', '/diagram-editor.html')])
def test_from_the_server_the_logo_goes_to_the_servers_home_page(request, fixture, came_from):
    ed = request.getfixturevalue(fixture)
    base = ed.server[0]
    assert ed.page.url == base + came_from
    logo(ed).click()
    ed.page.wait_for_url(base + '/home')
    assert ed.page.get_by_role('link', name='Diagram Editor').count() == 1


@pytest.mark.parametrize('fixture', ['mm', 'dg'])
@pytest.mark.parametrize('width, height', [(390, 844), (844, 390), (1024, 768)])
def test_on_phones_and_tablets_the_tile_shows_and_fits_the_header(request, fixture, width, height):
    ed = request.getfixturevalue(fixture)
    ed.page.set_viewport_size({'width': width, 'height': height})
    tile = logo(ed).locator('.logo')
    assert tile.is_visible()
    box = tile.bounding_box()
    assert box['width'] >= 24 and box['height'] >= 24                 # big enough to tap
    header = ed.page.locator('header').bounding_box()
    assert header['y'] <= box['y'] and box['y'] + box['height'] <= header['y'] + header['height']
    assert ed.page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    name_shown = logo(ed).locator('.name').bounding_box()['width'] > 1   # on phones it's kept only for screen readers
    assert name_shown == (width > 720 and height > 500)                  # phones show the tile alone
