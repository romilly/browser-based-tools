"""Browser tests for crudulator.html. Run with:  pytest   (see README for setup)."""
import sqlite3


def schema(path, table):
    con = sqlite3.connect(path)
    try:
        return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]
    finally:
        con.close()


def fetch(path, sql):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# ---------- records ----------

def test_opens_with_sample_contacts(app):
    assert app.rows() == 4
    assert 'sample data' in app.info


def test_search_filters_rows(app):
    app.search('grace')
    assert app.rows() == 1
    app.search('')
    assert app.rows() == 4


def test_required_field_blocks_save(app):
    app.page.click('#new-record-btn')
    app.save_record()
    assert app.page.locator('#record-dlg').is_visible()


def test_add_record(app):
    app.add_record(name='Kenneth Iverson', birthday='1920-12-17', active=True)
    assert app.rows() == 5
    assert 'Kenneth Iverson' in app.grid_text()
    assert 'not downloaded' in app.info


def test_edit_record(app):
    app.open_row('Alan Turing')
    app.fill_form(email='turing@example.com')
    app.save_record()
    assert 'turing@example.com' in app.grid_text()


def test_delete_record(app):
    app.open_row('Dijkstra')
    app.page.click('#record-delete')
    assert app.rows() == 3
    assert 'Dijkstra' not in app.grid_text()


def test_sort_toggles_direction(app):
    app.sort_by('name')
    assert app.first_row()[1] == 'Ada Lovelace'
    app.sort_by('name')
    assert app.first_row()[1] == 'Grace Hopper'


# ---------- table designer ----------

def test_create_table_previews_sql_then_creates_it(app):
    app.new_table('books', ('title', 'TEXT', True), ('pages', 'INTEGER', False), ('finished', 'BOOLEAN', False))
    assert 'CREATE TABLE "books"' in app.sql_preview
    assert '"title" TEXT NOT NULL' in app.sql_preview
    app.save_design()
    assert app.page.input_value('#table-select') == 'books'
    assert 'No records yet' in app.grid_text()


def test_duplicate_table_name_is_rejected(app):
    app.new_table('contacts', ('x', 'TEXT', False))
    app.save_design()
    assert 'already a table' in app.design_error


def test_invalid_column_name_is_rejected(app):
    app.new_table('things', ('bad name', 'TEXT', False))
    app.save_design()
    assert 'letters, digits and underscores' in app.design_error


def test_add_and_remove_columns(app, tmp_path):
    app.edit_design()
    app.remove_column('phone')
    app.add_column('rating', 'REAL')
    assert 'DROP COLUMN "phone"' in app.sql_preview
    assert 'ADD COLUMN "rating" REAL' in app.sql_preview
    app.save_design()
    app.open_row('Ada Lovelace')
    assert app.page.locator('[data-col="rating"]').count() == 1
    assert app.page.locator('[data-col="phone"]').count() == 0


def test_open_existing_db_with_text_primary_key(app, tmp_path):
    path = tmp_path / 'stock.db'
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE items (code VARCHAR(10) PRIMARY KEY, qty INT NOT NULL, price NUMERIC)')
    con.execute("INSERT INTO items VALUES ('A1', 3, 9.99)")
    con.commit()
    con.close()
    app.open_file(path)
    assert app.rows() == 1
    app.open_row('A1')
    assert app.page.locator('[data-col="code"]').count() == 1   # a non-numeric key is editable
    app.fill_form(qty=7)
    app.save_record()
    out = tmp_path / 'out'
    out.mkdir()
    assert fetch(app.download(out), 'SELECT qty FROM items') == [(7,)]


# ---------- naming and downloading ----------

def test_rename_is_used_for_download(app, tmp_path):
    app.prompt_answers.append('my contacts')
    app.page.click('#name-btn')
    assert app.file_name == 'my contacts.db'
    path = app.download(tmp_path)
    assert path.name == 'my contacts.db'
    assert fetch(path, 'SELECT count(*) FROM contacts') == [(4,)]


def test_new_database_asks_for_a_name(app):
    app.prompt_answers.append('library.sqlite')
    app.page.click('#new-db-btn')
    assert app.file_name == 'library.sqlite'
    assert app.page.is_visible('#empty-view')


def test_cancelling_new_database_keeps_current_one(app):
    app.page.click('#new-db-btn')          # no answer queued, so the prompt is cancelled
    assert app.file_name == 'contacts.db'
    assert app.rows() == 4


def test_file_names_are_cleaned_up(app):
    app.prompt_answers.append('a/b:c')
    app.page.click('#name-btn')
    assert app.file_name == 'a_b_c.db'


# ---------- saved in the browser ----------

def test_changes_survive_a_reload(app):
    app.add_record(name='Persisted Person')
    app.reload()
    assert 'Persisted Person' in app.grid_text()
    assert 'not downloaded' in app.info
    assert 'sample data' not in app.info


def test_downloading_clears_the_not_downloaded_flag(app, tmp_path):
    app.add_record(name='Someone')
    app.download(tmp_path)
    assert 'not downloaded' not in app.info
    app.reload()
    assert 'not downloaded' not in app.info
    assert 'saved in this browser' in app.info


def test_replacing_undownloaded_work_asks_first(app):
    app.add_record(name='Unsaved')
    app.dialogs.clear()
    app.prompt_answers.append('fresh')
    app.page.click('#new-db-btn')
    assert app.dialogs == ['confirm', 'prompt']
    app.reload()
    assert app.file_name == 'fresh.db'


def test_opened_file_survives_a_reload(app, cds_db):
    app.open_file(cds_db)
    app.reload()
    assert app.file_name == 'CDS.db'


# ---------- links between tables ----------

def test_unmatched_values_block_conversion(app, cds_db):
    app.open_file(cds_db)
    app.choose_table('cds')
    app.add_record(Title='Goldberg Variations', Issuer='Hyperian')   # misspelt
    app.edit_design()
    app.convert_to_link('Issuer', 'Issuers')
    assert 'Hyperian' in app.sql_preview
    app.save_design()
    assert 'Hyperian' in app.design_error


def test_convert_text_column_to_link(app, cds_db, tmp_path):
    app.open_file(cds_db)
    app.choose_table('cds')
    app.edit_design()
    app.convert_to_link('Issuer', 'Issuers')
    assert 'REFERENCES "Issuers"("id")' in app.sql_preview
    app.save_design()
    path = app.download(tmp_path)
    assert fetch(path, 'PRAGMA foreign_key_list(cds)')[0][2:5] == ('Issuers', 'Issuer', 'id')
    assert fetch(path, 'SELECT Title, Issuer FROM cds ORDER BY id') == [('The Marriage of Figaro', 1), ('Winterreise', 2)]
    assert fetch(path, 'PRAGMA foreign_key_check') == []
    assert fetch(path, 'PRAGMA integrity_check') == [('ok',)]


def convert_issuer(app, cds_db):
    app.open_file(cds_db)
    app.choose_table('cds')
    app.edit_design()
    app.convert_to_link('Issuer', 'Issuers')
    app.save_design()


def test_linked_column_shows_names_and_a_dropdown(app, cds_db):
    convert_issuer(app, cds_db)
    assert '→ Issuers' in app.grid_text()
    assert 'Naxos' in app.grid_text() and 'Hyperion' in app.grid_text()
    app.open_row('Winterreise')
    dropdown = app.page.locator('select[data-col="Issuer"]')
    assert dropdown.evaluate('s => s.options[s.selectedIndex].text') == 'Hyperion'
    app.fill_form(Issuer='Naxos')
    app.save_record()
    app.search('naxos')
    assert app.rows() == 2


def test_linked_record_cannot_be_deleted(app, cds_db):
    convert_issuer(app, cds_db)
    app.choose_table('Issuers')
    app.open_row('Naxos')
    app.page.click('#record-delete')
    assert 'still link to it' in app.record_error()


def test_linked_table_cannot_be_dropped(app, cds_db):
    convert_issuer(app, cds_db)
    app.choose_table('Issuers')
    app.edit_design()
    app.page.click('#d-drop')
    assert 'link to it' in app.design_error


def test_new_link_column(app, cds_db):
    app.open_file(cds_db)
    app.new_table('tracks', ('title', 'TEXT', True), ('cd', 'REF:cds', True))
    assert '"cd" INTEGER NOT NULL REFERENCES "cds"("id")' in app.sql_preview
    app.save_design()
    app.add_record(title='Gute Nacht', cd='Winterreise')
    assert 'Winterreise' in app.grid_text()
