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


# The schema matches what the editor writes.

def test_a_new_map_with_only_a_root_is_saved_in_the_schema_format(mm, tmp_path):
    mm.new_map()
    _, data = read_zip(mm.save(tmp_path))
    assert data == {'root': {'title': 'New mind map'}}
    jsonschema.validate(data, SCHEMA)


def test_the_schema_examples_are_valid_and_open_unchanged(mm, tmp_path):
    for i, example in enumerate(SCHEMA['examples']):
        jsonschema.validate(example, SCHEMA)
        path = write_zip(tmp_path / f'ex{i}.zip', yaml.safe_dump(example, sort_keys=False, allow_unicode=True))
        mm.open(path)
        assert 'Opened' in mm.message()
        _, saved = read_zip(mm.save(tmp_path / f'out{i}'))
        assert saved == example


# mindmap-editor/reference/file-format.md: its examples and its checker must match what the editor does.

FORMAT_DOC = (ROOT / 'mindmap-editor' / 'reference' / 'file-format.md').read_text()


def doc_blocks(language):
    """The doc's fenced code blocks in a language, as (text, marked_wrong) pairs."""
    import re
    return [(m['code'], bool(m['wrong']))
            for m in re.finditer(r'(?P<wrong><!-- wrong -->\n)?```' + language + r'\n(?P<code>.*?)```', FORMAT_DOC, re.S)]


def doc_checker():
    """check_mind_map from the doc, bound to the schema."""
    code, _ = doc_blocks('python')[0]
    space = {}
    exec(code, space)
    return lambda text: space['check_mind_map'](text, SCHEMA)


def test_the_format_doc_examples_are_valid_and_open_unchanged(mm, tmp_path):
    good = [text for text, wrong in doc_blocks('yaml') if not wrong]
    assert len(good) >= 6
    for i, text in enumerate(good):
        data = yaml.safe_load(text)
        jsonschema.validate(data, SCHEMA)
        mm.open(write_zip(tmp_path / f'doc{i}.zip', text))
        assert 'Opened' in mm.message(), text
        _, saved = read_zip(mm.save(tmp_path / f'out{i}'))
        assert saved == data, text


def test_the_complete_example_puts_branches_on_the_sides_the_doc_says(mm, tmp_path):
    complete = doc_blocks('yaml')[-1][0]
    mm.open(write_zip(tmp_path / 'c.zip', complete))
    sides = mm.page.evaluate('root.children.map(c => c.title + ":" + c.side)')
    assert sides == ['Travel:right', 'Budget:right', 'Places:left', 'To do: before we go:left']


def test_the_doc_checker_passes_the_examples_and_finds_each_mistake():
    check = doc_checker()
    for text, wrong in doc_blocks('yaml'):
        assert (check(text) != []) == wrong, text
    good = 'root:\n  title: A\n  children:\n    b: {title: B}\n'
    assert check(good) == []
    assert 'duplicate' in check(good + '    b: {title: C}\n')[0]
    assert 'not in the map' in check('root:\n  title: A\n  connectors: [{to: root/x}]\n')[0]
    assert 'own node' in check('root:\n  title: A\n  connectors: [{to: root}]\n')[0]
    assert check('root:\n  title: 2026\n')
    assert check('root:\n  title: A\n  colour: red\n')
    assert check('root:\n  title: A\n  children:\n    - title: B\n')
    assert 'control character' in check('root:\n  title: A\n  note: "$\\\\frac{1}{2}$"\n'.replace('\\\\', '\\'))[0]
    assert check('root: [\n')[0].startswith('not valid YAML')


def test_the_doc_lists_exactly_the_icons_the_editor_knows(mm):
    import re
    known = mm.page.evaluate('[...ICONS.keys()]')
    section = FORMAT_DOC.split('## Icons')[1].split('\n## ')[0]
    listed = re.findall(r'`([^`]+)` \(', section)
    assert listed == known


# Images: one PNG or JPEG per node, shown under the title, kept in the saved zip and in IndexedDB.

def make_image(path, size=(300, 150), fmt=None, colour=(40, 120, 200)):
    from PIL import Image
    Image.new('RGB', size, colour).save(path, fmt)
    return path


def image_size(data):
    import io
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        return im.size, im.format


def attach_image(mm, title, path):
    mm.node(title).click()
    with mm.page.expect_file_chooser() as fc:
        mm.menu('Image', '#bAttach')
    fc.value.set_files(str(path))
    mm.page.wait_for_function('!document.querySelector("#imageIn").dataset.busy')


def shown_image(mm, title):
    img = mm.node(title).locator('.pic img')
    img.wait_for()
    mm.page.wait_for_function('i => i.complete && i.naturalWidth > 0', arg=img.element_handle())
    return img


def zip_files(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def stored_images(mm):
    return mm.page.evaluate('''() => new Promise(ok => {
        const r = indexedDB.open('mindmap-editor-images');
        r.onsuccess = () => { const db = r.result;
          if (!db.objectStoreNames.contains('images')) { db.close(); return ok([]); }
          const q = db.transaction('images').objectStore('images').getAllKeys();
          q.onsuccess = () => { db.close(); ok(q.result); }; };
      })''')


def test_an_attached_image_is_shown_under_the_title(mm, tmp_path):
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'wide.png', (300, 150)))
    img = shown_image(mm, 'CRUDulator')
    box, title = img.bounding_box(), mm.node('CRUDulator').locator('.t').bounding_box()
    assert (round(box['width']), round(box['height'])) == (200, 100)     # fitted into 200 x 200, shape kept
    assert box['y'] >= title['y'] + title['height'] - 1


def test_a_small_image_is_shown_at_its_own_size(mm, tmp_path):
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'small.png', (80, 40)))
    box = shown_image(mm, 'CRUDulator').bounding_box()
    assert (round(box['width']), round(box['height'])) == (80, 40)


def test_the_image_menu_attaches_replaces_and_removes_with_undo(mm, tmp_path):
    mm.node('CRUDulator').click()
    mm.menu('Image')
    assert mm.page.is_disabled('#bRemoveImage')
    mm.page.keyboard.press('Escape')
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'a.png', colour=(255, 0, 0)))
    first = shown_image(mm, 'CRUDulator').get_attribute('src')
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'b.png', colour=(0, 255, 0)))
    assert shown_image(mm, 'CRUDulator').get_attribute('src') != first
    assert mm.page.locator('.pic').count() == 1
    mm.page.keyboard.press('Control+z')
    assert shown_image(mm, 'CRUDulator').get_attribute('src') == first
    mm.menu('Image', '#bRemoveImage')
    assert mm.node('CRUDulator').locator('.pic').count() == 0
    mm.page.keyboard.press('Control+z')
    assert shown_image(mm, 'CRUDulator').get_attribute('src') == first


def test_images_are_saved_in_the_zip_and_opened_again(mm, tmp_path):
    png = make_image(tmp_path / 'Ferry photo.png', (120, 90))
    attach_image(mm, 'CRUDulator', png)
    saved = mm.save(tmp_path / 'out')
    files = zip_files(saved)
    _, data = read_zip(saved)
    jsonschema.validate(data, SCHEMA)
    path = data['root']['children']['crudulator']['image']
    assert path.startswith('images/ferry_photo') and path.endswith('.png')
    assert files[path] == png.read_bytes()                  # small images are kept exactly as they were
    mm.new_map()
    mm.open(saved)
    assert shown_image(mm, 'CRUDulator').evaluate('i => [i.naturalWidth, i.naturalHeight]') == [120, 90]


def test_images_survive_a_reload(mm, tmp_path):
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'keep.jpg', (100, 100), 'JPEG'))
    mm.page.reload()
    mm.page.wait_for_selector('.node.root')
    shown_image(mm, 'CRUDulator')


def test_a_large_photo_is_shrunk_when_attached(mm, tmp_path):
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'big.jpg', (3000, 2000), 'JPEG'))
    _, data = read_zip(saved := mm.save(tmp_path / 'out'))
    path = data['root']['children']['crudulator']['image']
    assert path.endswith('.jpg')
    assert image_size(zip_files(saved)[path]) == ((1600, 1067), 'JPEG')


def test_a_large_png_stays_a_png(mm, tmp_path):
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'big.png', (1000, 2400)))
    _, data = read_zip(saved := mm.save(tmp_path / 'out'))
    path = data['root']['children']['crudulator']['image']
    assert image_size(zip_files(saved)[path]) == ((667, 1600), 'PNG')


def test_other_kinds_of_image_are_refused(mm, tmp_path):
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'anim.gif', (50, 50), 'GIF'))
    assert 'PNG and JPEG' in mm.message()
    assert mm.page.locator('.pic').count() == 0


def test_a_missing_image_shows_a_placeholder_and_keeps_its_reference(mm, tmp_path):
    mm.open(write_zip(tmp_path / 'm.zip', 'root:\n  title: M\n  children:\n    a: {title: A, image: images/gone.png}\n'))
    assert 'missing' in mm.message()
    assert mm.node('A').locator('.pic.missing').is_visible()
    _, data = read_zip(mm.save(tmp_path / 'out'))
    assert data['root']['children']['a']['image'] == 'images/gone.png'


def test_images_are_found_beside_a_yaml_file_in_a_folder(mm, tmp_path):
    from io import BytesIO
    from PIL import Image
    buf = BytesIO(); Image.new('RGB', (30, 20), (9, 9, 9)).save(buf, 'PNG')
    path = tmp_path / 'f.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('trip/map.yaml', 'root:\n  title: T\n  children:\n    a: {title: A, image: pics/x.png}\n')
        z.writestr('trip/pics/x.png', buf.getvalue())
    mm.open(path)
    shown_image(mm, 'A')


def _put_file_in_page(mm, path, mime):
    import base64
    return mm.page.evaluate_handle('''([b64, name, type]) => {
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const dt = new DataTransfer(); dt.items.add(new File([bytes], name, { type })); return dt; }''',
        [base64.b64encode(path.read_bytes()).decode(), path.name, mime])


def test_an_image_dropped_on_a_node_is_attached_to_it(mm, tmp_path):
    dt = _put_file_in_page(mm, make_image(tmp_path / 'drop.png', (60, 60)), 'image/png')
    mm.node('SQLite browser').dispatch_event('drop', {'dataTransfer': dt})
    shown_image(mm, 'SQLite browser')
    assert mm.page.locator('.node.sel .t').inner_text() == 'SQLite browser'


def test_a_pasted_image_is_attached_to_the_selected_node(mm, tmp_path):
    dt = _put_file_in_page(mm, make_image(tmp_path / 'paste.png', (60, 60)), 'image/png')
    mm.node('Mind map editor').click()
    mm.page.evaluate('dt => document.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }))', dt)
    shown_image(mm, 'Mind map editor')


def test_images_no_longer_used_are_cleared_from_the_browser_on_reload(mm, tmp_path):
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'old.png'))
    assert len(stored_images(mm)) == 1
    mm.new_map()
    mm.page.reload()
    mm.page.wait_for_selector('.node.root')
    mm.page.wait_for_function('window.imagesReady')
    assert stored_images(mm) == []


def test_the_doc_zip_checker_finds_missing_images(mm, tmp_path):
    space = {}
    exec(doc_blocks('python')[0][0], space)
    check_zip = lambda p: space['check_mind_map_zip'](p, SCHEMA)
    attach_image(mm, 'CRUDulator', make_image(tmp_path / 'ok.png', (40, 40)))
    saved = mm.save(tmp_path / 'out')
    assert check_zip(saved) == []
    gone = write_zip(tmp_path / 'gone.zip', 'root:\n  title: G\n  children:\n    a: {title: A, image: images/gone.png}\n')
    assert 'not in the zip' in check_zip(gone)[0]
    assert space['check_mind_map']('root:\n  title: A\n  image: ../x.png\n', SCHEMA)          # outside the zip
    assert space['check_mind_map']('root:\n  title: A\n  image: x.gif\n', SCHEMA)             # not PNG or JPEG


def test_an_image_path_outside_the_zip_is_refused(mm, tmp_path):
    before = mm.titles()
    mm.open(write_zip(tmp_path / 'bad.zip', 'root:\n  title: B\n  children:\n    a: {title: A, image: ../secret.png}\n'))
    assert 'not the path of a file in the zip' in mm.message()
    assert mm.titles() == before


def test_help_explains_images(mm):
    mm.page.click('#bHelp')
    section = mm.page.locator('#dlg section', has=mm.page.locator('h3', has_text='Images'))
    assert 'Attach image' in section.inner_text()


# Fitting the screen

FITS = '''() => { const r = s => document.querySelector(s).getBoundingClientRect();
  return [r('body').height, r('#vp').bottom, r('aside').bottom].every(v => v <= innerHeight + 0.5) }'''


def test_the_map_and_panel_fit_a_phone_turned_to_landscape(mm):
    mm.page.set_viewport_size({'width': 390, 'height': 844})
    mm.page.wait_for_timeout(200)
    assert mm.page.evaluate(FITS)
    mm.page.set_viewport_size({'width': 844, 'height': 390})
    mm.page.wait_for_timeout(200)
    assert mm.page.evaluate(FITS)
    root = mm.page.locator('.node.root').bounding_box()
    vp = mm.page.locator('#vp').bounding_box()
    assert vp['y'] <= root['y'] and root['y'] + root['height'] <= vp['y'] + vp['height']   # the root is still in view


EDITING = ['#bChild', '#bSib', '#bEdit', '#bFold', '#bUp', '#bDown', '#bConnect', '#bDel']


def tops(mm, *selectors):
    return {round(mm.page.locator(s).bounding_box()['y']) for s in selectors}


def test_on_a_phone_the_header_takes_two_short_rows(mm):
    mm.page.set_viewport_size({'width': 412, 'height': 915})
    mm.page.wait_for_timeout(200)
    assert not mm.page.locator('header h1').is_visible()
    assert len(tops(mm, '#mbFile', '#mbIcons', '#mbImage', '#bHelp', '#bUndo', '#bRedo')) == 1   # menus, Undo, Redo
    assert len(tops(mm, *EDITING)) == 1                                                          # editing commands
    assert mm.page.locator('header').bounding_box()['height'] <= 90


def test_on_a_narrow_phone_every_editing_button_can_be_reached(mm):
    mm.page.set_viewport_size({'width': 320, 'height': 700})
    mm.page.wait_for_timeout(200)
    mm.new_map()
    mm.node('New mind map').click()
    mm.page.click('#bChild')
    mm.page.keyboard.press('Enter')
    assert len(mm.titles()) == 2
    mm.page.click('#bDel')                 # scrolled into view if the row is wider than the screen
    assert len(mm.titles()) == 1
    assert mm.page.evaluate('document.documentElement.scrollWidth <= innerWidth')   # the page doesn't scroll sideways


def test_on_a_phone_in_landscape_the_header_is_one_row(mm):
    mm.page.set_viewport_size({'width': 915, 'height': 412})
    mm.page.wait_for_timeout(200)
    assert not mm.page.locator('header h1').is_visible()
    assert len(tops(mm, '#mbFile', '#bChild', '#bDel', '#bRedo')) == 1


def test_on_a_desktop_the_title_is_shown(mm):
    mm.page.set_viewport_size({'width': 1280, 'height': 720})
    assert mm.page.locator('header h1').is_visible()


# Exporting as linked Markdown files

TRIP = '''
root:
  title: Holiday
  note: |
    A week in **June**.
  children:
    travel:
      title: Travel
      icons: [full-1, idea]
      link: https://www.stenaline.co.uk
      note: |
        Book the **night ferry**.

        $$C = n \\times (h + f)$$
      connectors:
        - to: root/places/utrecht
          label: then by train
        - to: root
      children:
        ferry:
          title: Ferry
          image: images/ferry.png
        trains:
          title: Trains
    places:
      title: Places
      children:
        utrecht:
          title: Utrecht
'''


def export_markdown(mm, folder):
    with mm.page.expect_download() as d:
        mm.menu('File', '#bExportMd')
    path = Path(folder) / d.value.suggested_filename
    d.value.save_as(path)
    return path


def markdown_files(path):
    """The exported zip's files (not folders), text for Markdown and bytes for the rest."""
    with zipfile.ZipFile(path) as z:
        return {n: (z.read(n).decode('utf-8') if n.endswith('.md') else z.read(n))
                for n in z.namelist() if not n.endswith('/')}


def open_trip(mm, tmp_path, image=True):
    path = tmp_path / 'trip.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('trip.yaml', TRIP)
        if image:
            z.write(make_image(tmp_path / 'ferry.png', (60, 40)), 'images/ferry.png')
    mm.open(path)
    assert 'Opened' in mm.message()


def test_export_gives_a_zip_with_one_markdown_file_per_node_in_folders_like_the_tree(mm, tmp_path):
    path = export_markdown(mm, tmp_path)
    assert path.name == 'toolbox_markdown.zip'
    files = markdown_files(path)
    assert len(files) == mm.page.evaluate('allNodes().length')
    assert all(name.startswith('toolbox/') and name.endswith('/index.md') or name == 'toolbox/index.md' for name in files)
    assert 'toolbox/crudulator/index.md' in files
    assert files['toolbox/index.md'].startswith('# Toolbox\n')
    assert '\nBrowser-based tools' in files['toolbox/index.md']
    assert 'Exported toolbox_markdown.zip' in mm.message()


def test_each_file_has_the_node_and_links_to_its_children_connectors_and_parent(mm, tmp_path):
    open_trip(mm, tmp_path)
    files = markdown_files(export_markdown(mm, tmp_path))
    assert files['holiday/travel/index.md'] == '''# 1️⃣ 💡 Travel

🔗 <https://www.stenaline.co.uk>

Book the **night ferry**.

$$C = n \\times (h + f)$$

## Contents

- [Ferry](ferry/index.md)
- [Trains](trains/index.md)

## See also

- [Utrecht](../places/utrecht/index.md): then by train
- [Holiday](../index.md)

---

Up: [Holiday](../index.md) · Next: [Places](../places/index.md)
'''
    assert files['holiday/index.md'] == '''# Holiday

A week in **June**.

## Contents

- [Travel](travel/index.md)
- [Places](places/index.md)
'''


def test_images_go_in_the_zip_and_are_shown_from_their_node(mm, tmp_path):
    open_trip(mm, tmp_path)
    files = markdown_files(export_markdown(mm, tmp_path))
    assert files['holiday/images/ferry.png'] == (tmp_path / 'ferry.png').read_bytes()
    assert files['holiday/travel/ferry/index.md'].startswith('# Ferry\n\n![Ferry](../../images/ferry.png)\n')


def test_every_relative_link_in_the_export_names_a_file_in_it(mm, tmp_path):
    import posixpath
    import re
    open_trip(mm, tmp_path)
    files = markdown_files(export_markdown(mm, tmp_path))
    targets = 0
    for name, text in files.items():
        if not name.endswith('.md'):
            continue
        for target in re.findall(r'\]\(([^)]+)\)', text):
            targets += 1
            assert posixpath.normpath(posixpath.join(posixpath.dirname(name), target)) in files, (name, target)
    assert targets == 17


def test_pages_link_to_the_previous_and_next_sibling(mm, tmp_path):
    open_trip(mm, tmp_path)
    files = markdown_files(export_markdown(mm, tmp_path))
    assert files['holiday/travel/trains/index.md'].endswith(
        '\n---\n\nPrevious: [Ferry](../ferry/index.md) · Up: [Travel](../index.md)\n')
    assert files['holiday/places/utrecht/index.md'].endswith('\n---\n\nUp: [Places](../index.md)\n')


def test_a_missing_image_is_left_out_and_reported(mm, tmp_path):
    open_trip(mm, tmp_path, image=False)
    files = markdown_files(export_markdown(mm, tmp_path))
    assert files['holiday/travel/ferry/index.md'] == '# Ferry\n\n---\n\nUp: [Travel](../index.md) · Next: [Trains](../trains/index.md)\n'
    assert not any(name.endswith('.png') for name in files)
    assert '1 image missing' in mm.message()


def test_titles_are_kept_as_plain_text(mm, tmp_path):
    mm.new_map()
    mm.page.dblclick('.node.root .t')
    mm.page.keyboard.press('Control+a')
    mm.page.keyboard.type('*Rob\'s* [list] costs $5 and $10')
    mm.page.keyboard.press('Enter')
    files = markdown_files(export_markdown(mm, tmp_path))
    assert list(files) == ['rob_s_list_costs_5_and_10/index.md']
    assert files['rob_s_list_costs_5_and_10/index.md'] == "# \\*Rob's\\* \\[list\\] costs \\$5 and \\$10\n"


def test_help_explains_markdown_export(mm):
    mm.page.click('#bHelp')
    section = mm.page.locator('#dlg section', has=mm.page.locator('h3', has_text='Saving'))
    assert 'Export as Markdown' in section.inner_text()
