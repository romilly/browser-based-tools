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

    def menu(self, name, item=None):
        """Open a menu on the menu bar (File, Icons) and optionally choose one of its items."""
        self.page.click(f'#menubar button.mb:text-is("{name}")')
        if item:
            self.page.click(item)

    def save(self, folder):
        with self.page.expect_download() as d:
            self.menu('File', '#bSave')
        path = Path(folder) / d.value.suggested_filename
        d.value.save_as(path)
        return path

    def icons_of(self, title):
        return self.node(title).locator('.ic').evaluate_all('es => es.map(e => e.dataset.icon)')

    def toggle_icons(self, title, *names):
        self.node(title).click()
        self.menu('Icons')
        for n in names:
            self.page.click(f'#mIcons [data-icon="{n}"]')
        self.page.keyboard.press('Escape')

    def open(self, path):
        before = self.message()
        self.page.set_input_files('#fileIn', str(path))
        self.page.wait_for_function('t => document.querySelector("#toast").innerText !== t', arg=before)

    def new_map(self):
        self.menu('File', '#bNew')

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


CRUD_KIDS = ['Foreign keys', 'Multiple tables', 'Screen designer', 'Demo video']


def crud_kids(mm):
    titles = mm.titles()
    i = titles.index('CRUDulator') + 1
    return titles[i:i + 4]


# ---------- moving branches up and down ----------

def test_ctrl_up_moves_a_branch_above_its_previous_sibling(mm):
    mm.node('Multiple tables').click()
    mm.page.keyboard.press('Control+ArrowUp')
    assert crud_kids(mm) == ['Multiple tables', 'Foreign keys', 'Screen designer', 'Demo video']
    assert 'sel' in mm.node('Multiple tables').get_attribute('class')


def test_ctrl_down_moves_a_branch_below_its_next_sibling(mm):
    mm.node('Foreign keys').click()
    mm.page.keyboard.press('Control+ArrowDown')
    mm.page.keyboard.press('Control+ArrowDown')
    assert crud_kids(mm) == ['Multiple tables', 'Screen designer', 'Foreign keys', 'Demo video']


def test_a_branch_at_the_end_stays_put_and_its_button_is_disabled(mm):
    mm.node('Foreign keys').click()
    assert mm.page.is_disabled('#bUp')
    mm.page.keyboard.press('Control+ArrowUp')
    mm.node('Demo video').click()
    assert mm.page.is_disabled('#bDown')
    mm.page.keyboard.press('Control+ArrowDown')
    assert crud_kids(mm) == CRUD_KIDS
    assert mm.page.is_disabled('#bUndo')


def test_the_buttons_move_branches_too(mm):
    mm.node('Screen designer').click()
    mm.page.click('#bUp')
    assert crud_kids(mm) == ['Foreign keys', 'Screen designer', 'Multiple tables', 'Demo video']
    mm.page.click('#bDown')
    assert crud_kids(mm) == CRUD_KIDS


def test_main_branches_move_only_within_their_side_of_the_root(mm, tmp_path):
    mm.node('SQLite browser').click()        # top of the left side
    assert mm.page.is_disabled('#bUp')
    mm.node('Mind map editor').click()       # bottom of the right side
    assert mm.page.is_disabled('#bDown')
    mm.page.keyboard.press('Control+ArrowUp')
    _, data = read_zip(mm.save(tmp_path))
    assert child_titles(data['root']) == ['Mind map editor', 'CRUDulator', 'SQLite browser', 'Repo housekeeping']


def test_undo_puts_a_moved_branch_back(mm):
    mm.node('Demo video').click()
    mm.page.keyboard.press('Control+ArrowUp')
    mm.page.click('#bUndo')
    assert crud_kids(mm) == CRUD_KIDS


# ---------- menus and toolbar ----------

ACCELERATED = ['Child', 'Sibling', 'Edit', 'Fold', 'Up', 'Down', 'Connect', 'Delete', 'Undo', 'Redo']


def test_the_toolbar_only_has_commands_with_keys(mm):
    labels = mm.page.locator('#toolbar button').evaluate_all('bs => bs.map(b => b.firstChild.textContent.trim())')
    assert labels == ACCELERATED
    assert mm.page.locator('#toolbar button:not([title*="("])').count() == 0   # every tooltip names its key


def test_file_commands_are_in_the_file_menu(mm):
    assert not mm.page.is_visible('#bSave')
    mm.menu('File')
    assert mm.page.is_visible('#bNew') and mm.page.is_visible('#bOpen') and mm.page.is_visible('#bSave')
    mm.page.keyboard.press('Escape')
    assert not mm.page.is_visible('#mFile')


def test_clicking_the_map_closes_a_menu(mm):
    mm.menu('File')
    mm.node('SQLite browser').click()
    assert not mm.page.is_visible('#mFile')
    assert 'sel' in mm.node('SQLite browser').get_attribute('class')


def test_ctrl_s_saves(mm, tmp_path):
    with mm.page.expect_download() as d:
        mm.page.keyboard.press('Control+s')
    assert d.value.suggested_filename == 'toolbox.zip'


# ---------- icons ----------

def test_an_icon_from_the_icons_menu_is_shown_before_the_title(mm):
    mm.toggle_icons('Foreign keys', 'idea')
    assert mm.icons_of('Foreign keys') == ['idea']
    first = mm.node('Foreign keys').evaluate('e => e.firstElementChild.className')
    assert first == 'ic'


def test_choosing_an_icon_again_removes_it(mm):
    mm.toggle_icons('Foreign keys', 'full-1', 'idea')
    mm.menu('Icons')
    assert mm.page.get_attribute('#mIcons [data-icon="idea"]', 'aria-pressed') == 'true'
    assert mm.page.get_attribute('#mIcons [data-icon="yes"]', 'aria-pressed') == 'false'
    mm.page.click('#mIcons [data-icon="full-1"]')
    assert mm.icons_of('Foreign keys') == ['idea']


def test_remove_all_icons_and_undo(mm):
    mm.toggle_icons('Foreign keys', 'full-1', 'idea')
    mm.menu('Icons', '#iClear')
    assert mm.icons_of('Foreign keys') == []
    mm.page.keyboard.press('Escape')
    mm.page.click('#bUndo')
    assert mm.icons_of('Foreign keys') == ['full-1', 'idea']


def test_icons_are_saved_and_opened(mm, tmp_path):
    mm.toggle_icons('Foreign keys', 'full-1', 'button_ok')
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    first = mm.save(tmp_path / 'a')
    _, data = read_zip(first)
    jsonschema.validate(data, SCHEMA)
    assert data['root']['children']['crudulator']['children']['foreign_keys']['icons'] == ['full-1', 'button_ok']
    assert 'icons' not in data['root']['children']['crudulator']
    mm.new_map()
    mm.open(first)
    assert mm.icons_of('Foreign keys') == ['full-1', 'button_ok']
    assert read_zip(mm.save(tmp_path / 'b')) == read_zip(first)


def test_an_unknown_icon_name_is_kept(mm, tmp_path, ):
    mm.open(write_zip(tmp_path / 'u.zip', 'root:\n  title: U\n  children:\n    a: {title: A, icons: [idea, korn]}\n'))
    assert mm.icons_of('A') == ['idea', 'korn']
    _, data = read_zip(mm.save(tmp_path))
    assert data['root']['children']['a']['icons'] == ['idea', 'korn']


def test_icons_that_are_not_a_list_are_reported(mm, tmp_path):
    before = mm.titles()
    mm.open(write_zip(tmp_path / 'bad.zip', 'root:\n  title: B\n  icons: idea\n  children:\n    a: {title: A}\n'))
    assert 'icons' in mm.message()
    assert mm.titles() == before


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


# Notes are Markdown: typed as text, shown formatted when you're not editing them.

def note_view(mm):
    return mm.page.locator('#noteView')


def write_note(mm, title, text):
    mm.node(title).click()
    if note_view(mm).is_visible():
        note_view(mm).click()
    mm.page.fill('#note', text)
    mm.page.press('#note', 'Escape')


def test_a_note_is_shown_formatted_after_editing(mm):
    write_note(mm, 'CRUDulator', '**Book** early\n\n- ferry\n- train')
    view = note_view(mm)
    assert view.is_visible()
    assert not mm.page.locator('#note').is_visible()
    assert view.locator('strong').inner_text() == 'Book'
    assert view.locator('li').all_inner_texts() == ['ferry', 'train']


def test_clicking_a_formatted_note_edits_the_markdown(mm):
    write_note(mm, 'CRUDulator', '*soon*')
    note_view(mm).click()
    assert mm.page.locator('#note').is_visible()
    assert mm.page.evaluate('document.activeElement.id') == 'note'
    assert mm.page.input_value('#note') == '*soon*'


def test_a_node_without_a_note_shows_the_empty_note_box(mm):
    write_note(mm, 'CRUDulator', '')
    assert mm.page.locator('#note').is_visible()
    assert not note_view(mm).is_visible()


def test_links_in_a_note_open_in_a_new_tab(mm):
    write_note(mm, 'CRUDulator', 'See [the ferry](https://www.stenaline.co.uk)')
    a = note_view(mm).locator('a')
    assert a.get_attribute('href') == 'https://www.stenaline.co.uk'
    assert a.get_attribute('target') == '_blank'
    assert 'noopener' in a.get_attribute('rel')


def test_html_in_an_opened_note_cannot_run(mm, tmp_path):
    mm.open(write_zip(tmp_path / 'evil.zip', """
root:
  title: Evil
  children:
    a:
      title: A
      note: |
        Hello <img src="x" onerror="window.pwned = 1"><script>window.pwned = 2</script>
        [click](javascript:window.pwned=3)
"""))
    mm.node('A').click()
    view = note_view(mm)
    assert 'Hello' in view.inner_text()
    for link in view.locator('a').all():
        link.click()
    mm.page.wait_for_timeout(200)
    assert mm.page.evaluate('window.pwned') is None
    assert view.locator('script, [onerror]').count() == 0


def test_markdown_notes_are_saved_unchanged(mm, tmp_path):
    text = '# Plan\n\n1. **Book** the ferry\n2. Pack `bikes`\n'
    write_note(mm, 'CRUDulator', text)
    _, data = read_zip(mm.save(tmp_path))
    jsonschema.validate(data, SCHEMA)
    assert data['root']['children']['crudulator']['note'] == text


# Maths in notes: LaTeX between $...$ (in a line) or $$...$$ (on its own), drawn by MathJax.

def wait_for_maths(mm):
    mm.page.wait_for_function('!document.querySelector("#noteView .math:not(.done)")')


def test_inline_maths_is_drawn(mm):
    write_note(mm, 'CRUDulator', 'Energy is $E = mc^2$ here')
    wait_for_maths(mm)
    m = note_view(mm).locator('mjx-container')
    assert m.count() == 1
    assert m.get_attribute('display') is None
    assert 'Energy is' in note_view(mm).inner_text()
    # the copy of the formula kept for screen readers is hidden, so the formula is shown once
    clip = note_view(mm).locator('mjx-assistive-mml').evaluate('e => getComputedStyle(e).clip')
    assert clip.startswith('rect(')


def test_display_maths_is_drawn_on_its_own(mm):
    write_note(mm, 'CRUDulator', 'Sum:\n\n$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$$\n')
    wait_for_maths(mm)
    assert note_view(mm).locator('mjx-container[display="true"]').count() == 1


def test_underscores_in_maths_are_not_italics(mm):
    write_note(mm, 'CRUDulator', '$a_1 + b_1$ and $c_2$')
    wait_for_maths(mm)
    assert note_view(mm).locator('em').count() == 0
    assert note_view(mm).locator('mjx-container').count() == 2


def test_escaped_dollars_stay_dollars(mm):
    write_note(mm, 'CRUDulator', 'Costs \\$5 and \\$10')
    assert note_view(mm).inner_text().strip() == 'Costs $5 and $10'
    assert note_view(mm).locator('mjx-container, .math').count() == 0


def test_dollars_in_code_are_left_alone(mm):
    write_note(mm, 'CRUDulator', 'Run `echo $HOME $PATH`')
    assert note_view(mm).locator('code').inner_text() == 'echo $HOME $PATH'
    assert note_view(mm).locator('.math').count() == 0


def test_a_bad_formula_shows_an_error_and_the_rest_of_the_note(mm):
    write_note(mm, 'CRUDulator', 'Before $\\frac{1}$ after')
    wait_for_maths(mm)
    text = note_view(mm).inner_text()
    assert 'Before' in text and 'after' in text
    assert note_view(mm).locator('[data-mjx-error]').count() >= 1


def test_mathjax_is_only_loaded_for_notes_with_maths(mm):
    write_note(mm, 'CRUDulator', '**no maths here**')
    assert mm.page.locator('script[src*="mathjax"]').count() == 0
    write_note(mm, 'SQLite browser', '$x$')
    wait_for_maths(mm)
    assert mm.page.locator('script[src*="mathjax"]').count() == 1


def test_maths_is_saved_unchanged(mm, tmp_path):
    text = 'Area $A = \\pi r^2$\n\n$$\\int_0^1 x\\,dx = \\tfrac12$$\n'
    write_note(mm, 'CRUDulator', text)
    _, data = read_zip(mm.save(tmp_path))
    assert data['root']['children']['crudulator']['note'] == text


def test_prices_without_backslashes_stay_text(mm):
    write_note(mm, 'CRUDulator', 'Tickets $5 and $10 each')
    assert note_view(mm).inner_text().strip() == 'Tickets $5 and $10 each'
    assert note_view(mm).locator('.math').count() == 0


def test_a_script_link_in_maths_cannot_run(mm, tmp_path):
    mm.open(write_zip(tmp_path / 'evil.zip', 'root:\n  title: Evil\n  children:\n    a:\n      title: A\n'
                      '      note: \'Click $\\href{javascript:window.pwned=1}{here}$\'\n'))
    mm.node('A').click()
    wait_for_maths(mm)
    for link in note_view(mm).locator('a').all():
        link.click()
    mm.page.wait_for_timeout(200)
    assert mm.page.evaluate('window.pwned') is None
    assert note_view(mm).locator('[href^="javascript"]').count() == 0


def test_a_web_link_in_maths_works_and_opens_in_a_new_tab(mm):
    write_note(mm, 'CRUDulator', 'See $\\href{https://example.org}{x^2}$')
    wait_for_maths(mm)
    a = note_view(mm).locator('mjx-container a')
    assert a.get_attribute('href') == 'https://example.org'
    assert a.get_attribute('target') == '_blank'
    assert a.locator('use').count() >= 1        # the glyphs inside the link are still drawn


def test_help_has_a_latex_guide_with_a_link_to_more(mm):
    mm.page.click('#bHelp')
    section = mm.page.locator('#dlg section', has=mm.page.locator('h3', has_text='Maths in notes'))
    assert '\\frac{a}{b}' in section.inner_text()
    link = section.locator('a')
    assert link.get_attribute('href') == 'https://www.overleaf.com/learn/latex/Mathematical_expressions'
    assert link.get_attribute('target') == '_blank'
