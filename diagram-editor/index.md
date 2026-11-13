---
title: Diagram Editor
---

# Diagram Editor

Draw diagrams of nodes joined by edges, in the spirit of [yEd](https://www.yworks.com/products/yed): flowcharts, data-flow pipelines and the like. Each node has named input and output ports, and every edge runs from an output port to an input port, so a saved diagram is a model that programs can read.

**[Open the Diagram Editor](../diagram-editor.html)**

## What it does

- **Nodes and edges:** N adds a node; Connect (C) draws an edge by dragging, or tapping, from one node to another. Ports are made where an edge starts and ends, and can be renamed, given a data type, or dragged round the node's border.
- **Types and shapes:** give a node a type, such as a flowchart step or decision; each known type has its own shape, and you can choose the shape for any type.
- **Curved edges:** select an edge and drag its handles to bend it.
- **Move around:** drag the empty space, pinch or Ctrl + wheel to zoom, and 0 to show the whole diagram.
- **Undo and redo:** Ctrl+Z and Ctrl+Y, or the toolbar buttons.
- **Open and Save:** **Save** downloads the diagram as a YAML file; **Open** reads one back.

## Your data

The current diagram is kept in your browser between visits, but not across browsers or devices. Use **Save** to keep a copy you can move, back up or share.

To share diagrams between your devices, [run the mind map server](../mindmap-editor/how-to/run-a-server.md) on your home network: it serves the Diagram Editor too, and keeps diagrams in folders.

## Requirements

A modern browser on a desktop, tablet or phone. The page loads js-yaml from cdnjs for Open and Save; editing works without it.

## Documentation

- **In the tool:** click **Help**, or press `?`, for every key and gesture.
- **Examples:** [a flowchart](examples/opening_a_file.yaml) and [a data-flow pipeline](examples/mind_map_data_flow.yaml) you can open in the editor.
- **Reference:** the file format is defined by [`diagram-schema.json`](../diagram-schema.json).

[All tools](../)
