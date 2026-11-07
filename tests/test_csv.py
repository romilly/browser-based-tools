"""CSV import and export in crudulator.html."""
import csv
import sqlite3

import pytest


def write(path, text, encoding='utf-8'):
    path.write_bytes(text.encode(encoding))
    return path


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.reader(f))


def fetch(path, sql):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def convert_issuer(app, cds_db):
    app.open_file(cds_db)
    app.choose_table('cds')
    app.edit_design()
    app.convert_to_link('Issuer', 'Issuers')
    app.save_design()


# ---------- the parser and other pure functions ----------

def test_parse_quotes_commas_and_line_breaks(app):
    text = 'a,b,c\r\n"x, y","say ""hi""","two\nlines"\r\n'
    assert app.js('parseCSV', text)['rows'] == [['a', 'b', 'c'], ['x, y', 'say "hi"', 'two\nlines']]


def test_parse_skips_bom_and_blank_lines(app):
    result = app.js('parseCSV', '﻿a,b\n\n1,2\n\n')
    assert result['rows'] == [['a', 'b'], ['1', '2']]


def test_parse_keeps_empty_fields(app):
    assert app.js('parseCSV', 'a,b,c\n1,,\n')['rows'] == [['a', 'b', 'c'], ['1', '', '']]


@pytest.mark.parametrize('sep', [';', '\t'])
def test_parse_detects_semicolons_and_tabs(app, sep):
    result = app.js('parseCSV', f'name{sep}price\n"a{sep}b"{sep}1,5\n')
    assert result['delimiter'] == sep
    assert result['rows'] == [['name', 'price'], [f'a{sep}b', '1,5']]


def test_written_csv_reads_back_unchanged(app):
    rows = [['id', 'text'], ['1', 'plain'], ['2', 'comma, here'], ['3', 'quote " here'], ['4', 'line\nbreak'], ['5', ' padded ']]
    text = app.js('toCSV', rows)
    assert text.startswith('﻿') and '\r\n' in text
    assert app.js('parseCSV', text)['rows'] == rows


@pytest.mark.parametrize('value, fmt, expected', [
    ('17/12/1920', 'UK', '1920-12-17'),
    ('12/17/1920', 'US', '1920-12-17'),
    ('1.2.2020', 'UK', '2020-02-01'),
    ('1.2.2020', 'US', '2020-01-02'),
    ('1920-12-17', 'UK', '1920-12-17'),     # ISO is accepted whatever the choice
    ('1920-12-17', 'ISO', '1920-12-17'),
    ('17/12/1920', 'ISO', None),
    ('17/12/1920', 'US', None),             # there is no 17th month
    ('31/02/2020', 'UK', None),             # no 31st of February
    ('17/12/20', 'UK', None),               # two-digit years are ambiguous
])
def test_parse_date(app, value, fmt, expected):
    assert app.js('parseDate', value, fmt) == expected


@pytest.mark.parametrize('values, expected', [
    (['2020-01-02', '2021-03-04'], 'ISO'),
    (['25/12/2020', '01/02/2020'], 'UK'),
    (['12/25/2020', '01/02/2020'], 'US'),
    (['01/02/2020'], 'UK'),                 # can't tell, so UK
])
def test_detect_date_format(app, values, expected):
    assert app.js('detectDateFormat', values) == expected


@pytest.mark.parametrize('values, expected', [
    (['1', '22', '-3'], 'INTEGER'),
    (['01234 567890', '01473 123456'], 'TEXT'),
    (['007', '12'], 'TEXT'),                # leading zeros: codes, not numbers
    (['1.5', '2', '-0.25'], 'REAL'),
    (['Yes', 'no', 'TRUE'], 'BOOLEAN'),
    (['1', '0'], 'INTEGER'),
    (['2020-01-02', '17/12/1920'], 'DATE'),
    (['short', 'x' * 150], 'LONGTEXT'),
    (['one\ntwo'], 'LONGTEXT'),
    (['12', 'twelve'], 'TEXT'),
    (['', '  '], 'TEXT'),
    (['3', ''], 'INTEGER'),                 # blanks don't affect the guess
])
def test_guess_kind(app, values, expected):
    assert app.js('guessKind', values) == expected


@pytest.mark.parametrize('heading, expected', [
    ('CD Count', 'CD_Count'), ('  price (£) ', 'price'), ('2nd name', 'c_2nd_name'), ('***', 'fallback'),
])
def test_headings_become_column_names(app, heading, expected):
    assert app.js('identFrom', heading, 'fallback') == expected


def test_decodes_windows_excel_files(app):
    utf8 = app.page.evaluate("b => window.crudulator.decodeText(new Uint8Array(b))", list('Café £5'.encode('utf-8')))
    cp1252 = app.page.evaluate("b => window.crudulator.decodeText(new Uint8Array(b))", list('Café £5'.encode('cp1252')))
    assert utf8 == {'text': 'Café £5', 'encoding': 'UTF-8'}
    assert cp1252 == {'text': 'Café £5', 'encoding': 'Windows-1252'}


# ---------- export ----------

def test_export_whole_table(app, tmp_path):
    app.search('grace')                     # export ignores the search
    path = app.export_csv(tmp_path)
    assert path.name == 'contacts.csv'
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    rows = read_csv(path)
    assert rows[0] == ['id', 'name', 'email', 'phone', 'birthday', 'active', 'notes']
    assert len(rows) == 5
    assert rows[1] == ['1', 'Ada Lovelace', 'ada@example.com', '01234 567890', '1815-12-10', '1', 'Wrote the first published algorithm.']
    assert rows[2][3] == ''                 # NULL becomes an empty cell
    assert rows[3][6] == 'Popularised the term "debugging".'


def test_export_writes_linked_names(app, cds_db, tmp_path):
    convert_issuer(app, cds_db)
    rows = read_csv(app.export_csv(tmp_path))
    assert [r[2] for r in rows] == ['Issuer', 'Naxos', 'Hyperion']


# ---------- import into an existing table ----------

def test_import_appends_rows_and_matches_headings(app, tmp_path):
    path = write(tmp_path / 'more.csv',
                 'ID,Name,EMAIL,Birthday,Active,Shoe size\n'
                 '99,Kenneth Iverson,ken@example.com,17/12/1920,yes,9\n'
                 '100,John Backus,,03/12/1924,No,\n')
    app.import_csv(path)
    columns = app.page.inner_text('#import-columns')
    assert 'Name → name' in columns and 'EMAIL → email' in columns
    assert 'Shoe size' in columns and 'ID' in columns          # listed as ignored
    assert app.page.input_value('#import-date-format') == 'UK'  # 17/12 can only be UK
    assert app.import_problems() == ''
    app.confirm_import()
    assert app.rows() == 6
    out = app.download(tmp_path)
    assert fetch(out, "SELECT id, name, email, birthday, active FROM contacts WHERE id > 4") == [
        (5, 'Kenneth Iverson', 'ken@example.com', '1920-12-17', 1),
        (6, 'John Backus', None, '1924-12-03', 0),
    ]


def test_date_format_choice_changes_the_check(app, tmp_path):
    path = write(tmp_path / 'dates.csv', 'name,birthday\nA,05/06/2001\nB,07/08/2002\n')
    app.import_csv(path)
    app.page.select_option('#import-date-format', 'ISO')
    assert 'Row 2, birthday' in app.import_problems()
    assert app.import_button().is_disabled()
    app.page.select_option('#import-date-format', 'US')
    assert app.import_problems() == ''
    app.confirm_import()
    out = app.download(tmp_path)
    assert fetch(out, "SELECT birthday FROM contacts WHERE name IN ('A', 'B') ORDER BY name") == [('2001-05-06',), ('2002-07-08',)]


def test_bad_values_block_the_whole_import(app, tmp_path):
    path = write(tmp_path / 'bad.csv', 'name,active,birthday\nGood,yes,2000-01-01\nBad,perhaps,2000-13-01\n,no,\n')
    app.import_csv(path)
    problems = app.import_problems()
    assert 'Row 3, active: “perhaps” isn’t yes or no' in problems
    assert 'Row 3, birthday' in problems
    assert 'Row 4, name: a value is required' in problems
    assert app.import_button().is_disabled()
    app.page.click('#import-cancel')
    assert app.rows() == 4


def test_missing_required_column_is_reported(app, tmp_path):
    app.import_csv(write(tmp_path / 'noname.csv', 'email\nx@example.com\n'))
    assert 'name is required, but the file has no heading for it' in app.import_problems()


def test_extra_values_are_reported(app, tmp_path):
    app.import_csv(write(tmp_path / 'ragged.csv', 'name\nAda,extra\n'))
    assert 'Row 2: has more values than there are headings' in app.import_problems()


def test_semicolon_file_from_windows_excel(app, tmp_path):
    path = write(tmp_path / 'excel.csv', 'name;notes\nZoë;Café owner, £5 a cup\n', encoding='cp1252')
    app.import_csv(path)
    assert 'semicolons' in app.page.inner_text('#import-summary')
    assert 'Windows-1252' in app.page.inner_text('#import-summary')
    app.confirm_import()
    out = app.download(tmp_path)
    assert fetch(out, "SELECT notes FROM contacts WHERE name = 'Zoë'") == [('Café owner, £5 a cup',)]


def test_export_then_import_round_trip(app, tmp_path):
    exported = app.export_csv(tmp_path)
    app.import_csv(exported)
    assert app.import_problems() == ''
    app.confirm_import()
    assert app.rows() == 8
    out = app.download(tmp_path)
    cols = 'name, email, phone, birthday, active, notes'
    assert fetch(out, f'SELECT {cols} FROM contacts WHERE id <= 4 ORDER BY id') == \
           fetch(out, f'SELECT {cols} FROM contacts WHERE id > 4 ORDER BY id')


# ---------- importing into linked columns ----------

def test_import_links_by_name_or_id(app, cds_db, tmp_path):
    convert_issuer(app, cds_db)
    app.import_csv(write(tmp_path / 'cds.csv', 'Title,Issuer\nGoldberg Variations,hyperion\nThe Magic Flute,1\nSilence,\n'))
    assert app.import_problems() == ''
    app.confirm_import()
    out = app.download(tmp_path)
    assert fetch(out, 'SELECT Title, Issuer FROM cds WHERE id > 2 ORDER BY id') == [
        ('Goldberg Variations', 2), ('The Magic Flute', 1), ('Silence', None)]


def test_unknown_linked_name_is_reported(app, cds_db, tmp_path):
    convert_issuer(app, cds_db)
    app.import_csv(write(tmp_path / 'cds.csv', 'Title,Issuer\nX,Deutsche Grammophon\n'))
    assert 'Row 2, Issuer: no Issuers record called “Deutsche Grammophon”' in app.import_problems()


def test_ambiguous_linked_name_is_reported(app, cds_db, tmp_path):
    convert_issuer(app, cds_db)
    app.choose_table('Issuers')
    app.add_record(Name='Naxos')            # a second Naxos
    app.choose_table('cds')
    app.import_csv(write(tmp_path / 'cds.csv', 'Title,Issuer\nX,Naxos\n'))
    assert 'more than one Issuers record is called “Naxos”' in app.import_problems()


# ---------- new table from a CSV file ----------

def test_new_table_from_csv(app, tmp_path):
    path = write(tmp_path / 'Book List.csv',
                 'id,Title,Pages,Price,Published,In stock,Code\n'
                 '7,SICP,657,45.50,1985-07-01,yes,007\n'
                 '8,TAOCP,672,,1968-01-01,no,012\n')
    app.start_from_csv(path)
    assert app.page.input_value('#d-name') == 'Book_List'
    assert app.designer_columns() == [
        ('Title', 'TEXT'), ('Pages', 'INTEGER'), ('Price', 'REAL'), ('Published', 'DATE'), ('In_stock', 'BOOLEAN'), ('Code', 'TEXT')]
    assert app.page.inner_text('#d-save') == 'Create table and import 2 rows'
    app.save_design()
    assert app.page.input_value('#table-select') == 'Book_List'
    assert app.rows() == 2
    out = app.download(tmp_path)
    assert fetch(out, 'SELECT * FROM Book_List ORDER BY id') == [
        (1, 'SICP', 657, 45.5, '1985-07-01', 1, '007'), (2, 'TAOCP', 672, None, '1968-01-01', 0, '012')]


def test_new_table_from_csv_with_bad_rows_creates_nothing(app, tmp_path):
    app.start_from_csv(write(tmp_path / 'things.csv', 'name,qty\nA,1\nB,2\n'))
    app.page.locator('#d-cols .col-row').nth(1).locator('select').select_option('BOOLEAN')   # 2 isn't yes/no
    app.save_design()
    assert 'Row 3, qty: “2” isn’t yes or no' in app.design_error
    assert 'things' not in app.page.inner_text('#table-select')


def test_new_table_from_csv_can_link_to_existing_table(app, cds_db, tmp_path):
    app.open_file(cds_db)
    app.start_from_csv(write(tmp_path / 'tracks.csv', 'title,cd\nGute Nacht,Winterreise\nAria,The Marriage of Figaro\n'))
    app.page.locator('#d-cols .col-row').nth(1).locator('select').select_option('REF:cds')
    app.save_design()
    assert 'Winterreise' in app.grid_text() and '→ cds' in app.grid_text()
