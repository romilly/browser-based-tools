# browser-based-tools

Small, self-contained tools that run entirely in a web browser. Each tool is a single HTML file: open it in a browser and it works, with no server or install.

## Tools

### SQLite Browser — `sqlite-browser.html`

**[Open the SQLite Browser](https://romilly.github.io/browser-based-tools/sqlite-browser.html)**

Open a SQLite database file in your browser, browse its tables and columns, and run SQL against it.

- Open a `.db` / `.sqlite` file with the button, or drag it onto the page. A small sample database loads at startup so you can try it straight away.
- Click a table to see its columns (primary key highlighted) and its first 100 rows.
- Run any SQL with **Run query** or Ctrl/⌘+Enter. Multiple statements give multiple result grids.
- Changes affect an in-memory copy only. Click **Download database** to save them.
- Your file is never uploaded: SQLite runs in the browser via [sql.js](https://github.com/sql-js/sql.js).

### CRUDulator — `crudulator.html`

**[Open CRUDulator](https://romilly.github.io/browser-based-tools/crudulator.html)**

Design a SQLite database of linked tables and get a simple data-entry application for it: list, search, add, edit and delete records in every table.

- **Several tables in one database:** add as many tables as you need with **New table**, and switch between them with the **Table** menu.
- **Design a table:** give it a name and columns. Each column has a type (Text, Long text, Whole number, Decimal number, Date, Yes / No, or Link to another table) and can be required. An auto-numbered `id` is added for you, and the SQL is shown before it runs.
- **Change a design:** rename the table, add or remove columns, or delete the table.
- **Link tables (foreign keys):** a column can link to a record in another table. Linked columns show the other record's name in the list and a drop-down in the form, and links are enforced. An existing column can be converted into a link: text values are matched by name, and anything without a match is reported before any change is made.
- **Work with records:** a sortable, searchable list. Click a row to edit or delete it; forms use the right input for each type.
- **CSV import and export:** export a whole table as CSV (linked columns as names). Import a CSV into a table, with headings matched to columns, a preview, a choice of UK, US or ISO dates, and a list of any problems; the import is all or nothing. **Start from CSV…** in the table designer creates a new table with column types guessed from the file and imports its rows. Comma, semicolon and tab separated files work, including ones saved by older Windows Excel.
- **Open existing databases:** any SQLite file works, and you can pick which of its tables to work with.
- **Name your database:** **New database** asks for a file name, and you can rename it by clicking the name in the header.
- **Remembered between visits:** every change is saved in the browser (IndexedDB) and the database reopens next time. The browser keeps one database at a time and clearing site data deletes it, so **Download database** is still your real backup.

Each record list and form shows one table at a time, with links to other tables shown by name. Screen designers are planned.

### Mind Map Editor — `mindmap-editor.html`

**[Open the Mind Map Editor](https://romilly.github.io/browser-based-tools/mindmap-editor.html)**

Build a mind map in the style of [Freeplane](https://docs.freeplane.org/): a central topic with branches curving out to the left and right. Every branch has a title and an optional note.

- **Add, edit and delete branches:** Tab adds a child, Enter adds a sibling, F2 or a double-click (double-tap on a tablet) edits a title, and Delete removes a branch with everything below it. The toolbar buttons do the same on touch screens.
- **Notes:** select a branch and type in the Note panel. Branches with a note show a small page icon, and hovering shows the note.
- **Fold branches:** Space folds or unfolds a branch. A folded branch shows a circle with the number of hidden nodes; click it to unfold.
- **Move around:** the arrow keys move between branches, and you can drag the empty space (or swipe) to scroll the map.
- **Undo and redo:** Ctrl+Z and Ctrl+Y, or the toolbar buttons.
- **Help:** the Help button, or `?`, lists every action.
- **Open and Save:** **Save** downloads the map as a `.zip` file holding one YAML file in the format described by [`mindmap-schema.json`](mindmap-schema.json). **Open** reads one of those, or a plain `.yaml` file, and replaces the current map (Undo brings the old one back). You can also drop a file onto the map. YAML doesn't record which side of the centre a branch is on, so an opened map shares its branches between left and right.
- **Remembered between visits:** the current map is also kept in the browser (localStorage), but not across browsers or devices, so use **Save** to keep a copy.

---

The SQLite Browser and CRUDulator need an internet connection on first load, to fetch sql.js and JSZip from cdnjs. The Mind Map Editor fetches js-yaml and JSZip from cdnjs for Open and Save; editing works without them.

## Running the tests

The tests are written with [pytest](https://pytest.org) and [Playwright](https://playwright.dev/python/): they open the pages in a real browser, click through them, and check the downloaded databases with Python's `sqlite3`.

One-time setup, from the repository folder:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
playwright install chromium
```

Then, with the venv active:

```bash
pytest                    # run everything, headless
pytest --headed           # watch the browser while the tests run
pytest -k link            # run only tests with "link" in their name
```

The tests serve the repository from a local web server, so no setup is needed beyond the above. The pages fetch sql.js and JSZip from cdnjs; to run offline, put `sql-asm.js` and `jszip.min.js` in a folder and set `CRUD_LOCAL_LIBS` to its path (add `js-yaml.min.js` for the Mind Map Editor tests).
