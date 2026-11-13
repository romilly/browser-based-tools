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
