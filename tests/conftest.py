"""Shared fixtures: a local web server for the repo, and an App helper that drives crudulator.html.

The pages load sql.js and JSZip from cdnjs. To run without internet access, set CRUD_LOCAL_LIBS
to a folder containing sql-asm.js, jszip.min.js and js-yaml.min.js; requests for them are then served from there.
"""
import functools
import http.server
import os
import sqlite3
import threading
from pathlib import Path

import pytest

from js_coverage import JsCoverage, watch

ROOT = Path(__file__).resolve().parent.parent
LOCAL_LIBS = os.environ.get('CRUD_LOCAL_LIBS')


JS_COVERAGE = pytest.StashKey()


def pytest_addoption(parser):
    parser.addoption('--js-coverage', action='store_true',
                     help="measure which JavaScript in the tools' HTML files the tests run (see tests/js_coverage.py)")


def pytest_configure(config):
    if config.getoption('--js-coverage'):
        config.stash[JS_COVERAGE] = JsCoverage(ROOT)


@pytest.fixture(autouse=True)
def js_coverage(request):
    """With --js-coverage, record what runs on each test's page."""
    coverage = request.config.stash.get(JS_COVERAGE, None)
    if coverage is None or 'page' not in request.fixturenames:
        yield
        return
    stop = watch(request.getfixturevalue('page'), coverage)
    yield
    stop()


def pytest_terminal_summary(terminalreporter, config):
    coverage = config.stash.get(JS_COVERAGE, None)
    if coverage is not None:
        coverage.write_html(ROOT / 'js-coverage')
        terminalreporter.section('JavaScript coverage')
        terminalreporter.write_line(coverage.table())
        terminalreporter.write_line('Details: js-coverage/index.html')


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope='session')
def server():
    """Serve the repository over http, as GitHub Pages does (IndexedDB needs a real origin)."""
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_port}'
    httpd.shutdown()


def _use_local_libs(page):
    folder = Path(LOCAL_LIBS)

    def route(r):
        name = r.request.url.rsplit('/', 1)[-1]
        if (folder / name).exists():
            r.fulfill(path=str(folder / name), content_type='application/javascript')
        else:
            r.abort()

    page.route('https://cdnjs.cloudflare.com/**', route)
    page.route('https://fonts.googleapis.com/**', lambda r: r.abort())
    page.route('https://fonts.gstatic.com/**', lambda r: r.abort())


class App:
    """Drives crudulator.html. Dialogs are handled automatically: confirms are accepted,
    and prompts are answered from `prompt_answers` (or cancelled if it's empty)."""

    def __init__(self, page, url):
        self.page, self.url = page, url
        self.prompt_answers = []
        self.dialogs = []
        self.errors = []
        page.on('dialog', self._on_dialog)
        page.on('pageerror', lambda e: self.errors.append(str(e)))

    def _on_dialog(self, d):
        self.dialogs.append(d.type)
        if d.type == 'prompt':
            d.accept(self.prompt_answers.pop(0)) if self.prompt_answers else d.dismiss()
        else:
            d.accept()

    # --- page state ---
    def load(self):
        self.page.goto(self.url)
        self.page.wait_for_selector('#name-btn')

    def flush(self):
        """Wait until the browser copy is written, so a reload sees it. Reading IndexedDB
        queues behind any pending write, so this returns what was stored."""
        return self.page.evaluate("""() => new Promise((resolve, reject) => {
            const req = indexedDB.open('crudulator', 1);
            req.onerror = () => reject(req.error);
            req.onsuccess = () => {
                const get = req.result.transaction('files').objectStore('files').get('current');
                get.onsuccess = () => resolve(get.result ? { name: get.result.name, dirty: get.result.dirty } : null);
            };
        })""")

    def reload(self):
        self.flush()
        self.load()

    @property
    def info(self):
        return self.page.inner_text('#file-info').lower()

    @property
    def file_name(self):
        return self.page.inner_text('#name-btn').replace('✎', '').strip()

    def rows(self):
        return self.page.locator('#grid tbody tr').count()

    def grid_text(self):
        return self.page.inner_text('#grid')

    # --- actions ---
    def choose_table(self, name):
        self.page.select_option('#table-select', name)

    def search(self, text):
        self.page.fill('#search', text)
        self.page.wait_for_timeout(300)   # the search box waits briefly for typing to stop

    def sort_by(self, column):
        self.page.click(f'[data-sort="{column}"]')

    def first_row(self):
        return self.page.locator('#grid tbody tr').first.inner_text().split('\t')

    def open_row(self, text):
        self.page.locator('#grid tbody tr', has_text=text).click()

    def fill_form(self, **fields):
        for col, value in fields.items():
            el = self.page.locator(f'[data-col="{col}"]')
            tag = el.evaluate('e => e.tagName + (e.type ? ":" + e.type : "")')
            if tag == 'INPUT:checkbox':
                el.set_checked(bool(value))
            elif tag.startswith('SELECT'):
                el.select_option(label=value)
            else:
                el.fill(str(value))

    def save_record(self):
        self.page.click('#record-form button[type=submit]')

    def add_record(self, **fields):
        self.page.click('#new-record-btn')
        self.fill_form(**fields)
        self.save_record()

    def record_error(self):
        return self.page.inner_text('#record-error')

    def open_file(self, path):
        self.page.set_input_files('#file-input', str(path))
        self.page.wait_for_function(
            "name => document.querySelector('#name-btn').innerText.includes(name)", arg=Path(path).name)

    def download(self, folder):
        with self.page.expect_download() as d:
            self.page.click('#save-btn')
        path = Path(folder) / d.value.suggested_filename
        d.value.save_as(path)
        return path

    # --- CSV ---
    def js(self, name, *args):
        """Call one of the page's pure CSV functions (window.crudulator.<name>)."""
        return self.page.evaluate('([name, args]) => window.crudulator[name](...args)', [name, list(args)])

    def _choose_file(self, button, path):
        with self.page.expect_file_chooser() as chooser:
            self.page.click(button)
        chooser.value.set_files(str(path))

    def export_csv(self, folder):
        with self.page.expect_download() as d:
            self.page.click('#export-btn')
        path = Path(folder) / d.value.suggested_filename
        d.value.save_as(path)
        return path

    def import_csv(self, path):
        """Choose a CSV file for the current table; leaves the import dialog open."""
        self._choose_file('#import-btn', path)
        self.page.wait_for_selector('#import-dlg[open]')

    def import_problems(self):
        el = self.page.locator('#import-problems')
        return el.inner_text() if el.is_visible() else ''

    def import_button(self):
        return self.page.locator('#import-go')

    def confirm_import(self):
        self.page.click('#import-go')

    def start_from_csv(self, path):
        self.page.click('#new-table-btn')
        self._choose_file('#d-from-csv', path)
        self.page.wait_for_function(
            "name => document.querySelector('#d-csv-info').innerText.includes(name)", arg=Path(path).name)

    def designer_columns(self):
        """[(name, type value)] for the new-column rows in the designer."""
        rows = self.page.locator('#d-cols .col-row:not(.fixed)')
        return [(rows.nth(i).locator('input[type=text]').input_value(), rows.nth(i).locator('select').input_value())
                for i in range(rows.count())]

    # --- designer ---
    def new_table(self, name, *columns):
        """columns: (name, type_value, required) tuples; type_value as in the Type box, e.g. 'INTEGER' or 'REF:cds'."""
        self.page.click('#new-table-btn')
        self.page.fill('#d-name', name)
        for i, (col, kind, required) in enumerate(columns):
            if i:
                self.page.click('#d-add-col')
            row = self.page.locator('#d-cols .col-row').nth(i)
            row.locator('input[type=text]').fill(col)
            row.locator('select').select_option(kind)
            row.locator('input[type=checkbox]').set_checked(required)

    def edit_design(self):
        self.page.click('#design-btn')

    def add_column(self, name, kind='TEXT'):
        self.page.click('#d-add-col')
        row = self.page.locator('#d-cols .col-row:not(.fixed)').last
        row.locator('input[type=text]').fill(name)
        row.locator('select').select_option(kind)

    def remove_column(self, name):
        self.page.locator('.col-row.fixed', has=self.page.locator(f'span:text-is("{name}")')).locator('button').click()

    def convert_to_link(self, column, target):
        self.page.select_option(f'select[aria-label="Type of {column}"]', target)

    def save_design(self):
        self.page.click('#d-save')

    @property
    def sql_preview(self):
        return self.page.inner_text('#d-sql')

    @property
    def design_error(self):
        return self.page.inner_text('#d-error')


@pytest.fixture
def app(page, server):
    """A fresh CRUDulator page; each test gets a new browser context, so browser storage starts empty."""
    if LOCAL_LIBS:
        _use_local_libs(page)
    a = App(page, server + '/crudulator.html')
    a.load()
    yield a
    assert not a.errors, f'JavaScript errors on the page: {a.errors}'


@pytest.fixture
def cds_db(tmp_path):
    """A small database like the CDs example: cds.Issuer holds issuer names as text."""
    path = tmp_path / 'CDS.db'
    con = sqlite3.connect(path)
    con.executescript('''
        CREATE TABLE "cds" ("id" INTEGER PRIMARY KEY, "Title" TEXT, "Issuer" TEXT, "cd_count" INTEGER, "Description" LONGTEXT);
        CREATE TABLE "Issuers" ("id" INTEGER PRIMARY KEY, "Name" TEXT);
        INSERT INTO Issuers (Name) VALUES ('Naxos'), ('Hyperion');
        INSERT INTO cds (Title, Issuer, cd_count, Description) VALUES
          ('The Marriage of Figaro', 'Naxos', 3, 'Mozart''s classic opera'),
          ('Winterreise', 'Hyperion', 1, NULL);
    ''')
    con.commit()
    con.close()
    return path
