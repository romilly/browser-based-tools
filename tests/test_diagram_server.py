"""The server (mindmap_server.py) also serves the Diagram Editor and keeps diagrams in a folder on the local network."""
import json

import pytest
import yaml

from conftest import LOCAL_LIBS, ROOT, _use_local_libs
from test_diagram import Diagram, SMALL
from test_mindmap_server import call, maps, zip_bytes  # noqa: F401 (maps is a fixture)

from mindmap_server import start_mind_map_server

GARDEN = '''diagram:
  title: Garden
  nodes:
    beans:
      label: Beans
      outputs:
        out1: {}
      layout: {x: 0, y: 0}
    soup:
      label: Soup
      inputs:
        in1: {}
      layout: {x: 240, y: 0}
  edges:
    - {from: beans.out1, to: soup.in1}
'''


def put(base, name, text=GARDEN, headers=None):
    return call(f'{base}/api/diagrams/{name}.yaml', 'PUT', text.encode(), headers)


# --- the API ---

def test_serves_the_diagram_editor_beside_the_mind_map_editor(maps):
    base, _ = maps
    status, headers, body = call(base + '/diagram-editor.html')
    assert status == 200 and 'text/html' in headers['Content-Type']
    assert body == (ROOT / 'diagram-editor.html').read_bytes()
    assert call(base + '/')[2] == (ROOT / 'mindmap-editor.html').read_bytes()       # the mind map editor stays at the top


def test_an_empty_server_lists_no_diagrams_and_makes_no_folder_for_them(maps):
    base, folder = maps
    status, _, body = call(base + '/api/diagrams')
    assert status == 200 and json.loads(body) == []
    assert list(folder.iterdir()) == []


def test_a_saved_diagram_is_kept_in_the_diagrams_folder_listed_and_read_back(maps):
    base, folder = maps
    status, headers, _ = put(base, 'garden')
    assert status == 200 and headers['ETag']
    assert (folder / 'diagrams' / 'garden.yaml').read_text() == GARDEN
    listed = json.loads(call(base + '/api/diagrams')[2])
    assert [d['name'] for d in listed] == ['garden'] and listed[0]['etag'] == headers['ETag']
    status, got, body = call(base + '/api/diagrams/garden.yaml')
    assert status == 200 and body.decode() == GARDEN and got['ETag'] == headers['ETag']
    assert 'yaml' in got['Content-Type']


def test_maps_and_diagrams_are_listed_apart(maps):
    base, _ = maps
    put(base, 'garden')
    call(base + '/api/maps/garden.zip', 'PUT', zip_bytes())
    assert [m['name'] for m in json.loads(call(base + '/api/maps')[2])] == ['garden']
    assert [d['name'] for d in json.loads(call(base + '/api/diagrams')[2])] == ['garden']
    assert call(base + '/api/diagrams/garden.zip')[0] == 404
    assert call(base + '/api/maps/garden.yaml')[0] == 404


def test_saving_over_a_diagram_someone_else_changed_is_refused(maps):
    base, folder = maps
    first = put(base, 'garden')[1]['ETag']
    assert put(base, 'garden', GARDEN.replace('Soup', 'Stew'), {'If-Match': first})[0] == 200
    assert put(base, 'garden', GARDEN, {'If-Match': first})[0] == 409
    assert put(base, 'garden', GARDEN, {'If-None-Match': '*'})[0] == 409
    assert 'Stew' in (folder / 'diagrams' / 'garden.yaml').read_text()


@pytest.mark.parametrize('name', ['../escape.yaml', 'Garden.yaml', 'gar%20den.yaml', '.yaml', 'garden.yml'])
def test_names_other_than_editor_keys_are_refused(maps, name):
    base, folder = maps
    assert call(f'{base}/api/diagrams/{name}', 'PUT', GARDEN.encode())[0] in (400, 404)
    assert not any(folder.parent.rglob('escape.yaml')) and not (folder / 'diagrams').exists()


def test_a_file_that_is_not_text_is_refused(maps):
    base, folder = maps
    assert call(base + '/api/diagrams/garden.yaml', 'PUT', b'\xff\xfe\x00 not text')[0] == 400
    assert call(base + '/api/diagrams/garden.yaml', 'PUT', b'')[0] == 400
    assert not (folder / 'diagrams').exists()


def test_diagrams_can_be_kept_in_a_folder_of_their_own(tmp_path):
    srv = start_mind_map_server(tmp_path / 'maps', port=0, host='127.0.0.1', diagrams=tmp_path / 'designs')
    try:
        base = f'http://127.0.0.1:{srv.server_port}'
        assert put(base, 'garden')[0] == 200
        assert (tmp_path / 'designs' / 'garden.yaml').read_text() == GARDEN
    finally:
        srv.shutdown()


# --- the editor, served by the server ---

@pytest.fixture
def sdg(page, maps):
    """The Diagram Editor opened from the server, with (base URL, folder) as sdg.server."""
    if LOCAL_LIBS:
        _use_local_libs(page)
    d = Diagram(page, maps[0] + '/diagram-editor.html')
    d.server = maps
    d.load()
    page.wait_for_selector('#bServerSave:not([hidden])', state='attached')
    yield d
    assert not d.errors, f'JavaScript errors on the page: {d.errors}'


def stored(sdg, name='garden'):
    return (sdg.server[1] / 'diagrams' / f'{name}.yaml').read_text()


def server_save(dg, expect='Saved'):
    dg.page.evaluate('document.querySelector("#toast").innerText = ""')
    dg.menu('File', '#bServerSave')
    dg.page.wait_for_function('document.querySelector("#toast").innerText !== ""')
    assert expect in dg.message()


def server_open(dg, name):
    dg.menu('File', '#bServerOpen')
    dg.page.wait_for_selector('#serverFiles[open]')
    before = dg.message()
    dg.page.click(f'#serverFiles button[data-name="{name}"]')
    dg.page.wait_for_function('t => document.querySelector("#toast").innerText !== t', arg=before)


def open_link(dg, name):
    base, _ = dg.server
    dg.page.goto(f'{base}/diagram-editor.html?diagram={name}')
    dg.page.wait_for_selector('#canvas')
    dg.page.wait_for_function('document.querySelector("#toast").innerText !== ""')


def add_node(dg):
    dg.add_node()
    dg.page.keyboard.press('Escape')


def test_without_a_server_the_server_commands_stay_hidden(page, server):
    if LOCAL_LIBS:
        _use_local_libs(page)
    d = Diagram(page, server + '/diagram-editor.html')
    d.load()
    d.menu('File')
    assert page.locator('#bServerOpen').is_hidden() and page.locator('#bServerSave').is_hidden()


def test_save_to_server_stores_the_same_yaml_as_save(sdg, tmp_path):
    path = tmp_path / 'small.yaml'
    path.write_text(SMALL)
    sdg.open(path)
    server_save(sdg)
    assert stored(sdg, 'small') == sdg.save(tmp_path / 'out').read_text()


def test_open_from_server_lists_the_diagrams_and_opens_one(sdg):
    base, _ = sdg.server
    put(base, 'garden')
    put(base, 'kitchen', GARDEN.replace('Garden', 'Kitchen'))
    sdg.menu('File', '#bServerOpen')
    sdg.page.wait_for_selector('#serverFiles[open]')
    assert sorted(sdg.page.locator('#serverFiles button[data-name]').evaluate_all('bs => bs.map(b => b.dataset.name)')) == ['garden', 'kitchen']
    sdg.page.keyboard.press('Escape')
    server_open(sdg, 'garden')
    assert 'Opened garden' in sdg.message()
    assert sdg.title() == 'Garden' and sdg.nodes() == ['beans', 'soup']
    assert sdg.page.url == f'{base}/diagram-editor.html?diagram=garden'


def test_the_list_says_when_there_are_no_diagrams(sdg):
    sdg.menu('File', '#bServerOpen')
    sdg.page.wait_for_selector('#serverFiles[open]')
    assert 'No diagrams' in sdg.page.inner_text('#serverList')


def test_a_link_opens_a_diagram_and_ctrl_s_saves_it_back_under_its_own_name(sdg):
    base, folder = sdg.server
    put(base, 'garden')
    open_link(sdg, 'garden')
    assert 'Opened garden' in sdg.message() and sdg.nodes() == ['beans', 'soup']
    sdg.page.on('dialog', lambda d: pytest.fail('unexpected question: ' + d.message))
    sdg.page.on('download', lambda d: pytest.fail('downloaded ' + d.suggested_filename))
    sdg.page.fill('#title', 'Allotment')                      # renaming doesn't change where it is saved
    add_node(sdg)
    sdg.page.keyboard.press('Control+s')
    sdg.page.wait_for_function('document.querySelector("#toast").innerText.includes("to the server")')
    data = yaml.safe_load(stored(sdg))['diagram']
    assert data['title'] == 'Allotment' and list(data['nodes']) == ['beans', 'soup', 'node']
    assert sorted(p.name for p in (folder / 'diagrams').iterdir()) == ['garden.yaml']


def test_ctrl_s_downloads_a_diagram_that_did_not_come_from_the_server(sdg):
    with sdg.page.expect_download() as d:
        sdg.page.keyboard.press('Control+s')
    assert d.value.suggested_filename == 'new_diagram.yaml'


def test_saving_over_a_change_from_another_device_asks_first(sdg):
    base, _ = sdg.server
    put(base, 'garden')
    open_link(sdg, 'garden')
    put(base, 'garden', GARDEN.replace('Soup', 'Stew'))       # another device saves a newer version
    add_node(sdg)
    answers = []
    sdg.page.once('dialog', lambda d: (answers.append(d.message), d.dismiss()))
    server_save(sdg, expect='Not saved')
    assert 'changed' in answers[0] and 'Stew' in stored(sdg)
    sdg.page.once('dialog', lambda d: d.accept())
    server_save(sdg)
    assert 'Soup' in stored(sdg) and 'node:' in stored(sdg)


def test_saving_a_new_diagram_over_one_already_on_the_server_asks_first(sdg):
    base, _ = sdg.server
    put(base, 'new_diagram', GARDEN)
    answers = []
    sdg.page.once('dialog', lambda d: (answers.append(d.message), d.dismiss()))
    server_save(sdg, expect='Not saved')
    assert 'already' in answers[0] and 'Garden' in stored(sdg, 'new_diagram')


def test_the_address_bar_follows_the_diagram(sdg):
    base, _ = sdg.server
    put(base, 'garden')
    open_link(sdg, 'garden')
    sdg.new_diagram()
    assert sdg.page.url == f'{base}/diagram-editor.html'
    server_save(sdg)
    assert sdg.page.url == f'{base}/diagram-editor.html?diagram=new_diagram'


def test_a_link_to_a_diagram_that_is_not_there_says_so(sdg):
    add_node(sdg)
    open_link(sdg, 'nothing')
    assert 'nothing' in sdg.message() and 'not on the server' in sdg.message()
    assert sdg.nodes() == ['node']


def test_closing_with_changes_not_saved_to_the_server_asks_first(sdg):
    base, _ = sdg.server
    put(base, 'garden')
    open_link(sdg, 'garden')
    assert not sdg.page.evaluate('hasUnsavedChanges()')
    add_node(sdg)
    assert sdg.page.evaluate('hasUnsavedChanges()')
    server_save(sdg)
    assert not sdg.page.evaluate('hasUnsavedChanges()')
    add_node(sdg)
    sdg.page.once('dialog', lambda d: d.dismiss())
    with sdg.page.expect_event('dialog') as asked:
        sdg.page.close(run_before_unload=True)
    assert asked.value.type == 'beforeunload'
