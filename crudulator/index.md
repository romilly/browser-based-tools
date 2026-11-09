---
title: CRUDulator
---

# CRUDulator

Design a SQLite database of linked tables and get a simple data-entry application for it: list, search, add, edit and delete records in every table.

**[Open CRUDulator](../crudulator.html)**

## What it does

- **Several tables in one database:** add as many tables as you need with **New table**, and switch between them with the **Table** menu.
- **Design a table:** give it a name and columns. Each column has a type (Text, Long text, Whole number, Decimal number, Date, Yes / No, or Link to another table) and can be required. An auto-numbered `id` is added for you, and the SQL is shown before it runs.
- **Change a design:** rename a table, add or remove columns, or delete the table.
- **Link tables:** a column can link to a record in another table (a foreign key). Linked columns show the other record's name in the list and a drop-down in the form, and links are enforced. An existing column can be turned into a link: text values are matched by name, and anything without a match is reported before any change is made.
- **Work with records:** a sortable, searchable list. Click a row to edit or delete it; each form uses the right input for each column's type.
- **Import and export CSV:** export a whole table as CSV, or import a CSV into a table with headings matched to columns, a preview, a choice of UK, US or ISO dates, and a list of any problems. The import is all or nothing. **Start from CSV…** creates a new table from a file, guessing the column types.
- **Open existing databases:** any SQLite file works, and you can choose which of its tables to work with.

## Your data

Everything happens in your browser; nothing is uploaded. Every change is saved automatically in the browser's own storage (IndexedDB), and the database reopens when you come back.

The browser keeps one database at a time, and clearing your browsing data deletes it, so use **Download database** to keep a real copy.

## Requirements

A modern browser. The page loads sql.js and JSZip from cdnjs, so it needs an internet connection when it first opens.

## Documentation

- **In the tool:** click **Help** for a guide to designing tables, linking them, CSV files, records and saving.

[All tools](../)
