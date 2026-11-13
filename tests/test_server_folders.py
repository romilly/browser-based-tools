"""Folders on the server (mindmap_server.py): maps and diagrams kept in folders, moved and deleted."""
import json

import pytest

from test_diagram_server import GARDEN
from test_mindmap_server import call, maps, zip_bytes  # noqa: F401 (maps is a fixture)

KINDS = [('maps', 'zip', zip_bytes()), ('diagrams', 'yaml', GARDEN.encode())]


@pytest.fixture(params=KINDS, ids=['maps', 'diagrams'])
def kind(request, maps):
    """One kind of file on a running server: its API (base URL), folder, extension and a valid body."""
    name, ext, body = request.param
    base, folder = maps

    class Kind:
        api = f'{base}/api/{name}'
        root = folder if name == 'maps' else folder / 'diagrams'

        def put(self, path, headers=None):
            return call(f'{self.api}/{path}.{ext}', 'PUT', body, headers)

        def file(self, path):
            return self.root / f'{path}.{ext}'

        def listing(self, folder=''):
            status, _, got = call(f'{self.api}/{folder}/' if folder else f'{self.api}/')
            assert status == 200
            got = json.loads(got)
            return got['folders'], [f['name'] for f in got['files']]

        def move(self, path, to, folder=False):
            data = json.dumps({'to': to}).encode()
            return call(f'{self.api}/{path}/' if folder else f'{self.api}/{path}.{ext}', 'POST', data)[0]

        def delete(self, path, headers=None):
            return call(f'{self.api}/{path}.{ext}', 'DELETE', headers=headers)[0]

        def trash(self):
            bin_ = self.root / '.trash'
            return sorted(f.relative_to(bin_).as_posix() for f in bin_.rglob('*') if f.is_file())

    Kind.ext, Kind.body = ext, body
    return Kind()


def test_a_file_saved_with_a_path_is_kept_in_folders_and_read_back(kind):
    status, headers, _ = kind.put('projects/toolbox/plan')
    assert status == 200
    assert kind.file('projects/toolbox/plan').read_bytes() == kind.body
    status, got, body = call(f'{kind.api}/projects/toolbox/plan.{kind.ext}')
    assert status == 200 and body == kind.body and got['ETag'] == headers['ETag']


def test_a_folder_lists_its_folders_and_its_own_files(kind):
    kind.put('garden')
    kind.put('projects/plan')
    kind.put('projects/toolbox/server')
    assert kind.listing() == (['projects'], ['garden'])
    assert kind.listing('projects') == (['toolbox'], ['projects/plan'])
    assert kind.listing('projects/toolbox') == ([], ['projects/toolbox/server'])


def test_the_plain_list_still_has_only_the_files_at_the_top(kind):
    kind.put('garden')
    kind.put('projects/plan')
    assert [f['name'] for f in json.loads(call(kind.api)[2])] == ['garden']


def test_a_folder_that_is_not_there_lists_nothing(kind):
    assert kind.listing('nowhere/at_all') == ([], [])
    assert not (kind.root / 'nowhere').exists()


def test_folders_holding_no_files_of_this_kind_are_not_listed(kind):
    kind.put('garden')
    (kind.root / 'empty').mkdir()
    (kind.root / 'notes').mkdir()
    (kind.root / 'notes' / 'readme.txt').write_text('hello')
    (kind.root / 'Bad Name').mkdir()
    (kind.root / 'Bad Name' / f'x.{kind.ext}').write_bytes(kind.body)
    assert kind.listing() == ([], ['garden'])


@pytest.mark.parametrize('path', ['../escape', 'a/../escape', 'a//b', '/a', 'a/', 'A/b', 'a/.hidden', '.trash/a'])
def test_paths_that_are_not_keys_are_refused(kind, path):
    assert kind.put(path)[0] in (400, 404)
    assert not any(kind.root.parent.parent.rglob('escape.*')) and not any(kind.root.rglob('*.' + kind.ext))


def test_the_diagrams_folder_inside_the_maps_is_not_a_folder_of_maps(maps):
    base, folder = maps
    call(f'{base}/api/diagrams/sub/garden.yaml', 'PUT', GARDEN.encode())
    assert call(f'{base}/api/maps/diagrams/garden.zip', 'PUT', zip_bytes())[0] == 404
    assert call(f'{base}/api/maps/diagrams/sub/garden.zip', 'PUT', zip_bytes())[0] == 404
    call(f'{base}/api/maps/garden.zip', 'PUT', zip_bytes())
    data = json.dumps({'to': 'diagrams/garden'}).encode()
    assert call(f'{base}/api/maps/garden.zip', 'POST', data)[0] == 400
    (folder / 'diagrams' / 'stray.zip').write_bytes(zip_bytes())
    assert json.loads(call(f'{base}/api/maps/')[2])['folders'] == []
    assert call(f'{base}/api/maps/diagrams/')[0] == 404


# --- delete ---

def test_a_deleted_file_goes_to_the_trash_and_is_no_longer_listed(kind):
    kind.put('garden')
    assert kind.delete('garden') == 200
    assert kind.listing() == ([], []) and not kind.file('garden').exists()
    assert call(f'{kind.api}/garden.{kind.ext}')[0] == 404
    [kept] = kind.trash()
    assert kept.startswith('garden.') and kept.endswith('.' + kind.ext)
    assert (kind.root / '.trash' / kept).read_bytes() == kind.body


def test_deleting_the_same_name_twice_keeps_both_in_the_trash(kind):
    for _ in range(2):
        kind.put('projects/garden')
        assert kind.delete('projects/garden') == 200
    assert len(kind.trash()) == 2 and all(t.startswith('projects/garden.') for t in kind.trash())


def test_deleting_the_last_file_in_a_folder_removes_the_folder(kind):
    kind.put('projects/toolbox/plan')
    kind.put('projects/garden')
    kind.delete('projects/toolbox/plan')
    assert not (kind.root / 'projects' / 'toolbox').exists() and kind.listing('projects') == ([], ['projects/garden'])
    kind.delete('projects/garden')
    assert kind.listing() == ([], []) and not (kind.root / 'projects').exists() and kind.root.is_dir()


def test_deleting_a_file_that_is_not_there_or_has_changed_is_refused(kind):
    assert kind.delete('garden') == 404
    tag = kind.put('garden')[1]['ETag']
    assert kind.delete('garden', {'If-Match': '"something else"'}) == 409 and kind.file('garden').exists()
    assert kind.delete('garden', {'If-Match': tag}) == 200


# --- move ---

def test_a_file_can_be_renamed_and_moved_into_a_new_folder(kind):
    kind.put('garden')
    assert kind.move('garden', 'allotment') == 200
    assert kind.listing() == ([], ['allotment'])
    assert kind.move('allotment', 'outdoors/plots/allotment') == 200
    assert kind.listing() == (['outdoors'], []) and kind.listing('outdoors/plots') == ([], ['outdoors/plots/allotment'])
    assert kind.file('outdoors/plots/allotment').read_bytes() == kind.body


def test_moving_the_last_file_out_of_a_folder_removes_the_folder(kind):
    kind.put('projects/toolbox/plan')
    assert kind.move('projects/toolbox/plan', 'plan') == 200
    assert kind.listing() == ([], ['plan']) and not (kind.root / 'projects').exists()


def test_a_move_never_replaces_a_file(kind):
    kind.put('garden')
    kind.put('projects/garden')
    assert kind.move('garden', 'projects/garden') == 409
    assert kind.listing() == (['projects'], ['garden'])


def test_a_move_needs_a_file_that_is_there_and_a_name_that_is_a_path_of_keys(kind):
    assert kind.move('garden', 'allotment') == 404
    kind.put('garden')
    for bad in ['../escape', 'Allotment', 'a//b', '', 'a/', '.trash/x', 7, None]:
        assert kind.move('garden', bad) == 400
    assert call(f'{kind.api}/garden.{kind.ext}', 'POST', b'not json')[0] == 400
    assert kind.listing() == ([], ['garden']) and not any(kind.root.parent.parent.rglob('escape.*'))


def test_a_folder_can_be_renamed_and_moved_with_everything_in_it(kind):
    kind.put('projects/plan')
    kind.put('projects/toolbox/server')
    assert kind.move('projects', 'work', folder=True) == 200
    assert kind.listing() == (['work'], []) and kind.listing('work') == (['toolbox'], ['work/plan'])
    assert kind.move('work/toolbox', 'archive/2026/toolbox', folder=True) == 200
    assert kind.listing('archive/2026/toolbox') == ([], ['archive/2026/toolbox/server'])
    assert kind.listing('work') == ([], ['work/plan'])


def test_a_folder_move_is_refused_into_itself_onto_another_or_when_it_is_not_there(kind):
    kind.put('projects/plan')
    kind.put('work/plan')
    assert kind.move('projects', 'projects/inside', folder=True) == 400
    assert kind.move('projects', 'projects', folder=True) == 400
    assert kind.move('projects', 'work', folder=True) == 409
    assert kind.move('nowhere', 'somewhere', folder=True) == 404
    assert call(f'{kind.api}/', 'POST', json.dumps({'to': 'x'}).encode())[0] == 404
    assert kind.listing() == (['projects', 'work'], [])


# --- the editors: one dialog walks the folders, and opens, saves, moves and deletes ---

from conftest import LOCAL_LIBS, _use_local_libs  # noqa: E402
from test_diagram import Diagram  # noqa: E402
from test_mindmap import MindMap  # noqa: E402

EDITORS = {
    'mind map': dict(api='maps', ext='zip', body=zip_bytes(), path='', param='map', dlg='#serverMaps', attr='map',
                     helper=MindMap, fresh='new_mind_map'),
    'diagram': dict(api='diagrams', ext='yaml', body=GARDEN.encode(), path='diagram-editor.html', param='diagram',
                    dlg='#serverFiles', attr='name', helper=Diagram, fresh='new_diagram'),
}


class Editor:
    """An editor opened from the server, and the folder its files are kept in."""

    def __init__(self, page, maps, e):
        self.__dict__.update(e)
        self.page, (self.base, folder) = page, maps
        self.root = folder if self.api == 'maps' else folder / 'diagrams'
        self.app = self.helper(page, f'{self.base}/{self.path}')
        self.answers, self.asked = [], []
        page.on('dialog', self._answer)

    def _answer(self, d):
        self.asked.append(d.message)
        answer = self.answers.pop(0) if self.answers else None
        d.dismiss() if answer is None else d.accept(answer) if d.type == 'prompt' else d.accept()

    def put(self, *paths):
        for path in paths:
            assert call(f'{self.base}/api/{self.api}/{path}.{self.ext}', 'PUT', self.body)[0] == 200

    def has(self, path):
        return (self.root / f'{path}.{self.ext}').is_file()

    def url(self, path=None):
        return f'{self.base}/{self.path}' + (f'?{self.param}={path}' if path else '')

    def toast(self, text):
        self.page.wait_for_function('t => document.querySelector("#toast").innerText.includes(t)', arg=text)

    def browse(self):
        self.app.menu('File', '#bServerOpen')
        self.page.wait_for_selector(self.dlg + '[open]')

    def save_as(self):
        self.app.menu('File', '#bServerSave')
        self.page.wait_for_selector(self.dlg + '[open]')

    def new(self):
        self.app.menu('File', '#bNew')

    def enter(self, folder):
        self.page.click(f'#serverList button[data-folder="{folder}"]')
        self.shows_folder(folder)

    def up(self, folder):
        self.page.click(f'#serverPath button[data-folder="{folder}"]')
        self.shows_folder(folder)

    def shows_folder(self, folder):
        self.page.wait_for_function('f => serverFolder === f && document.querySelector("#serverPath").innerText.replace(/\\s/g, "").endsWith(f)', arg=folder)

    def listed(self):
        """(folders, files) in the dialog, by the names shown."""
        return (self.page.locator('#serverList button.sfolder').all_inner_texts(),
                self.page.locator(f'#serverList button[data-{self.attr}]').evaluate_all('bs => bs.map(b => b.firstChild.textContent)'))

    def file(self, path):
        return f'#serverList button[data-{self.attr}="{path}"]'

    def open(self, path):
        self.page.click(self.file(path))
        self.toast(f'Opened {path.split("/")[-1]}')

    def name(self, text):
        self.page.fill('#serverNameIn', text)
        self.page.click('#serverGo')


@pytest.fixture(params=list(EDITORS), ids=list(EDITORS))
def ed(request, page, maps):
    if LOCAL_LIBS:
        _use_local_libs(page)
    e = Editor(page, maps, EDITORS[request.param])
    e.app.load()
    page.wait_for_selector('#bServerSave:not([hidden])', state='attached')
    e.new()                                                                         # the mind map editor starts with a sample
    yield e
    assert not e.app.errors, f'JavaScript errors on the page: {e.app.errors}'


def test_the_dialog_shows_folders_and_opens_a_file_inside_one(ed):
    ed.put('garden', 'projects/plan', 'projects/toolbox/server')
    ed.browse()
    assert ed.listed() == (['projects/'], ['garden'])
    ed.enter('projects')
    assert ed.listed() == (['toolbox/'], ['plan'])
    ed.enter('projects/toolbox')
    assert ed.listed() == ([], ['server'])
    ed.open('projects/toolbox/server')
    assert ed.page.url == ed.url('projects/toolbox/server')
    assert not ed.page.locator(ed.dlg + '[open]').count()


def test_the_path_at_the_top_leads_back_up(ed):
    ed.put('garden', 'projects/toolbox/server')
    ed.browse()
    ed.enter('projects')
    ed.enter('projects/toolbox')
    assert ed.page.locator('#serverPath button').all_inner_texts()[1:] == ['projects', 'toolbox']
    ed.up('projects')
    assert ed.listed() == (['toolbox/'], [])
    ed.up('')
    assert ed.listed() == (['projects/'], ['garden'])


def test_the_dialog_opens_where_it_was_left(ed):
    ed.put('projects/plan')
    ed.browse()
    ed.enter('projects')
    ed.page.keyboard.press('Escape')
    ed.browse()
    assert ed.listed() == ([], ['plan'])


def test_a_link_with_folders_opens_the_file_and_ctrl_s_saves_it_back_there(ed):
    ed.put('projects/toolbox/server')
    before = (ed.root / 'projects' / 'toolbox' / f'server.{ed.ext}').stat().st_mtime_ns
    ed.page.goto(ed.url('projects/toolbox/server'))
    ed.toast('Opened server')
    ed.page.keyboard.press('Control+s')
    ed.toast('Saved projects/toolbox/server to the server')
    assert (ed.root / 'projects' / 'toolbox' / f'server.{ed.ext}').stat().st_mtime_ns > before
    assert ed.page.url == ed.url('projects/toolbox/server') and not ed.asked


def test_a_new_file_is_saved_in_the_folder_and_under_the_name_chosen(ed):
    ed.put('projects/plan')
    ed.save_as()
    assert ed.page.input_value('#serverNameIn') == ed.fresh
    assert ed.page.inner_text(ed.dlg + ' h2') == 'Save to server' and ed.page.inner_text('#serverGo') == 'Save here'
    assert ed.page.locator('#serverList button[aria-label="Move the folder projects"]').count() == 1   # Move while saving too
    ed.enter('projects')
    ed.name('My Plan 2')
    ed.toast('Saved projects/my_plan_2 to the server')
    assert ed.has('projects/my_plan_2') and ed.page.url == ed.url('projects/my_plan_2')
    assert not ed.page.locator(ed.dlg + '[open]').count()


def test_a_new_folder_is_made_by_saving_into_it(ed):
    ed.save_as()
    ed.answers.append('Work 2026')
    ed.page.click('#serverNewFolder')
    ed.shows_folder('work_2026')
    assert 'Nothing here yet' in ed.page.inner_text('#serverList') and not (ed.root / 'work_2026').exists()
    ed.page.click('#serverGo')
    ed.toast(f'Saved work_2026/{ed.fresh} to the server')
    assert ed.has(f'work_2026/{ed.fresh}')


def test_a_new_file_is_offered_the_folder_of_the_one_opened_before(ed):
    ed.put('projects/plan')
    ed.browse()
    ed.enter('projects')
    ed.open('projects/plan')
    ed.new()
    ed.save_as()
    ed.shows_folder('projects')
    ed.page.click('#serverGo')
    ed.toast(f'Saved projects/{ed.fresh} to the server')


def test_picking_a_file_while_saving_takes_its_name_and_asks_before_replacing_it(ed):
    ed.put('projects/plan')
    ed.save_as()
    ed.enter('projects')
    ed.page.click(ed.file('projects/plan'))
    assert ed.page.input_value('#serverNameIn') == 'plan'
    ed.page.click('#serverGo')
    ed.toast('Not saved')
    assert 'already' in ed.asked[0] and ed.page.locator(ed.dlg + '[open]').count()
    ed.answers.append('yes')
    ed.page.click('#serverGo')
    ed.toast('Saved projects/plan to the server')


def test_a_name_with_no_letters_or_digits_is_refused(ed):
    ed.save_as()
    ed.name('???')
    ed.toast('Give it a name')
    assert not any(ed.root.rglob('*.' + ed.ext))


def test_delete_asks_then_moves_the_file_to_the_trash(ed):
    ed.put('projects/plan', 'projects/notes')
    ed.browse()
    ed.enter('projects')
    ed.page.click('#serverList button[aria-label="Delete plan"]')
    assert ed.has('projects/plan') and 'Delete projects/plan' in ed.asked[0]      # not confirmed: nothing happens
    ed.answers.append('yes')
    ed.page.click('#serverList button[aria-label="Delete plan"]')
    ed.toast('Deleted projects/plan')
    ed.page.wait_for_selector(ed.file('projects/plan'), state='detached')
    assert ed.listed() == ([], ['notes']) and not ed.has('projects/plan')
    assert [f.name.split('.')[0] for f in (ed.root / '.trash' / 'projects').iterdir()] == ['plan']


def test_deleting_the_last_file_in_a_folder_goes_back_to_the_top(ed):
    ed.put('garden', 'projects/plan')
    ed.browse()
    ed.enter('projects')
    ed.answers.append('yes')
    ed.page.click('#serverList button[aria-label="Delete plan"]')
    ed.shows_folder('')
    ed.page.wait_for_selector(ed.file('garden'))
    assert ed.listed() == ([], ['garden'])


def test_deleting_the_file_that_is_open_unlinks_it(ed):
    ed.put('garden')
    ed.browse()
    ed.open('garden')
    ed.browse()
    ed.answers.append('yes')
    ed.page.click('#serverList button[aria-label="Delete garden"]')
    ed.toast('Deleted garden')
    assert ed.page.url == ed.url()
    ed.page.keyboard.press('Escape')
    ed.save_as()                                                                    # so saving asks where it goes again
    assert ed.page.inner_text(ed.dlg + ' h2') == 'Save to server'


def test_move_puts_a_file_in_the_folder_walked_to(ed):
    ed.put('garden', 'projects/plan')
    ed.browse()
    ed.page.click('#serverList button[aria-label="Move garden"]')
    ed.page.wait_for_selector('#serverName:not([hidden])')
    assert ed.page.inner_text(ed.dlg + ' h2') == 'Move garden' and ed.page.inner_text('#serverGo') == 'Move here'
    assert ed.page.input_value('#serverNameIn') == 'garden'
    ed.enter('projects')
    ed.page.click('#serverGo')
    ed.toast('Moved garden to projects/garden')
    assert ed.has('projects/garden') and not ed.has('garden')
    ed.page.wait_for_selector('#serverName', state='hidden')                        # back to opening, in that folder
    ed.page.wait_for_selector(ed.file('projects/garden'))
    assert ed.page.inner_text(ed.dlg + ' h2') == 'Open from server' and sorted(ed.listed()[1]) == ['garden', 'plan']


def test_move_renames_and_can_make_a_new_folder(ed):
    ed.put('garden')
    ed.browse()
    ed.page.click('#serverList button[aria-label="Move garden"]')
    ed.answers.append('Outdoors')
    ed.page.click('#serverNewFolder')
    ed.shows_folder('outdoors')
    ed.name('Allotment')
    ed.toast('Moved garden to outdoors/allotment')
    assert ed.has('outdoors/allotment') and not ed.has('garden')


def test_a_move_onto_a_name_already_there_is_refused(ed):
    ed.put('garden', 'projects/garden')
    ed.browse()
    ed.page.click('#serverList button[aria-label="Move garden"]')
    ed.page.click('#serverGo')
    ed.toast('garden is already here')
    ed.enter('projects')
    ed.page.click('#serverGo')
    ed.toast('Not moved: projects/garden is already on the server')
    assert ed.has('garden') and ed.page.locator(ed.dlg + '[open]').count()


def test_moving_the_file_that_is_open_keeps_it_linked(ed):
    ed.put('garden')
    ed.browse()
    ed.open('garden')
    ed.browse()
    ed.page.click('#serverList button[aria-label="Move garden"]')
    ed.name('allotment')
    ed.toast('Moved garden to allotment')
    assert ed.page.url == ed.url('allotment')
    ed.page.keyboard.press('Escape')
    ed.page.keyboard.press('Control+s')
    ed.toast('Saved allotment to the server')
    assert ed.has('allotment') and not ed.has('garden') and not ed.asked


def test_a_folder_is_renamed_and_moved_with_everything_in_it(ed):
    ed.put('projects/plan', 'projects/toolbox/server', 'archive/old')
    ed.browse()
    ed.enter('projects')
    ed.open('projects/plan')
    ed.browse()
    ed.up('')
    ed.page.click('#serverList button[aria-label="Move the folder projects"]')
    ed.page.wait_for_selector('#serverList button[data-folder="projects"]', state='detached')
    assert ed.listed()[0] == ['archive/']                                           # it can't go inside itself
    ed.enter('archive')
    ed.name('Work')
    ed.toast('Moved projects to archive/work')
    assert ed.has('archive/work/plan') and ed.has('archive/work/toolbox/server') and not (ed.root / 'projects').exists()
    assert ed.page.url == ed.url('archive/work/plan')                               # the open file moved with it
    ed.page.wait_for_selector('#serverList button[data-folder="archive/work"]')
    assert ed.listed() == (['work/'], ['old'])


def test_a_server_from_before_folders_says_so(ed):
    ed.page.route(f'**/api/{ed.api}/', lambda r: r.fulfill(status=404, body='{}', content_type='application/json'))
    ed.app.menu('File', '#bServerOpen')
    ed.toast('older than this editor')
    assert not ed.page.locator(ed.dlg + '[open]').count()


def test_move_and_delete_are_offered_while_saving_and_saving_carries_on(ed):
    ed.put('projects/plan', 'projects/old')
    ed.save_as()
    ed.enter('projects')
    ed.page.fill('#serverNameIn', 'Kept Name')
    ed.answers.append('yes')
    ed.page.click('#serverList button[aria-label="Delete old"]')
    ed.toast('Deleted projects/old')
    ed.page.wait_for_selector(ed.file('projects/old'), state='detached')
    assert ed.page.inner_text(ed.dlg + ' h2') == 'Save to server' and ed.page.input_value('#serverNameIn') == 'Kept Name'
    ed.page.click('#serverList button[aria-label="Move plan"]')
    ed.page.wait_for_function('document.querySelector("#serverGo").textContent === "Move here"')
    ed.page.wait_for_selector('#serverList .smini', state='detached')                # none while choosing where a move goes
    ed.name('Plan 2026')
    ed.toast('Moved projects/plan to projects/plan_2026')
    ed.page.wait_for_function('document.querySelector("#serverGo").textContent === "Save here"')
    assert ed.page.inner_text(ed.dlg + ' h2') == 'Save to server' and ed.page.input_value('#serverNameIn') == 'Kept Name'
    ed.page.click('#serverGo')
    ed.toast('Saved projects/kept_name to the server')
    assert ed.has('projects/kept_name') and ed.has('projects/plan_2026') and not ed.has('projects/plan')


def test_cancel_during_a_move_goes_back_to_what_you_were_doing(ed):
    ed.put('garden')
    ed.save_as()
    ed.page.click('#serverList button[aria-label="Move garden"]')
    ed.page.wait_for_function('document.querySelector("#serverGo").textContent === "Move here"')
    ed.page.click('#serverCancel')
    ed.page.wait_for_function('document.querySelector("#serverGo").textContent === "Save here"')
    assert ed.page.locator(ed.dlg + '[open]').count() and ed.page.input_value('#serverNameIn') == ed.fresh
    ed.page.click('#serverCancel')
    assert not ed.page.locator(ed.dlg + '[open]').count() and ed.has('garden')
