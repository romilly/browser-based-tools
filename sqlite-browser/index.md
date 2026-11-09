---
title: SQLite Browser
---

# SQLite Browser

Open a SQLite database file in your browser, browse its tables and columns, and run SQL against it.

**[Open the SQLite Browser](../sqlite-browser.html)**

## What it does

- **Open a database:** choose a `.db`, `.sqlite` or `.sqlite3` file, or drag it onto the page. A small sample database opens at the start so you can try the tool straight away.
- **Browse tables:** click a table or view to see its columns (the primary key is highlighted) and its first 100 rows.
- **Run SQL:** type any SQL and click **Run query**, or press Ctrl+Enter (⌘+Enter on a Mac). Several statements run in order, and each one that returns rows gets its own result grid.
- **Change data safely:** `INSERT`, `UPDATE`, `CREATE TABLE` and other statements change an in-memory copy only. Your file is untouched until you click **Download database** to save a changed copy.

## Your data

Your file is never uploaded. SQLite runs inside your browser using [sql.js](https://github.com/sql-js/sql.js), and the database is held in memory while the page is open.

## Requirements

A modern browser. The page loads sql.js and JSZip from cdnjs, so it needs an internet connection when it first opens.

## Documentation

- **In the tool:** click **Help** for a guide to opening, browsing, querying and saving.

[All tools](../)
