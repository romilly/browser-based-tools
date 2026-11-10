---
title: Mind Map Editor
---

# Mind Map Editor

Build a mind map in the style of [Freeplane](https://docs.freeplane.org/): a central topic with branches curving out to the left and right. Branches can have notes, maths, images, icons, web links, and connectors to other branches.

**[Open the Mind Map Editor](../mindmap-editor.html)**

<video controls preload="metadata" width="100%" src="https://media.githubusercontent.com/media/romilly/browser-based-tools/main/demos/mindmap-demo.mp4">
  <a href="https://media.githubusercontent.com/media/romilly/browser-based-tools/main/demos/mindmap-demo.mp4">Download the demo video</a>
</video>

## What it does

- **Add, edit and delete branches:** Tab adds a child, Enter adds a sibling, F2 or a double-click (double-tap on a tablet) edits a title, and Delete removes a branch with everything below it. The toolbar buttons do the same on touch screens.
- **Notes:** each branch can have a note, written in Markdown and shown formatted. Maths can be written in LaTeX, between `$…$` in a line or `$$…$$` on its own, and is drawn with MathJax.
- **Images:** attach a PNG or JPEG to a branch from the **Image** menu, or by dropping or pasting it. It shows under the title.
- **Icons:** the **Icons** menu has about 60 icons, including priorities 1–9, idea, important, question, flags and dates. They use Freeplane's icon names.
- **Web links:** type an address in the **Link** box, and the branch shows a link icon that opens the page.
- **Connectors:** a dashed arrow from any branch to any other, with an optional label.
- **Fold, reorder and move around:** Space folds a branch; Ctrl+↑ and Ctrl+↓ move it among its siblings; the arrow keys move between branches; drag or swipe the empty space to scroll.
- **Undo and redo:** Ctrl+Z and Ctrl+Y, or the toolbar buttons.
- **Open and Save:** **Save** downloads the map as a `.zip` file holding a YAML file and any images. **Open** reads one of those, or a plain `.yaml` file.
- **Export as Markdown:** downloads the map as a `.zip` of linked Markdown pages, one per branch in folders shaped like the map, with its images. Notes and maths are copied as they are, so the pages read well on GitHub or in Obsidian.

## Your data

The current map and its images are kept in your browser between visits, but not across browsers or devices. Use **Save** to keep a copy you can move, back up or share.

Nothing is uploaded: the map is saved as a file on your own computer. If you want all your devices to share the same maps, you can [run your own server](how-to/run-a-server.md) on your home network.

## Requirements

A modern browser on a desktop, tablet or phone. The page loads its libraries from cdnjs:

- js-yaml and JSZip, for Open and Save;
- marked and DOMPurify, to show notes formatted;
- MathJax, only when a note contains maths.

Editing works without them, with notes shown as plain text.

## Documentation

- **Tutorial:** [Your first mind map](tutorials/first-mind-map/index.md) — plan a holiday and learn every main feature in about 20 minutes.
- **How-to:** [Share maps between your devices with a server](how-to/run-a-server.md) — run the small mind map server on a computer on your home network, by hand or as a service.
- **In the tool:** click **Help**, or press `?`, for every key and menu, and a short LaTeX guide.
- **Reference:** [The file format](reference/file-format.md) — how a map is stored, for people and AI agents that write map files, with a checker you can paste into Jupyter. The machine-readable definition is [`mindmap-schema.json`](../mindmap-schema.json).

[All tools](../)
