"""The optional mind map server (mindmap_server.py): it serves the editor and keeps maps in a folder on the local network."""
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile

import pytest

from conftest import LOCAL_LIBS, ROOT, _use_local_libs
from test_mindmap import MindMap, mm, write_zip  # noqa: F401 (mm is a fixture)

sys.path.insert(0, str(ROOT))
from mindmap_server import start_mind_map_server  # noqa: E402

MAP = 'root:\n  title: Garden\n  children:\n    beans:\n      title: Beans\n'


def zip_bytes(text=MAP, name='garden.yaml'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(name, text)
    return buf.getvalue()


@pytest.fixture
def maps(tmp_path):
    """A running server keeping maps in an empty folder; yields (base URL, folder)."""
    folder = tmp_path / 'maps'
    folder.mkdir()
    srv = start_mind_map_server(folder, port=0, host='127.0.0.1')
    yield f'http://127.0.0.1:{srv.server_port}', folder
    srv.shutdown()


def call(url, method='GET', data=None, headers=None):
    """(status, headers, body) of a request; HTTP errors are returned, not raised."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


# --- the API ---

def test_serves_the_editor_at_the_top(maps):
    base, _ = maps
    status, headers, body = call(base + '/')
    assert status == 200 and 'text/html' in headers['Content-Type']
    assert body == (ROOT / 'mindmap-editor.html').read_bytes()


def test_an_empty_folder_lists_no_maps(maps):
    base, _ = maps
    status, _, body = call(base + '/api/maps')
    assert status == 200 and json.loads(body) == []


def test_a_saved_map_is_stored_listed_and_read_back(maps):
    base, folder = maps
    status, headers, _ = call(base + '/api/maps/garden.zip', 'PUT', zip_bytes())
    assert status == 200 and headers['ETag']
    assert (folder / 'garden.zip').read_bytes() == zip_bytes()
    listed = json.loads(call(base + '/api/maps')[2])
    assert [m['name'] for m in listed] == ['garden']
    assert listed[0]['etag'] == headers['ETag']
    status, got, body = call(base + '/api/maps/garden.zip')
    assert status == 200 and body == zip_bytes() and got['ETag'] == headers['ETag']


def test_a_missing_map_is_not_found(maps):
    base, _ = maps
    assert call(base + '/api/maps/nothing.zip')[0] == 404


def test_saving_over_a_map_someone_else_changed_is_refused(maps):
    base, _ = maps
    first = call(base + '/api/maps/garden.zip', 'PUT', zip_bytes())[1]['ETag']
    call(base + '/api/maps/garden.zip', 'PUT', zip_bytes(MAP + '    leeks:\n      title: Leeks\n'), {'If-Match': first})
    status, _, _ = call(base + '/api/maps/garden.zip', 'PUT', zip_bytes(), {'If-Match': first})
    assert status == 409


def test_a_matching_etag_saves(maps):
    base, folder = maps
    first = call(base + '/api/maps/garden.zip', 'PUT', zip_bytes())[1]['ETag']
    newer = zip_bytes(MAP + '    leeks:\n      title: Leeks\n')
    assert call(base + '/api/maps/garden.zip', 'PUT', newer, {'If-Match': first})[0] == 200
    assert (folder / 'garden.zip').read_bytes() == newer


@pytest.mark.parametrize('name', ['../escape.zip', 'Garden.zip', 'gar%20den.zip', 'garden.yaml', '.zip'])
def test_names_other_than_editor_keys_are_refused(maps, name):
    base, folder = maps
    assert call(f'{base}/api/maps/{name}', 'PUT', zip_bytes())[0] in (400, 404)
    assert not any(folder.parent.rglob('escape.zip')) and list(folder.iterdir()) == []


def test_a_file_that_is_not_a_zip_is_refused(maps):
    base, folder = maps
    assert call(base + '/api/maps/garden.zip', 'PUT', b'not a zip')[0] == 400
    assert list(folder.iterdir()) == []


def test_other_files_in_the_folder_are_not_listed(maps):
    base, folder = maps
    (folder / 'notes.txt').write_text('hello')
    (folder / 'Bad Name.zip').write_bytes(zip_bytes())
    assert json.loads(call(base + '/api/maps')[2]) == []


# --- the editor, served by the server ---

@pytest.fixture
def smm(page, maps):
    """The editor opened from the server, with (base URL, folder) as smm.server."""
    if LOCAL_LIBS:
        _use_local_libs(page)
    m = MindMap(page, maps[0] + '/')
    m.server = maps
    m.load()
    page.wait_for_selector('#bServerSave:not([hidden])', state='attached')
    yield m
    assert not m.errors, f'JavaScript errors on the page: {m.errors}'


def server_save(mm, expect='Saved'):
    mm.page.evaluate('document.querySelector("#toast").innerText = ""')
    mm.menu('File', '#bServerSave')
    mm.page.wait_for_function('document.querySelector("#toast").innerText !== ""')
    assert expect in mm.message()


def server_open(mm, name):
    mm.menu('File', '#bServerOpen')
    mm.page.wait_for_selector('#serverMaps[open]')
    before = mm.message()
    mm.page.click(f'#serverMaps button[data-map="{name}"]')
    mm.page.wait_for_function('t => document.querySelector("#toast").innerText !== t', arg=before)


def test_without_a_server_the_server_commands_stay_hidden(mm):
    mm.menu('File')
    assert mm.page.locator('#bServerOpen').is_hidden()
    assert mm.page.locator('#bServerSave').is_hidden()


def test_save_to_server_stores_the_same_zip_as_save(smm, tmp_path):
    _, folder = smm.server
    server_save(smm)
    downloaded = smm.save(tmp_path)
    stored = folder / downloaded.name
    with zipfile.ZipFile(stored) as a, zipfile.ZipFile(downloaded) as b:
        assert a.namelist() == b.namelist()
        assert all(a.read(n) == b.read(n) for n in a.namelist())


def test_open_from_server_lists_the_maps_and_opens_one(smm, tmp_path):
    _, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    server_open(smm, 'garden')
    assert 'Opened garden' in smm.message()
    assert smm.titles() == ['Garden', 'Beans']


def test_a_map_opened_from_the_server_keeps_its_images(smm, tmp_path):
    from PIL import Image
    _, folder = smm.server
    pic = io.BytesIO()
    Image.new('RGB', (40, 30), 'red').save(pic, 'PNG')
    with zipfile.ZipFile(folder / 'garden.zip', 'w') as z:
        z.writestr('garden.yaml', MAP.replace('title: Beans', 'title: Beans\n      image: images/beans.png'))
        z.writestr('images/beans.png', pic.getvalue())
    server_open(smm, 'garden')
    smm.page.wait_for_selector('.node .pic img')
    server_save(smm)
    assert 'images/beans.png' in zipfile.ZipFile(folder / 'garden.zip').namelist()


def test_saving_over_a_change_from_another_device_asks_first(smm):
    base, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    server_open(smm, 'garden')
    # another device saves a newer version
    call(base + '/api/maps/garden.zip', 'PUT', zip_bytes(MAP + '    leeks:\n      title: Leeks\n'))
    smm.node('Beans').click()
    smm.page.keyboard.press('Tab')
    smm.page.keyboard.type('Peas')
    smm.page.keyboard.press('Enter')
    answers = []
    smm.page.once('dialog', lambda d: (answers.append(d.message), d.dismiss()))
    server_save(smm, expect='Not saved')
    assert 'changed' in answers[0]
    assert 'Leeks' in zipfile.ZipFile(folder / 'garden.zip').read('garden.yaml').decode()
    smm.page.once('dialog', lambda d: d.accept())
    server_save(smm)
    assert 'Peas' in zipfile.ZipFile(folder / 'garden.zip').read('garden.yaml').decode()


def test_saving_twice_from_one_device_does_not_ask(smm):
    smm.page.on('dialog', lambda d: pytest.fail('unexpected question: ' + d.message))
    server_save(smm)
    smm.node(smm.titles()[0]).click()
    smm.page.keyboard.press('Tab')
    smm.page.keyboard.type('More')
    smm.page.keyboard.press('Enter')
    server_save(smm)


def test_if_none_match_refuses_to_replace_an_existing_map(maps):
    base, _ = maps
    assert call(base + '/api/maps/garden.zip', 'PUT', zip_bytes(), {'If-None-Match': '*'})[0] == 200
    assert call(base + '/api/maps/garden.zip', 'PUT', zip_bytes(), {'If-None-Match': '*'})[0] == 409


def test_saving_a_new_map_over_one_already_on_the_server_asks_first(smm):
    _, folder = smm.server
    name = smm.page.evaluate('slug(root.title)')
    write_zip(folder / f'{name}.zip', MAP, f'{name}.yaml')
    answers = []
    smm.page.once('dialog', lambda d: (answers.append(d.message), d.dismiss()))
    server_save(smm, expect='Not saved')
    assert 'already' in answers[0]
    assert 'Garden' in zipfile.ZipFile(folder / f'{name}.zip').read(f'{name}.yaml').decode()


def test_the_server_maps_list_says_when_there_are_none(smm):
    smm.menu('File', '#bServerOpen')
    smm.page.wait_for_selector('#serverMaps[open]')
    assert 'No maps' in smm.page.inner_text('#serverList')
    smm.page.keyboard.press('Escape')
    assert not smm.page.locator('#serverMaps[open]').count()


# --- links to maps on the server (for example from an Obsidian note) ---

def open_link(mm, name):
    """Load the editor from the server with ?map=<name>, and wait for it to report opening (or failing)."""
    base, _ = mm.server
    mm.page.goto(f'{base}/?map={name}')
    mm.page.wait_for_selector('.node.root')
    mm.page.wait_for_function('document.querySelector("#toast").innerText !== ""')


def add_child(mm, parent, title):
    mm.node(parent).click()
    mm.page.keyboard.press('Tab')
    mm.page.keyboard.type(title)
    mm.page.keyboard.press('Enter')


def stored_yaml(folder, name='garden'):
    with zipfile.ZipFile(folder / f'{name}.zip') as z:
        return z.read(next(n for n in z.namelist() if n.endswith('.yaml'))).decode()


def test_a_link_opens_a_map_from_the_server(smm):
    _, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    open_link(smm, 'garden')
    assert 'Opened garden' in smm.message()
    assert smm.titles() == ['Garden', 'Beans']


def test_a_linked_map_saves_back_to_the_server_without_asking(smm):
    _, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    open_link(smm, 'garden')
    smm.page.on('dialog', lambda d: pytest.fail('unexpected question: ' + d.message))
    add_child(smm, 'Beans', 'Peas')
    server_save(smm)
    assert 'Peas' in stored_yaml(folder)


def test_a_renamed_linked_map_saves_back_under_its_own_name(smm):
    _, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    open_link(smm, 'garden')
    smm.node('Garden').dblclick()
    smm.page.keyboard.press('Control+A')
    smm.page.keyboard.type('Allotment')
    smm.page.keyboard.press('Enter')
    server_save(smm)
    assert 'Allotment' in stored_yaml(folder)
    assert sorted(p.name for p in folder.iterdir()) == ['garden.zip']
    assert smm.page.url.endswith('/?map=garden')


def test_ctrl_s_saves_a_server_map_to_the_server(smm):
    _, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    open_link(smm, 'garden')
    smm.page.on('download', lambda d: pytest.fail('downloaded ' + d.suggested_filename))
    add_child(smm, 'Beans', 'Peas')
    smm.page.keyboard.press('Control+s')
    smm.page.wait_for_function('document.querySelector("#toast").innerText.includes("to the server")')
    assert 'Peas' in stored_yaml(folder)


def test_ctrl_s_downloads_a_map_that_did_not_come_from_the_server(smm, tmp_path):
    with smm.page.expect_download() as d:
        smm.page.keyboard.press('Control+s')
    assert d.value.suggested_filename.endswith('.zip')


def test_a_link_to_a_map_that_is_not_there_says_so(smm):
    before = smm.titles()
    open_link(smm, 'nothing')
    assert 'nothing' in smm.message() and 'not on the server' in smm.message()
    assert smm.titles() == before


def test_a_link_with_a_bad_name_says_so(smm):
    before = smm.titles()
    open_link(smm, 'Bad%20Name')
    assert 'Bad Name' in smm.message() and 'not on the server' in smm.message()
    assert smm.titles() == before


def test_the_address_bar_links_to_the_map_on_the_server(smm):
    base, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    server_open(smm, 'garden')
    assert smm.page.url == f'{base}/?map=garden'
    smm.menu('File', '#bNew')
    assert smm.page.url == f'{base}/'
    server_save(smm)
    assert smm.page.url == f'{base}/?map=new_mind_map'


def test_closing_with_changes_not_saved_to_the_server_asks_first(smm):
    _, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    open_link(smm, 'garden')
    unsaved = 'hasUnsavedChanges()'
    assert not smm.page.evaluate(unsaved)
    add_child(smm, 'Beans', 'Peas')
    assert smm.page.evaluate(unsaved)
    smm.page.once('dialog', lambda d: d.dismiss())    # stay on the page
    with smm.page.expect_event('dialog') as asked:
        smm.page.close(run_before_unload=True)
    assert asked.value.type == 'beforeunload'


def test_saving_to_the_server_clears_the_warning(smm):
    _, folder = smm.server
    write_zip(folder / 'garden.zip', MAP, 'garden.yaml')
    open_link(smm, 'garden')
    add_child(smm, 'Beans', 'Peas')
    server_save(smm)
    assert not smm.page.evaluate('hasUnsavedChanges()')


def test_a_map_from_a_link_keeps_its_images_after_a_reload(smm):
    from PIL import Image
    base, folder = smm.server
    pic = io.BytesIO()
    Image.new('RGB', (40, 30), 'red').save(pic, 'PNG')
    with zipfile.ZipFile(folder / 'garden.zip', 'w') as z:
        z.writestr('garden.yaml', MAP.replace('title: Beans', 'title: Beans\n      image: images/beans.png'))
        z.writestr('images/beans.png', pic.getvalue())
    open_link(smm, 'garden')
    smm.page.wait_for_selector('.node .pic img')
    smm.page.goto(base + '/')                  # the autosaved copy, without the link
    smm.page.wait_for_function('imagesReady')
    smm.page.wait_for_selector('.node .pic img')
