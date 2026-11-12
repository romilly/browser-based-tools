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
    scale = user['width'] / 140                                      # the view may be zoomed to fit
    assert edit['x'] - user['x'] == pytest.approx(220 * scale, abs=1)
    assert check['y'] - user['y'] == pytest.approx(200 * scale, abs=1)
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
