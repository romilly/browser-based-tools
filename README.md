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

Needs an internet connection on first load, to fetch sql.js and JSZip from cdnjs.
