"""The diagram format (diagram-schema.json) and opening and saving diagrams as YAML in diagram-editor.html."""
import copy
import itertools
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from conftest import LOCAL_LIBS, ROOT, _use_local_libs

SCHEMA = json.loads((ROOT / 'diagram-schema.json').read_text())
EXAMPLES = ROOT / 'diagram-editor' / 'examples'
DATA_FLOW = EXAMPLES / 'mind_map_data_flow.yaml'      # every node has a layout
FLOWCHART = EXAMPLES / 'opening_a_file.yaml'          # no layout at all
EXAMPLE_FILES = sorted(EXAMPLES.glob('*.yaml'))

SMALL = '''diagram:
  title: Small
  nodes:
    a:
      label: A
      outputs:
        out1: {}
    b:
      label: B
      inputs:
        in1: {}
  edges:
    - {from: a.out1, to: b.in1}
'''


def edge_problems(data):
    """The edge ends that don't name a port: 'from' must be an output and 'to' an input (the schema can't check this)."""
    nodes = data['diagram'].get('nodes', {})

    def missing(end, ports):
        node, port = end.split('.')
        return port not in nodes.get(node, {}).get(ports, {})

    return [end for e in data['diagram'].get('edges', [])
            for end, ports in ((e['from'], 'outputs'), (e['to'], 'inputs')) if missing(end, ports)]


def without_layout(data):
    """A copy of a diagram with every layout block (on nodes, ports and edges) removed: what a code generator reads."""
    if isinstance(data, dict):
        return {k: without_layout(v) for k, v in data.items() if k != 'layout'}
    if isinstance(data, list):
        return [without_layout(v) for v in data]
    return data


# --- the format: these need no editor ---

def test_the_schema_is_a_valid_schema():
    jsonschema.Draft7Validator.check_schema(SCHEMA)


def test_the_schema_examples_are_valid():
    assert len(SCHEMA['examples']) == 2
    for example in SCHEMA['examples']:
        jsonschema.validate(example, SCHEMA)
        assert edge_problems(example) == []


@pytest.mark.parametrize('path', EXAMPLE_FILES, ids=lambda p: p.name)
def test_the_example_diagrams_are_valid(path):
    data = yaml.safe_load(path.read_text())
    jsonschema.validate(data, SCHEMA)
    assert edge_problems(data) == []


def test_the_examples_cover_a_data_flow_with_layout_and_a_flowchart_without():
    flow, chart = (yaml.safe_load(p.read_text())['diagram'] for p in (DATA_FLOW, FLOWCHART))
    assert flow['kind'] == 'dataflow' and all('layout' in n for n in flow['nodes'].values())
    assert chart['kind'] == 'flowchart' and without_layout(chart) == chart
    assert list(chart['nodes']['is_zip']['outputs']) == ['yes', 'no']       # quoted in the file, so not booleans


@pytest.mark.parametrize('change, problem', [
    (lambda d: d.pop('title'), "'title' is a required property"),
    (lambda d: d.update(title=2026), 'is not of type'),
    (lambda d: d.update(nodes=[{'label': 'A'}]), 'is not of type'),                    # nodes are a mapping, not a list
    (lambda d: d['nodes']['a'].update(colour='red'), 'Additional properties'),
    (lambda d: d['nodes']['a'].update(label=1), 'is not of type'),
    (lambda d: d['nodes']['a'].update(outputs=['out1']), 'is not of type'),            # ports are a mapping too
    (lambda d: d['nodes'].update({'no spaces': {}}), 'does not match'),
    (lambda d: d['nodes']['a']['outputs'].update({'out-1': {}}), 'does not match'),
    (lambda d: d['nodes']['a']['outputs']['out1'].update(layout={'side': 'middle'}), 'is not one of'),
    (lambda d: d['nodes']['a']['outputs']['out1'].update(layout={'at': 1.5}), 'greater than the maximum'),
    (lambda d: d['nodes']['a'].update(layout={'x': 10}), "'y' is a required property"),
    (lambda d: d['nodes']['a'].update(layout={'x': 0, 'y': 0, 'w': 0}), 'less than or equal to the minimum'),
    (lambda d: d['nodes']['a'].update(image='../secret.png'), 'does not match'),
    (lambda d: d['edges'][0].update({'from': 'a'}), 'does not match'),                 # an edge end names a port
    (lambda d: d['edges'][0].pop('to'), "'to' is a required property"),
    (lambda d: d['edges'][0].update(layout={'curve': [[1, 2]]}), 'too short'),
    (lambda d: d['edges'][0].update(colour='red'), 'Additional properties'),
])
def test_the_schema_rejects_mistakes(change, problem):
    data = yaml.safe_load(SMALL)
    jsonschema.validate(data, SCHEMA)
    change(data['diagram'])
    messages = [e.message for e in jsonschema.Draft7Validator(SCHEMA).iter_errors(data)]
    assert any(problem in m for m in messages), messages


def test_layout_can_be_left_out_of_everything():
    """A program that generates or reads diagrams can ignore layout completely."""
    for path in EXAMPLE_FILES:
        data = without_layout(yaml.safe_load(path.read_text()))
        jsonschema.validate(data, SCHEMA)
        assert edge_problems(data) == []


# --- the editor ---

class Diagram:
    """Drives diagram-editor.html."""

    def __init__(self, page, url):
        self.page, self.url = page, url
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))

    def load(self):
        response = self.page.goto(self.url)
        assert response.ok, f'{self.url} gave {response.status}: diagram-editor.html is not written yet'
        self.page.wait_for_selector('#canvas')

    def title(self):
        return self.page.input_value('#title')

    def node(self, node_id):
        return self.page.locator(f'#canvas g.node[data-id="{node_id}"]')

    def nodes(self):
        return self.page.locator('#canvas g.node').evaluate_all('es => es.map(e => e.dataset.id)')

    def label(self, node_id):
        return self.node(node_id).locator('.label').text_content()

    def ports(self, node_id, direction):
        """Names of a node's ports; direction is 'in' or 'out'."""
        return self.node(node_id).locator(f'.port[data-dir="{direction}"]').evaluate_all('es => es.map(e => e.dataset.port)')

    def edges(self):
        return self.page.locator('#canvas path.edge').evaluate_all('es => es.map(e => [e.dataset.from, e.dataset.to])')

    def edge_labels(self):
        return self.page.locator('#canvas .elabel').all_text_contents()

    def box(self, node_id):
        """The node's shape on the screen: {x, y, width, height}."""
        return self.node(node_id).locator('.shape').bounding_box()

    def port_centre(self, node_id, direction, name):
        b = self.node(node_id).locator(f'.port[data-dir="{direction}"][data-port="{name}"]').bounding_box()
        return b['x'] + b['width'] / 2, b['y'] + b['height'] / 2

    def message(self):
        return self.page.text_content('#toast')

    def menu(self, name, item=None):
        self.page.click(f'#menubar button.mb:text-is("{name}")')
        if item:
            self.page.click(item)

    def new_diagram(self):
        self.menu('File', '#bNew')

    def open(self, path):
        before = self.message()
        self.page.set_input_files('#fileIn', str(path))
        self.page.wait_for_function('t => document.querySelector("#toast").innerText !== t', arg=before)

    def save(self, folder):
        with self.page.expect_download() as d:
            self.menu('File', '#bSave')
        path = Path(folder) / d.value.suggested_filename
        d.value.save_as(path)
        return path

    def saved(self, folder):
        """Save, and return the YAML's data, checked against the schema."""
        data = yaml.safe_load(self.save(folder).read_text())
        jsonschema.validate(data, SCHEMA)
        assert edge_problems(data) == []
        return data

    def add_node(self):
        self.page.click('#bNode')

    def rename(self, node_id, label):
        self.node(node_id).click()
        self.page.keyboard.press('F2')
        self.page.keyboard.press('Control+A')
        self.page.keyboard.type(label)
        self.page.keyboard.press('Enter')


@pytest.fixture
def dg(page, server):
    """A fresh editor showing a new, empty diagram; each test gets new browser storage."""
    if LOCAL_LIBS:
        _use_local_libs(page)
    d = Diagram(page, server + '/diagram-editor.html')
    d.load()
    yield d
    assert not d.errors, f'JavaScript errors on the page: {d.errors}'


def overlap(a, b):
    return a['x'] < b['x'] + b['width'] and b['x'] < a['x'] + a['width'] \
        and a['y'] < b['y'] + b['height'] and b['y'] < a['y'] + a['height']


def test_a_new_diagram_is_empty_and_saves_as_yaml_in_the_schema_format(dg, tmp_path):
    assert dg.title() == 'New diagram'
    assert dg.nodes() == []
    path = dg.save(tmp_path)
    assert path.name == 'new_diagram.yaml'
    data = yaml.safe_load(path.read_text())
    jsonschema.validate(data, SCHEMA)
    assert data == {'diagram': {'title': 'New diagram'}}


def test_opening_a_diagram_shows_its_nodes_ports_and_edges(dg):
    dg.open(DATA_FLOW)
    assert 'Opened' in dg.message()
    assert dg.title() == 'Mind map data flow'
    assert dg.nodes() == ['user', 'edit', 'map', 'browser_storage', 'build_zip', 'file', 'server', 'read_zip', 'check']
    assert dg.label('read_zip') == 'Read zip'
    assert dg.ports('read_zip', 'in') == ['zip']
    assert dg.ports('read_zip', 'out') == ['yaml', 'images']
    assert dg.ports('map', 'in') == ['map', 'opened'] and dg.ports('map', 'out') == ['map', 'autosave']
    assert len(dg.edges()) == 12
    assert ['read_zip.yaml', 'check.yaml'] in dg.edges()
    assert 'Save to server' in dg.edge_labels()


def test_nodes_and_ports_are_drawn_where_the_file_says(dg):
    dg.open(DATA_FLOW)
    user, edit, check = dg.box('user'), dg.box('edit'), dg.box('check')
    assert edit['width'] == pytest.approx(user['width']) and edit['y'] == pytest.approx(user['y'])
    scale = (edit['x'] - user['x']) / 220                            # the view may be zoomed to fit
    assert check['y'] - user['y'] == pytest.approx(200 * scale, abs=1)
    assert check['x'] - user['x'] == pytest.approx(440 * scale, abs=1)
    assert user['width'] == pytest.approx(140 * scale, abs=3)        # the box includes the outline
    assert user['height'] == pytest.approx(60 * scale, abs=3)
    # ports without a layout: inputs on the left, outputs on the right
    assert dg.port_centre('edit', 'in', 'actions')[0] == pytest.approx(edit['x'], abs=2)
    assert dg.port_centre('edit', 'out', 'map')[0] == pytest.approx(edit['x'] + edit['width'], abs=2)
    # ports with a side
    assert dg.port_centre('check', 'out', 'map')[1] == pytest.approx(check['y'], abs=2)
    assert dg.port_centre('check', 'out', 'error')[0] == pytest.approx(check['x'], abs=2)
    yaml_port, images_port = dg.port_centre('check', 'in', 'yaml'), dg.port_centre('check', 'in', 'images')
    assert yaml_port[0] == pytest.approx(check['x'] + check['width'], abs=2)
    assert images_port[1] - yaml_port[1] == pytest.approx(0.4 * check['height'], abs=2)


@pytest.mark.parametrize('example', [DATA_FLOW] + SCHEMA['examples'], ids=['data flow', 'new', 'every feature'])
def test_a_diagram_with_layout_is_saved_unchanged(dg, tmp_path, example):
    if isinstance(example, dict):
        path = tmp_path / 'example.yaml'
        path.write_text(yaml.safe_dump(example, sort_keys=False))
    else:
        path = example
    dg.open(path)
    assert dg.saved(tmp_path / 'out') == yaml.safe_load(path.read_text())


def test_a_diagram_without_layout_is_laid_out_and_keeps_its_meaning(dg, tmp_path):
    dg.open(FLOWCHART)
    original = yaml.safe_load(FLOWCHART.read_text())
    ids = list(original['diagram']['nodes'])
    assert dg.nodes() == ids
    for a, b in itertools.combinations(ids, 2):
        assert not overlap(dg.box(a), dg.box(b)), f'{a} and {b} overlap'
    data = dg.saved(tmp_path)
    assert all({'x', 'y'} <= set(n['layout']) for n in data['diagram']['nodes'].values())
    assert without_layout(data) == original
    assert list(data['diagram']['nodes']['is_zip']['outputs']) == ['yes', 'no']      # still strings once saved


def test_new_nodes_get_ids_that_stay_when_the_label_changes(dg, tmp_path):
    dg.add_node()
    dg.add_node()
    assert dg.nodes() == ['node', 'node_2']
    assert not overlap(dg.box('node'), dg.box('node_2'))
    dg.rename('node_2', 'Read zip')
    assert dg.label('node_2') == 'Read zip'
    nodes = dg.saved(tmp_path)['diagram']['nodes']
    assert list(nodes) == ['node', 'node_2']
    assert nodes['node_2']['label'] == 'Read zip' and {'x', 'y'} <= set(nodes['node_2']['layout'])


def _changed(change):
    data = yaml.safe_load(SMALL)
    change(data['diagram'])
    return yaml.safe_dump(data, sort_keys=False)


@pytest.mark.parametrize('text, problem', [
    ('diagram: [\n', 'not valid YAML'),
    ('title: no diagram\n', '"diagram"'),
    ('diagram:\n  kind: flowchart\n', 'has no title'),
    (_changed(lambda d: d.update(nodes=[{'label': 'A'}])), 'nodes'),
    (_changed(lambda d: d['edges'][0].update(to='c.in1')), 'c.in1'),               # no such node
    (_changed(lambda d: d['edges'][0].update(to='b.in2')), 'b.in2'),               # no such port
    (_changed(lambda d: d['edges'][0].update({'from': 'b.in1'})), 'b.in1'),        # an edge starts from an output
    (_changed(lambda d: d['edges'][0].update(to='a.out1')), 'a.out1'),             # and ends at an input
    (_changed(lambda d: d['edges'][0].update(to='b')), '"b"'),                     # an end must name a port
    (SMALL.replace('    b:\n      label: B', '    a:\n      label: B'), 'not valid YAML'),   # duplicate id
], ids=['not YAML', 'no diagram', 'no title', 'nodes as a list', 'edge to a missing node', 'edge to a missing port',
        'edge from an input', 'edge to an output', 'edge end without a port', 'duplicate node id'])
def test_a_bad_file_is_reported_and_the_diagram_is_kept(dg, tmp_path, text, problem):
    dg.add_node()
    path = tmp_path / 'bad.yaml'
    path.write_text(text)
    dg.open(path)
    assert problem in dg.message()
    assert dg.nodes() == ['node'] and dg.title() == 'New diagram'


# --- editing ---

def test_dragging_a_node_moves_it_and_its_edges_follow(dg, tmp_path):
    dg.open(DATA_FLOW)
    before = dg.box('edit')
    edge = dg.page.locator('#canvas path.edge[data-from="user.actions"]')
    path_before = edge.get_attribute('d')
    scale = (before['x'] - dg.box('user')['x']) / 220
    x, y = before['x'] + before['width'] / 2, before['y'] + before['height'] / 2
    dg.page.mouse.move(x, y)
    dg.page.mouse.down()
    dg.page.mouse.move(x + 20 * scale, y - 60 * scale, steps=5)
    dg.page.mouse.up()
    assert dg.box('edit')['y'] == pytest.approx(before['y'] - 60 * scale, abs=1.5)
    assert edge.get_attribute('d') != path_before
    nodes = dg.saved(tmp_path)['diagram']['nodes']
    assert nodes['edit']['layout'] == {'x': 280, 'y': 100, 'w': 140, 'h': 60}
    assert nodes['user']['layout'] == {'x': 40, 'y': 160, 'w': 140, 'h': 60}
    dg.page.click('#bUndo')
    assert dg.saved(tmp_path / 'undone')['diagram']['nodes']['edit']['layout']['y'] == 160


def test_deleting_a_node_removes_its_edges_and_undo_brings_them_back(dg):
    dg.open(DATA_FLOW)
    dg.node('read_zip').click()
    dg.page.keyboard.press('Delete')
    assert 'read_zip' not in dg.nodes()
    assert len(dg.edges()) == 8                       # two edges in and two out went with it
    dg.page.keyboard.press('Control+z')
    assert len(dg.nodes()) == 9 and len(dg.edges()) == 12
    dg.page.keyboard.press('Control+y')
    assert len(dg.nodes()) == 8


def test_an_edge_can_be_selected_labelled_and_deleted(dg, tmp_path):
    path = tmp_path / 'small.yaml'
    path.write_text(SMALL)
    dg.open(path)
    dg.page.locator('#canvas g[data-edge="0"] .ehit').click(force=True)
    assert dg.page.text_content('#selEdge') == 'a.out1 → b.in1'
    dg.page.fill('#edgeLabel', 'feeds')
    assert dg.edge_labels() == ['feeds']
    assert dg.saved(tmp_path / 'out')['diagram']['edges'] == [{'from': 'a.out1', 'to': 'b.in1', 'label': 'feeds'}]
    dg.page.locator('#canvas .elabel').click()
    dg.page.click('#bDel')
    assert dg.edges() == [] and dg.nodes() == ['a', 'b']


def test_undo_brings_back_the_diagram_replaced_by_open(dg):
    dg.add_node()
    dg.open(FLOWCHART)
    assert len(dg.nodes()) == 8
    dg.page.click('#bUndo')
    assert dg.nodes() == ['node'] and dg.title() == 'New diagram'


def test_the_diagram_is_kept_when_the_page_is_reloaded(dg):
    dg.open(DATA_FLOW)
    dg.load()
    assert dg.title() == 'Mind map data flow'
    assert len(dg.nodes()) == 9 and len(dg.edges()) == 12


def test_the_title_and_kind_are_edited_in_the_panel_and_name_the_file(dg, tmp_path):
    dg.page.fill('#title', 'Order handling')
    dg.page.select_option('#kind', 'flowchart')
    path = dg.save(tmp_path)
    assert path.name == 'order_handling.yaml'
    assert yaml.safe_load(path.read_text()) == {'diagram': {'title': 'Order handling', 'kind': 'flowchart'}}


def test_a_double_click_edits_a_label_and_escape_cancels(dg):
    dg.add_node()
    dg.node('node').dblclick()
    dg.page.keyboard.type('Two')
    dg.page.keyboard.press('Enter')
    assert dg.label('node') == 'Two'
    dg.node('node').dblclick()
    dg.page.keyboard.type('Changed my mind')
    dg.page.keyboard.press('Escape')
    assert dg.label('node') == 'Two'
    dg.page.keyboard.press('F2')
    dg.page.keyboard.press('End')
    dg.page.keyboard.press('Shift+Enter')
    dg.page.keyboard.type('lines')
    dg.page.keyboard.press('Enter')
    assert dg.node('node').locator('.label tspan').all_text_contents() == ['Two', 'lines']


def test_the_type_chosen_in_the_panel_changes_the_shape(dg, tmp_path):
    dg.add_node()
    assert dg.page.text_content('#selId') == 'node'
    assert dg.node('node').locator('.shape').evaluate('e => e.tagName') == 'rect'
    dg.page.select_option('#type', 'decision')
    assert dg.node('node').locator('.shape').evaluate('e => e.tagName') == 'polygon'
    assert dg.saved(tmp_path)['diagram']['nodes']['node']['type'] == 'decision'


def options(dg, select):
    return dg.page.locator(f'{select} option').all_text_contents()


def test_a_type_can_be_changed_again_and_again(dg, tmp_path):
    dg.add_node()
    every = ['(none)', 'process', 'store', 'external', 'step', 'decision', 'start', 'end', 'Other…']
    for t in ['store', 'decision', '']:
        assert options(dg, '#type') == every
        dg.page.select_option('#type', t)
    assert 'type' not in dg.saved(tmp_path)['diagram']['nodes']['node']
    dg.page.click('#bUndo')
    assert dg.page.input_value('#type') == 'decision'


def test_other_takes_any_type_name_which_then_joins_the_list(dg, tmp_path):
    dg.add_node()
    assert not dg.page.is_visible('#typeOther')
    dg.page.select_option('#type', label='Other…')
    assert dg.page.is_visible('#typeOther')
    dg.page.keyboard.type('queue')                     # the box has the focus
    dg.page.keyboard.press('Enter')
    assert not dg.page.is_visible('#typeOther')
    assert dg.page.input_value('#type') == 'queue' and options(dg, '#type')[-2:] == ['queue', 'Other…']
    assert dg.saved(tmp_path)['diagram']['nodes']['node']['type'] == 'queue'
    dg.page.select_option('#type', 'process')          # and still back to one of the list
    assert options(dg, '#type')[-2:] == ['end', 'Other…']
    dg.page.click('#bUndo')
    dg.page.click('#bUndo')
    assert 'type' not in dg.saved(tmp_path / 'undone')['diagram']['nodes']['node']


def test_a_kind_or_type_from_a_file_is_shown_in_the_list(dg, tmp_path):
    path = tmp_path / 'er.yaml'
    path.write_text('diagram:\n  title: Shop\n  kind: er\n  nodes:\n    order: {type: entity, label: Order}\n')
    dg.open(path)
    assert dg.page.input_value('#kind') == 'er'
    assert options(dg, '#kind') == ['(none)', 'dataflow', 'flowchart', 'er', 'class', 'Other…']
    dg.node('order').click()
    assert dg.page.input_value('#type') == 'entity'


def test_the_toolbar_holds_only_commands_that_have_keys(dg):
    titles = dg.page.locator('#toolbar button').evaluate_all('bs => bs.map(b => b.title)')
    assert len(titles) == 6 and all('(' in t for t in titles)


@pytest.mark.parametrize('width, height', [(390, 844), (844, 390), (1280, 720)], ids=['phone', 'phone on its side', 'desktop'])
def test_everything_fits_the_screen(dg, width, height):
    dg.page.set_viewport_size({'width': width, 'height': height})
    dg.open(DATA_FLOW)
    assert dg.page.evaluate('[document.documentElement.scrollWidth, document.documentElement.scrollHeight]') == [width, height]
    view = dg.page.locator('#vp').bounding_box()
    for node in dg.nodes():
        b = dg.box(node)
        assert view['x'] <= b['x'] and b['x'] + b['width'] <= view['x'] + view['width'], node
        assert view['y'] <= b['y'] and b['y'] + b['height'] <= view['y'] + view['height'], node
    for edge in dg.page.locator('#canvas path.edge').all():
        b = edge.bounding_box()
        assert view['x'] <= b['x'] and b['x'] + b['width'] <= view['x'] + view['width'], edge.get_attribute('data-from')
    delete = dg.page.locator('#bDel').bounding_box()
    assert delete['x'] >= 0 and delete['x'] + delete['width'] <= width


def test_two_fingers_zoom_the_diagram(dg):
    dg.open(DATA_FLOW)
    before = dg.box('user')['width']
    dg.page.evaluate("""() => {
        const svg = document.querySelector('#canvas'), r = svg.getBoundingClientRect();
        const send = (type, id, x, y) => svg.dispatchEvent(new PointerEvent(type,
            { pointerId: id, pointerType: 'touch', clientX: r.left + x, clientY: r.top + y, bubbles: true, isPrimary: id === 11 }));
        send('pointerdown', 11, 300, 300); send('pointerdown', 12, 400, 300);
        send('pointermove', 11, 250, 300); send('pointermove', 12, 450, 300);
        send('pointerup', 11, 250, 300); send('pointerup', 12, 450, 300);
    }""")
    assert dg.box('user')['width'] == pytest.approx(before * 2, rel=0.03)
    dg.page.keyboard.press('0')                                  # show the whole diagram again
    assert dg.box('user')['width'] == pytest.approx(before, rel=0.01)


def test_the_phone_header_has_two_tidy_rows(dg):
    dg.page.set_viewport_size({'width': 390, 'height': 844})
    top = lambda s: dg.page.locator(s).bounding_box()['y']
    assert top('#mbFile') == pytest.approx(top('#bUndo'), abs=3)
    assert top('#bNode') == top('#bEdit') == top('#bDel') > top('#mbFile') + 10
    assert dg.page.locator('header').bounding_box()['height'] < 80
    assert dg.page.locator('header .logo').is_visible()                       # the tile stays, the name goes
    assert dg.page.locator('header .name').bounding_box()['width'] <= 1


# --- drawing edges: Connect mode makes a port at each end, where the edge starts and ends ---

TWO_NODES = """diagram:
  title: Two
  nodes:
    a:
      label: A
      layout: {x: 0, y: 0, w: 100, h: 60}
    b:
      label: B
      layout: {x: 300, y: 0, w: 100, h: 60}
"""


@pytest.fixture
def two(dg, tmp_path):
    path = tmp_path / 'two.yaml'
    path.write_text(TWO_NODES)
    dg.open(path)
    return dg


def at(dg, node_id, fx, fy):
    """The screen point a fraction fx across and fy down a node's shape."""
    b = dg.box(node_id)
    return b['x'] + fx * b['width'], b['y'] + fy * b['height']


def drag(dg, start, end):
    dg.page.mouse.move(*start)
    dg.page.mouse.down()
    dg.page.mouse.move(*end, steps=6)
    dg.page.mouse.up()


def test_connect_draws_an_edge_by_dragging_and_makes_ports_where_it_starts_and_ends(two, tmp_path):
    two.page.click('#bConnect')
    assert two.page.get_attribute('#bConnect', 'aria-pressed') == 'true'
    drag(two, at(two, 'a', 0.9, 0.5), at(two, 'b', 0.1, 0.5))
    assert two.edges() == [['a.out1', 'b.in1']]
    assert two.ports('a', 'out') == ['out1'] and two.ports('b', 'in') == ['in1']
    data = two.saved(tmp_path)['diagram']
    assert data['nodes']['a']['outputs'] == {'out1': {'layout': {'side': 'right', 'at': 0.5}}}
    assert data['nodes']['b']['inputs'] == {'in1': {'layout': {'side': 'left', 'at': 0.5}}}
    assert data['edges'] == [{'from': 'a.out1', 'to': 'b.in1'}]
    assert data['nodes']['a']['layout'] == {'x': 0, 'y': 0, 'w': 100, 'h': 60}        # nothing moved


def test_connect_works_with_two_taps_too(two):
    two.page.keyboard.press('c')
    two.page.mouse.click(*at(two, 'a', 0.5, 0.95))
    assert 'source' in two.node('a').get_attribute('class')
    two.page.mouse.click(*at(two, 'b', 0.5, 0.05))
    assert two.edges() == [['a.out1', 'b.in1']]
    sides = two.page.evaluate("""() => [...document.querySelectorAll('.port')].map(p => [p.dataset.port, +p.getAttribute('cy')])""")
    assert sides == [['out1', 60], ['in1', 0]]                     # the bottom of A and the top of B


def test_dropping_on_a_port_reuses_it(two):
    two.page.keyboard.press('c')
    drag(two, at(two, 'a', 0.9, 0.5), at(two, 'b', 0.1, 0.5))
    out1, in1 = two.port_centre('a', 'out', 'out1'), two.port_centre('b', 'in', 'in1')
    drag(two, out1, at(two, 'b', 0.5, 0.95))                      # from the same output to a new place on B
    assert two.edges() == [['a.out1', 'b.in1'], ['a.out1', 'b.in2']]
    drag(two, out1, in1)                                           # the same edge again
    assert len(two.edges()) == 2 and 'already' in two.message()


def test_in_connect_mode_a_drag_never_moves_a_node_and_escape_leaves_the_mode(two):
    before = two.box('a')
    two.page.keyboard.press('c')
    drag(two, at(two, 'a', 0.5, 0.5), at(two, 'a', 0.5, 0.5)[0:1] + (before['y'] + 200,))   # dropped on empty space
    assert two.box('a') == before and two.edges() == []
    two.page.keyboard.press('Escape')
    assert two.page.get_attribute('#bConnect', 'aria-pressed') == 'false'
    drag(two, at(two, 'a', 0.5, 0.5), (before['x'] + before['width'] / 2, before['y'] + 130))
    assert two.box('a')['y'] > before['y'] + 50


def test_ports_are_renamed_and_typed_in_the_panel_and_edges_follow(two, tmp_path):
    two.page.keyboard.press('c')
    drag(two, at(two, 'a', 0.9, 0.5), at(two, 'b', 0.1, 0.5))
    two.page.keyboard.press('Escape')
    two.node('a').click()
    name = two.page.locator('#portList [aria-label="Name of output out1"]')
    name.fill('zip')
    two.page.locator('#portList [aria-label="Data type of output zip"]').fill('bytes')
    assert two.edges() == [['a.zip', 'b.in1']]
    data = two.saved(tmp_path)['diagram']
    assert data['nodes']['a']['outputs'] == {'zip': {'type': 'bytes', 'layout': {'side': 'right', 'at': 0.5}}}
    two.page.click('#bUndo')                                       # one undo step for the whole visit to each box
    two.page.click('#bUndo')
    assert two.edges() == [['a.out1', 'b.in1']]


@pytest.mark.parametrize('bad', ['two words', '', 'b-c'])
def test_a_port_name_must_be_a_name_and_unique(two, bad):
    two.page.keyboard.press('c')
    drag(two, at(two, 'a', 0.9, 0.3), at(two, 'b', 0.1, 0.3))
    drag(two, at(two, 'a', 0.9, 0.7), at(two, 'b', 0.1, 0.7))
    two.page.keyboard.press('Escape')
    two.node('a').click()
    for name in (bad, 'out1'):                                     # not a name; then the other port's name
        box = two.page.locator('#portList [aria-label="Name of output out2"]')
        box.fill(name)
        assert box.get_attribute('aria-invalid') == 'true'
        assert two.edges() == [['a.out1', 'b.in1'], ['a.out2', 'b.in2']]
    box.press('Enter')                                             # leaving the box puts the name back
    assert box.input_value() == 'out2' and box.get_attribute('aria-invalid') is None


def test_deleting_an_edge_removes_the_ports_it_made_but_not_ones_you_named(two):
    two.page.keyboard.press('c')
    drag(two, at(two, 'a', 0.9, 0.3), at(two, 'b', 0.1, 0.3))
    drag(two, at(two, 'a', 0.9, 0.7), at(two, 'b', 0.1, 0.7))
    two.page.keyboard.press('Escape')
    two.node('a').click()
    two.page.locator('#portList [aria-label="Name of output out2"]').fill('result')
    for _ in range(2):
        two.page.locator('#canvas g[data-edge="0"] .ehit').click(force=True)
        two.page.keyboard.press('Delete')
    assert two.edges() == []
    assert two.ports('a', 'out') == ['result'] and two.ports('b', 'in') == []


def test_deleting_a_port_deletes_its_edges(dg):
    dg.open(DATA_FLOW)
    dg.node('read_zip').click()
    dg.page.click('#portList [aria-label="Delete output yaml"]')
    assert dg.ports('read_zip', 'out') == ['images']
    assert ['read_zip.yaml', 'check.yaml'] not in dg.edges() and len(dg.edges()) == 11
    dg.page.click('#bUndo')
    assert dg.ports('read_zip', 'out') == ['yaml', 'images'] and len(dg.edges()) == 12


# --- bending edges and moving ports ---

JOINED = """diagram:
  title: Joined
  nodes:
    a:
      label: A
      outputs:
        out1: {}
      layout: {x: 0, y: 0, w: 100, h: 60}
    b:
      label: B
      inputs:
        in1: {}
      layout: {x: 300, y: 0, w: 100, h: 60}
  edges:
    - {from: a.out1, to: b.in1, label: feeds}
"""


@pytest.fixture
def joined(dg, tmp_path):
    path = tmp_path / 'joined.yaml'
    path.write_text(JOINED)
    dg.open(path)
    return dg


def scale(dg):
    return dg.box('a')['width'] / 100


def centre(locator):
    b = locator.bounding_box()
    return b['x'] + b['width'] / 2, b['y'] + b['height'] / 2


def nudge(dg, start, dx, dy):
    """Drag from a screen point by (dx, dy) in diagram units."""
    k = scale(dg)
    drag(dg, start, (start[0] + dx * k, start[1] + dy * k))


def handles(dg):
    return dg.page.locator('#handleLayer .handle .dot')


def test_a_selected_edge_has_two_handles_that_bend_its_curve(joined, tmp_path):
    assert handles(joined).count() == 0
    joined.page.locator('#canvas .elabel').click()
    assert handles(joined).count() == 2
    path = joined.page.locator('#canvas path.edge').get_attribute('d')
    nudge(joined, centre(handles(joined).nth(0)), 0, 80)
    assert joined.page.locator('#canvas path.edge').get_attribute('d') != path
    edge = joined.saved(tmp_path)['diagram']['edges'][0]
    assert edge['layout']['curve'] == [[180, pytest.approx(110, abs=1)], [220, 30]]   # the other stays where it was drawn
    joined.page.click('#bUndo')
    assert 'layout' not in joined.saved(tmp_path / 'undone')['diagram']['edges'][0]


def test_automatic_curve_puts_an_edge_back_to_the_curve_the_editor_draws(joined, tmp_path):
    joined.page.locator('#canvas .elabel').click()
    assert joined.page.locator('#edgeAuto').is_disabled()
    nudge(joined, centre(handles(joined).nth(1)), 0, -50)
    joined.page.click('#edgeAuto')
    assert 'layout' not in joined.saved(tmp_path)['diagram']['edges'][0]
    assert joined.page.locator('#edgeAuto').is_disabled()


def test_moving_a_node_takes_the_near_end_of_a_bent_curve_with_it(joined, tmp_path):
    joined.page.locator('#canvas .elabel').click()
    nudge(joined, centre(handles(joined).nth(0)), 0, 80)
    nudge(joined, at(joined, 'b', 0.5, 0.5), 50, 20)
    edge = joined.saved(tmp_path)['diagram']['edges'][0]
    assert edge['layout']['curve'] == [[180, pytest.approx(110, abs=1)], [pytest.approx(270, abs=1), pytest.approx(50, abs=1)]]


def test_dragging_a_port_moves_it_around_the_node_and_the_edge_follows(joined, tmp_path):
    before = centre(joined.node('a').locator('.shape'))
    nudge(joined, joined.port_centre('a', 'out', 'out1'), -50, 30)    # from the right side to the middle of the bottom
    assert centre(joined.node('a').locator('.shape')) == pytest.approx(before, abs=0.5)
    nodes = joined.saved(tmp_path)['diagram']['nodes']
    assert nodes['a']['outputs'] == {'out1': {'layout': {'side': 'bottom', 'at': 0.5}}}
    assert nodes['a']['layout'] == {'x': 0, 'y': 0, 'w': 100, 'h': 60}
    assert joined.edges() == [['a.out1', 'b.in1']]
    joined.page.keyboard.press('Control+z')
    assert 'layout' not in joined.saved(tmp_path / 'undone')['diagram']['nodes']['a']['outputs']['out1']


def test_tapping_a_port_selects_its_node(joined):
    joined.page.mouse.click(*joined.port_centre('b', 'in', 'in1'))
    assert joined.page.text_content('#selId') == 'b'


# --- how types are drawn ---

def stacked(dg, node_id):
    """The lines of text on a node, top to bottom."""
    return dg.node(node_id).locator('.label tspan').all_text_contents()


def test_a_type_without_a_shape_of_its_own_is_named_above_the_label(dg):
    dg.add_node()
    assert stacked(dg, 'node') == ['Node']
    for t, lines in [('process', ['Node']), ('step', ['Node']), ('', ['Node'])]:
        dg.page.select_option('#type', t)
        assert stacked(dg, 'node') == lines, t
    dg.page.select_option('#type', label='Other…')
    dg.page.keyboard.type('entity')
    dg.page.keyboard.press('Enter')
    assert stacked(dg, 'node') == ['«entity»', 'Node']
    assert dg.node('node').locator('.label tspan.stereo').count() == 1


def test_the_shape_of_a_type_is_chosen_in_the_panel_for_every_node_of_that_type(dg, tmp_path):
    path = tmp_path / 'er.yaml'
    path.write_text('diagram:\n  title: Shop\n  kind: er\n  nodes:\n'
                    '    places: {type: relationship, label: places}\n    buys: {type: relationship, label: buys}\n'
                    '    order: {type: entity, label: Order}\n')
    dg.open(path)
    assert not dg.page.is_visible('#shape')                    # nothing selected
    dg.node('places').click()
    assert dg.page.is_visible('#shape') and dg.page.input_value('#shape') == ''
    assert options(dg, '#shape') == ['Default: rectangle', 'rectangle', 'rounded', 'diamond', 'pill', 'store', 'external']
    dg.page.select_option('#shape', 'diamond')
    for node in ('places', 'buys'):
        assert dg.node(node).locator('.shape').evaluate('e => e.tagName') == 'polygon'
        assert stacked(dg, node) == [dg.label(node).strip()]   # the shape now says what it is
    assert stacked(dg, 'order') == ['«entity»', 'Order']
    data = dg.saved(tmp_path / 'out')['diagram']
    assert data['layout'] == {'shapes': {'relationship': 'diamond'}}
    assert 'layout' not in data['nodes']['places'] or 'shape' not in data['nodes']['places']['layout']
    dg.page.click('#bUndo')
    assert dg.node('buys').locator('.shape').evaluate('e => e.tagName') == 'rect'
    assert 'layout' not in dg.saved(tmp_path / 'undone')['diagram']


def test_a_built_in_type_can_be_given_another_shape_and_given_back_its_own(dg, tmp_path):
    dg.add_node()
    dg.page.select_option('#type', 'decision')
    assert options(dg, '#shape')[0] == 'Default: diamond'
    dg.page.select_option('#shape', 'pill')
    assert dg.node('node').locator('.shape').evaluate('e => [e.tagName, +e.getAttribute("rx") > 0]') == ['rect', True]
    dg.page.select_option('#shape', '')
    assert dg.node('node').locator('.shape').evaluate('e => e.tagName') == 'polygon'
    assert 'layout' not in dg.saved(tmp_path)['diagram']


def test_a_node_without_a_type_has_no_shape_choice(dg):
    dg.add_node()
    assert dg.page.is_visible('#type') and not dg.page.is_visible('#shape')


def test_an_unknown_shape_name_in_a_file_is_kept_and_drawn_as_a_rectangle(dg, tmp_path):
    path = tmp_path / 'odd.yaml'
    path.write_text('diagram:\n  title: Odd\n  nodes:\n    a: {type: cloud, label: A}\n  layout:\n    shapes: {cloud: cloud}\n')
    dg.open(path)
    assert dg.node('a').locator('.shape').evaluate('e => e.tagName') == 'rect'
    assert stacked(dg, 'a') == ['A']
    assert dg.saved(tmp_path / 'out')['diagram']['layout'] == {'shapes': {'cloud': 'cloud'}}
