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

Design a SQLite table and get a simple data-entry application for it: list, search, add, edit and delete records.

- **Design a table:** give it a name and columns. Each column has a type (Text, Long text, Whole number, Decimal number, Date, Yes / No, or Link to another table) and can be required. An auto-numbered `id` is added for you, and the SQL is shown before it runs.
- **Change a design:** rename the table, add or remove columns, or delete the table.
- **Link tables (foreign keys):** a column can link to a record in another table. Linked columns show the other record's name in the list and a drop-down in the form, and links are enforced. An existing column can be converted into a link: text values are matched by name, and anything without a match is reported before any change is made.
- **Work with records:** a sortable, searchable list. Click a row to edit or delete it; forms use the right input for each type.
- **Open existing databases:** any SQLite file works, and you can pick which of its tables to work with.
- **Name your database:** **New database** asks for a file name, and you can rename it by clicking the name in the header.
- **Remembered between visits:** every change is saved in the browser (IndexedDB) and the database reopens next time. The browser keeps one database at a time and clearing site data deletes it, so **Download database** is still your real backup.

Each screen works with one table at a time; screen designers are planned.

---

Both tools need an internet connection on first load, to fetch sql.js and JSZip from cdnjs.
