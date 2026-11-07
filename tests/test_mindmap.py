"""Opening and saving mind maps as zipped YAML in mindmap-editor.html."""
import json
import zipfile
from pathlib import Path

import jsonschema
import pytest
import yaml

from conftest import LOCAL_LIBS, ROOT, _use_local_libs

SCHEMA = json.loads((ROOT / 'mindmap-schema.json').read_text())
SAMPLE_TOP = ['CRUDulator', 'Mind map editor', 'SQLite browser', 'Repo housekeeping']


class MindMap:
    """Drives mindmap-editor.html."""

    def __init__(self, page, url):
        self.page, self.url = page, url
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))

    def load(self):
        self.page.goto(self.url)
        self.page.wait_for_selector('.node.root')

    def titles(self):
        return self.page.locator('.node .t').all_inner_texts()

    def node(self, title):
        return self.page.locator('.node', has=self.page.locator('.t', has_text=title)).first

    def message(self):
        return self.page.text_content('#toast')

    def save(self, folder):
        with self.page.expect_download() as d:
            self.page.click('#bSave')
        path = Path(folder) / d.value.suggested_filename
        d.value.save_as(path)
        return path

    def open(self, path):
        before = self.message()
        self.page.set_input_files('#fileIn', str(path))
        self.page.wait_for_function('t => document.querySelector("#toast").innerText !== t', arg=before)

    def new_map(self):
        self.page.click('#bNew')

    def add_link(self, title, url):
        self.node(title).click()
        self.page.fill('#link', url)
        self.page.press('#link', 'Enter')

    def connect(self, source, target, label=''):
        self.node(source).click()
        self.page.click('#bConnect')
        self.node(target).click()
        if label:
            self.page.fill('#connLabel', label)

    def connectors(self):
        return self.page.locator('#edges path.conn').count()

    def connector_labels(self):
        return self.page.locator('#edges .clabel').all_text_contents()


@pytest.fixture
def mm(page, server):
    """A fresh editor showing the example map; each test gets new browser storage."""
    if LOCAL_LIBS:
        _use_local_libs(page)
    m = MindMap(page, server + '/mindmap-editor.html')
    m.load()
    yield m
    assert not m.errors, f'JavaScript errors on the page: {m.errors}'


def read_zip(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        return names, yaml.safe_load(z.read(names[0]).decode('utf-8'))


def write_zip(path, text, name='map.yaml'):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(name, text)
    return path


def child_titles(node):
    return [c['title'] for c in node.get('children', {}).values()]


def test_save_gives_a_zip_holding_one_yaml_file_in_the_schema_format(mm, tmp_path):
    path = mm.save(tmp_path)
    assert path.name == 'toolbox.zip'
    names, data = read_zip(path)
    assert names == ['toolbox.yaml']
    jsonschema.validate(data, SCHEMA)
    assert data['root']['title'] == 'Toolbox'
    assert data['root']['note'].startswith('Browser-based tools')
    assert child_titles(data['root']) == SAMPLE_TOP
    assert child_titles(data['root']['children']['crudulator'])[-1] == 'Demo video'


def test_a_saved_map_opens_unchanged(mm, tmp_path):
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    first = mm.save(tmp_path / 'a')
    mm.new_map()
    assert mm.titles() == ['New mind map']
    mm.open(first)
    assert 'Opened' in mm.message()
    second = mm.save(tmp_path / 'b')
    assert read_zip(first) == read_zip(second)


def test_opens_a_zip_written_elsewhere(mm, tmp_path):
    path = write_zip(tmp_path / 'trip.zip', '''
root:
  title: Holiday
  children:
    travel:
      title: Travel
      note: Book the ferry early
      children:
        ferry: {title: Harwich ferry}
    food:
      title: Food
''')
    mm.open(path)
    assert set(mm.titles()) == {'Holiday', 'Travel', 'Harwich ferry', 'Food'}
    assert mm.node('Travel').locator('.ni').count() == 1
    mm.node('Travel').click()
    assert mm.page.input_value('#note') == 'Book the ferry early'


def test_opens_a_plain_yaml_file_too(mm, tmp_path):
    path = tmp_path / 'small.yaml'
    path.write_text('root:\n  title: Small\n  children:\n    a: {title: Only child}\n')
    mm.open(path)
    assert mm.titles() == ['Small', 'Only child']


@pytest.mark.parametrize('text, problem', [
    ('root:\n  note: no title here\n', 'has no title'),
    ('title: no root\n', '"root"'),
    ('root: [\n', 'not valid YAML'),
])
def test_a_bad_file_is_reported_and_the_map_is_kept(mm, tmp_path, text, problem):
    before = mm.titles()
    mm.open(write_zip(tmp_path / 'bad.zip', text))
    assert problem in mm.message()
    assert mm.titles() == before


def test_a_zip_without_yaml_is_reported(mm, tmp_path):
    before = mm.titles()
    mm.open(write_zip(tmp_path / 'other.zip', 'hello', name='readme.txt'))
    assert 'no .yaml file' in mm.message()
    assert mm.titles() == before


def test_undo_brings_back_the_map_replaced_by_open(mm, tmp_path):
    mm.open(write_zip(tmp_path / 'x.zip', 'root:\n  title: X\n  children:\n    y: {title: Y}\n'))
    assert mm.titles() == ['X', 'Y']
    mm.page.click('#bUndo')
    assert mm.titles()[0] == 'Toolbox'


def test_siblings_with_the_same_title_keep_separate_keys(mm, tmp_path):
    mm.new_map()
    for _ in range(2):
        mm.node('New mind map').click()
        mm.page.click('#bChild')
        mm.page.keyboard.press('Enter')
    names, data = read_zip(mm.save(tmp_path))
    assert names == ['new_mind_map.yaml']
    jsonschema.validate(data, SCHEMA)
    assert list(data['root']['children']) == ['new_node', 'new_node_2']


# ---------- web links on nodes ----------

def test_a_link_shows_an_icon_that_opens_it_in_a_new_tab(mm):
    mm.add_link('SQLite browser', 'example.org/sqlite')
    icon = mm.node('SQLite browser').locator('a.li')
    assert icon.get_attribute('href') == 'https://example.org/sqlite'
    assert icon.get_attribute('target') == '_blank'


def test_clearing_the_link_box_removes_the_link(mm):
    mm.add_link('SQLite browser', 'https://example.org')
    mm.add_link('SQLite browser', '')
    assert mm.node('SQLite browser').locator('a.li').count() == 0


# ---------- connectors between nodes ----------

def test_a_connector_is_drawn_with_its_label(mm):
    mm.connect('Foreign keys', 'Multiple tables', 'needs')
    assert mm.connectors() == 1
    assert mm.connector_labels() == ['needs']


def test_escape_cancels_connecting(mm):
    mm.node('Foreign keys').click()
    mm.page.click('#bConnect')
    mm.page.keyboard.press('Escape')
    mm.node('Multiple tables').click()
    assert mm.connectors() == 0


def test_a_selected_connector_can_be_deleted(mm):
    mm.connect('Foreign keys', 'SQLite browser', 'uses')
    mm.page.locator('#edges .clabel').click()
    assert mm.page.is_visible('#connPanel')
    mm.page.click('#connDel')
    assert mm.connectors() == 0


def test_deleting_a_node_removes_connectors_to_and_from_it(mm):
    mm.connect('Foreign keys', 'SQLite browser')
    mm.connect('SQLite browser', 'Demo video')
    mm.node('SQLite browser').click()
    mm.page.keyboard.press('Delete')
    assert mm.connectors() == 0


# ---------- saving and opening links and connectors ----------

def test_links_and_connectors_are_saved_and_opened(mm, tmp_path):
    mm.add_link('SQLite browser', 'https://example.org/sqlite')
    mm.connect('Foreign keys', 'Multiple tables', 'needs')
    mm.connect('Demo video', 'Toolbox')
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    first = mm.save(tmp_path / 'a')
    _, data = read_zip(first)
    jsonschema.validate(data, SCHEMA)
    kids = data['root']['children']
    assert kids['sqlite_browser']['link'] == 'https://example.org/sqlite'
    assert kids['crudulator']['children']['foreign_keys']['connectors'] == [
        {'to': 'root/crudulator/multiple_tables', 'label': 'needs'}]
    assert kids['crudulator']['children']['demo_video']['connectors'] == [{'to': 'root'}]

    mm.new_map()
    mm.open(first)
    assert mm.connectors() == 2
    assert mm.connector_labels() == ['needs']
    assert read_zip(mm.save(tmp_path / 'b')) == read_zip(first)


def test_a_connector_to_a_missing_node_is_reported(mm, tmp_path):
    before = mm.titles()
    mm.open(write_zip(tmp_path / 'bad.zip', """
root:
  title: A
  children:
    b:
      title: B
      connectors:
        - to: root/nowhere
"""))
    assert 'not in the map' in mm.message()
    assert mm.titles() == before
