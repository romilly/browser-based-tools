# Mind Map Editor file format

This document describes the file format used by the Mind Map Editor (`mindmap-editor.html`). It is written so that a person or an AI agent can produce a file that the editor opens correctly, without having to read the editor's code.

The machine-readable definition is [`mindmap-schema.json`](../../mindmap-schema.json) (JSON Schema, draft 7). This document adds the rules the schema can't express, and explains the YAML pitfalls that most often produce broken files.

## In brief

- A map is a YAML document with a single top-level key, `root`, holding the central node.
- Every node has a `title` (a string). It may also have `icons`, `image`, `note`, `link`, `connectors` and `children`. No other fields are allowed.
- `children` is a mapping, not a list. Each key names a child among its siblings and is made of ASCII letters, digits and underscores. The children appear in the order they are written.
- A connector's `to` is the path of another node: `root`, then each child key, separated by `/`. The node must exist in the same map.
- Notes are Markdown, with LaTeX maths between `$…$` or `$$…$$`. Write them as YAML block scalars (`|`).
- Quote any title that YAML might read as a number, boolean, date or null.
- An `image` is the path of a PNG or JPEG file inside the zip, such as `images/ferry.jpg`.

## Files

The editor saves a `.zip` file holding one YAML file, plus an `images` folder if any node has an image. The zip and the YAML file are named after the root's title, for example `holiday_in_the_netherlands.zip` containing `holiday_in_the_netherlands.yaml` and `images/harwich_ferry_3fa2c1d0.jpg`.

It opens either:

- a `.zip` file. It reads the first file in the archive whose name ends in `.yaml` or `.yml`, ignoring folders and anything under `__MACOSX/`; or
- a plain `.yaml` or `.yml` file. A plain file can't carry images, so any images it names show as placeholders.

Image paths are relative to the YAML file's folder inside the zip. If the YAML file is at `trip/map.yaml`, then `image: images/ferry.jpg` means `trip/images/ferry.jpg`.

Files are UTF-8 text. Indent with spaces, never tabs (YAML forbids tabs for indentation). The editor uses two spaces per level.

## The top level

```yaml
root:
  title: New mind map
```

The document is a mapping with exactly one key, `root`. That shown above is a complete, valid map: the root is the only node required, and it needn't have children.

## Nodes

| Field | Type | Required | Meaning |
|---|---|---|---|
| `title` | string | yes | The text shown on the node. Plain text, not Markdown. May contain line breaks. Keep it short (a few words); put detail in the note. |
| `icons` | list of strings | no | Icons shown before the title, in order. Use the names in [Icons](#icons). |
| `image` | string | no | A PNG or JPEG shown under the title: the path of the image file inside the zip. See [Images](#images). |
| `note` | string | no | A note shown in the side panel, in Markdown with LaTeX maths. See [Notes](#notes). |
| `link` | string | no | A web address. The node shows a link icon that opens it in a new tab. Use an absolute URL starting with `https://` (or `http://`); the editor doesn't add `https://` to links read from a file. |
| `connectors` | list of mappings | no | Dashed arrows from this node to other nodes. See [Connectors](#connectors). |
| `children` | mapping | no | Child nodes, in display order. See [Children and keys](#children-and-keys). |

Leave a field out rather than giving it an empty value. The editor never writes an empty note (or one that is only spaces), an empty link, or an empty list of icons, connectors or children.

Fields not in this table make the file invalid against the schema. The editor ignores them when it opens a file, and drops them when it saves.

## Children and keys

`children` maps keys to nodes:

```yaml
root:
  title: Garden
  children:
    vegetables:
      title: Vegetables
      children:
        runner_beans:
          title: Runner beans
        leeks:
          title: Leeks
    fruit:
      title: Fruit
```

Rules:

- Each key must match `^[a-zA-Z0-9_]+$`: ASCII letters, digits and underscores only.
- Keys must be unique among siblings. YAML itself forbids duplicate keys, and the editor refuses a file that has them. The same key may be used under different parents.
- The order of the keys is the order of the children on the map.
- `children` must be a mapping. A YAML list (lines starting with `- `) is rejected.

Keys don't have to match titles, but the editor makes its own keys from titles every time it saves. If you use the same rule, a file you write will come back unchanged after the editor opens and saves it, and connector paths will be predictable. The rule:

1. Lower-case the title.
2. Replace each run of characters other than `a`–`z` and `0`–`9` with a single `_`. Accented and other non-ASCII letters count as "other", so `Café & Crème!` becomes `caf_cr_me`.
3. Remove `_` from the start and end.
4. Keep the first 40 characters.
5. If nothing is left, use `node`.
6. If a sibling already has that key, add `_2`, then `_3`, and so on.

Keys are not permanent identifiers: renaming a node in the editor changes its key, and every connector path through it, on the next save.

### Left and right of the root

The file doesn't record which side of the central topic a branch is drawn on. When the editor opens a file, it puts the first half of the root's children on the right, rounding up, and the rest on the left. With five children, the first three go right and the last two go left. Order the root's children with that in mind.

## Connectors

A connector is a dashed arrow from the node it belongs to, to any other node, with an optional label.

```yaml
root:
  title: Project
  children:
    design:
      title: Design
      connectors:
        - to: root/testing/user_trials
          label: informs
    testing:
      title: Testing
      children:
        user_trials:
          title: User trials
```

- `to` (required) is the path of the target node: `root`, then the key of each node on the way down, separated by `/`. `root` alone means the central topic.
- `label` (optional) is a string shown on the arrow. Leave it out for no label.
- The target must exist in the same map. If it doesn't, the editor refuses the whole file with a message naming the connector. The schema can't check this.
- Don't point a connector at its own node. The editor keeps such a connector but never draws it.
- A connector can point forwards or backwards in the file, and to a node at any depth.

## Icons

Icons use the names of Freeplane's built-in icons, so a future Freeplane export can keep them. The editor draws these names as emoji:

| Group | Names (as shown in the editor) |
|---|---|
| Priority | `full-1` (Priority 1), `full-2` (Priority 2), `full-3` (Priority 3), `full-4` (Priority 4), `full-5` (Priority 5), `full-6` (Priority 6), `full-7` (Priority 7), `full-8` (Priority 8), `full-9` (Priority 9) |
| Status | `yes` (Important), `idea` (Idea), `help` (Question), `messagebox_warning` (Warning), `button_ok` (OK), `button_cancel` (Not OK), `stop-sign` (Stop), `checked` (Checked), `unchecked` (Unchecked), `flag` (Flag), `bookmark` (Bookmark), `info` (Information) |
| Time | `calendar` (Date), `clock` (Time), `hourglass` (Waiting), `bell` (Reminder) |
| Things | `Mail` (Mail), `attach` (Attachment), `pencil` (To edit), `list` (List), `folder` (Folder), `image` (Image), `video` (Video), `audio` (Audio), `internet` (Internet), `gohome` (Home), `password` (Password), `encrypted` (Locked), `decrypted` (Unlocked), `xmag` (To look into), `launch` (Launch) |
| People | `male1` (Man), `female1` (Woman), `group` (Group), `family` (Family) |
| Smileys | `ksmiletris` (Happy), `smiley-neutral` (Neutral), `smiley-oh` (Surprised), `smiley-angry` (Angry), `smily_bad` (Unhappy) |
| Arrows | `up` (Up), `down` (Down), `back` (Back), `forward` (Forward) |

Names are case-sensitive (`Mail` has a capital M). An unknown name is allowed: the editor keeps it, saves it, and shows it as a small ▫ with the name as a tooltip. Don't repeat a name on the same node; the editor treats choosing an icon again as removing it.

## Images

A node can have one image, shown under its title and scaled to fit within 200 × 200 pixels on the map (smaller images are shown at their own size).

```yaml
root:
  title: Birds
  children:
    robin:
      title: Robin
      image: images/robin.jpg
```

- `image` is the path of the file inside the zip, relative to the YAML file: folders separated by `/`, no leading `/`, and no `..`.
- The file must be a PNG or JPEG, ending in `.png`, `.jpg` or `.jpeg` (in any case). Other formats aren't shown.
- Put the image file into the zip at that path. If it isn't there, the editor shows an "Image missing" placeholder, keeps the `image` field, and reports how many images are missing when it opens and saves the file.
- File names are up to you. The editor names the images it adds `images/<name>_<hash>.<png or jpg>`: the original file name made into a key by the rule in [Children and keys](#children-and-keys), then eight hexadecimal digits from a SHA-256 hash of the bytes. It keeps your names when it saves a file it opened.
- Several nodes can share one image file.
- Large images are fine in a file, but the editor shrinks images it adds to 1600 pixels on the longer side, so keep yours to about that size.

## Notes

A note is Markdown (GitHub-flavoured), shown formatted in the side panel.

- Supported: headings (`#`), **bold** (`**…**`), *italic* (`*…*`), lists (`- ` or `1. `), links (`[text](https://…)`), inline code and fenced code blocks, block quotes, tables, and ~~strikethrough~~.
- Separate paragraphs, and put a blank line before a list. A single line break inside a paragraph is joined into one line.
- Links open in a new tab.
- Avoid raw HTML and images. The editor sanitises notes, removing scripts and similar, and images from other sites may not load where the editor runs.

### Maths

LaTeX maths is drawn by MathJax.

- `$…$` marks a formula within a line: `the area is $\pi r^2$`.
- `$$…$$` marks a displayed formula. Put it on its own lines, with blank lines around it.
- `\$` is a literal dollar sign. As in Pandoc, an opening `$` must not be followed by a space, and a closing `$` must not follow a space or be followed by a digit, so `$5 and $10` stays as text. Write `\$` when in doubt.
- Dollar signs inside code (`` `…` `` or fenced blocks) are not maths.
- A formula with a mistake is shown in red; the rest of the note still displays.
- `\href{url}{text}` makes a link inside a formula. Only `http`, `https` and `mailto` links are kept.

## Writing YAML safely

Most broken files come from YAML reading a value differently from what was meant.

**Quote titles that look like other types.** The title must be a string. Unquoted, `2024`, `3.5`, `true`, `false`, `null`, `~` and `2026-11-09` become a number, a boolean, null or a date, and the editor refuses the file ("has no title"). Some YAML libraries also read `yes`, `no`, `on` and `off` as booleans. Quote them:

```yaml
root:
  title: '2026'
  children:
    'yes':
      title: 'yes'
```

**Quote titles with special characters.** Quote a title if it contains `: ` or ` #`, or starts with any of `- ? : , [ ] { } # & * ! | > ' " % @` or a backtick. Single quotes are simplest: inside them, everything is literal except `'`, which is written `''`.

```yaml
root:
  title: 'Plan: phase 1'
  children:
    rob_s_list:
      title: 'Rob''s list'
```

**Write notes as block scalars.** Use `|` and indent the note's lines below the key. Everything in a block scalar is literal, including `#`, `:`, `$` and backslashes, and the line breaks Markdown needs are kept.

```yaml
root:
  title: Maths
  note: |
    The roots of $ax^2 + bx + c = 0$ are

    $$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$
```

**Never put LaTeX in a double-quoted string.** In double quotes, backslash starts an escape: `"\frac"` becomes a form-feed character followed by `rac`, and `"\nabla"` becomes a line break followed by `abla`. Use a block scalar, as above, or single quotes for a one-line note.

<!-- wrong -->
```yaml
root:
  title: Wrong
  note: "$\frac{1}{2}$"
```

**Multi-line titles.** A title can have line breaks. Use a block scalar with `|-`, which drops the final line break:

```yaml
root:
  title: |-
    Line one
    Line two
```

## What the file doesn't store

- Which side of the root a branch is on (see [Left and right of the root](#left-and-right-of-the-root)).
- Which branches are folded. Every branch is unfolded when a file is opened.
- Positions. The editor lays the map out itself.
- Image sizes. The editor works them out from the image files.

## Checking a file

A file is correct if:

1. it is valid YAML, with no duplicate keys;
2. it is valid against `mindmap-schema.json`;
3. every connector's `to` is the path of a node in the map, other than the connector's own node;
4. no text contains control characters such as a form feed. These are almost always LaTeX written in a double-quoted string; and
5. in a zip, every `image` names a file in the zip.

These Python functions check them: `check_mind_map` checks YAML text (and its images, if you pass the names of the files beside it), and `check_mind_map_zip` checks a whole `.zip` file. It needs `pyyaml` and `jsonschema`, and can be pasted into a Jupyter notebook.

```python
import json
import re
import zipfile
import yaml
import jsonschema

_CONTROL = re.compile('[\x00-\x08\x0b-\x1f\x7f]')   # control characters other than tab and line break


class _UniqueKeyLoader(yaml.SafeLoader):
    """A YAML loader that rejects duplicate keys, as the editor does."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(k, deep=deep) for k, _ in node.value]
        repeated = sorted({str(k) for k in keys if keys.count(k) > 1})
        if repeated:
            raise yaml.constructor.ConstructorError(
                None, None, f'duplicate key(s) {", ".join(repeated)}', node.start_mark)
        return super().construct_mapping(node, deep)


def check_mind_map(text, schema, image_files=None):
    """Return a list of problems with a mind map's YAML text. An empty list means the file is good.

    image_files, if given, is the set of file paths available beside the YAML file (as in a zip);
    every node's image must then be one of them.
    """
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as e:
        return [f'not valid YAML: {e}']
    problems = [f'{"/".join(map(str, e.absolute_path)) or "top level"}: {e.message}'
                for e in jsonschema.Draft7Validator(schema).iter_errors(data)]
    if problems:
        return problems
    paths = {}

    def walk(node, path):
        paths[path] = node
        for key, child in (node.get('children') or {}).items():
            walk(child, f'{path}/{key}')

    walk(data['root'], 'root')
    for path, node in paths.items():
        for c in node.get('connectors', []):
            if c['to'] not in paths:
                problems.append(f'{path}: connector to {c["to"]}, which is not in the map')
            elif c['to'] == path:
                problems.append(f'{path}: connector to its own node')
        if image_files is not None and 'image' in node and node['image'] not in image_files:
            problems.append(f'{path}: image {node["image"]} is not in the zip')
        texts = {'title': node['title'], 'note': node.get('note', ''), 'link': node.get('link', '')}
        texts.update({f'label of connector {i + 1}': c.get('label', '')
                      for i, c in enumerate(node.get('connectors', []))})
        for name, text in texts.items():
            if _CONTROL.search(text):
                problems.append(f'{path}: the {name} contains a control character '
                                '(LaTeX in a double-quoted string? Use a block scalar)')
    return problems


def check_mind_map_zip(path, schema):
    """Check a mind map .zip file: its YAML, as check_mind_map does, and that its images are in the zip."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        yamls = [n for n in names if n.lower().endswith(('.yaml', '.yml')) and not n.startswith('__MACOSX/')]
        if not yamls:
            return ['the zip has no .yaml file']
        folder = yamls[0].rpartition('/')[0]
        prefix = folder + '/' if folder else ''
        beside = {n[len(prefix):] for n in names if n.startswith(prefix)}
        return check_mind_map(z.read(yamls[0]).decode('utf-8'), schema, beside)


# Example:
# schema = json.load(open('mindmap-schema.json'))
# check_mind_map_zip('holiday_in_the_netherlands.zip', schema)
# check_mind_map(open('holiday_in_the_netherlands.yaml').read(), schema)
```

## A complete example

This map uses every feature. Its keys follow the editor's rule, so opening and saving it in the editor gives back the same data. Saved as a zip, it would also hold `images/harwich_ferry.jpg`; opened as plain YAML, that image shows as a placeholder.

```yaml
root:
  title: Holiday in the Netherlands
  link: https://www.holland.com
  note: |
    A week in **June**, travelling by ferry and train.
  children:
    travel:
      title: Travel
      icons:
        - full-1
      note: |
        Book the **night ferry** from Harwich.

        - bikes go free
        - cabin for two
      children:
        harwich_ferry:
          title: Harwich ferry
          image: images/harwich_ferry.jpg
          link: https://www.stenaline.co.uk
          connectors:
            - to: root/places/utrecht
              label: then by train
        trains:
          title: Trains
    budget:
      title: Budget
      icons:
        - idea
        - calendar
      note: |
        Total for $n$ nights at $h$ for the hotel and $f$ for food:

        $$C = n \times (h + f)$$

        The ferry costs about \$200 return.
    places:
      title: Places
      children:
        amsterdam:
          title: Amsterdam
          connectors:
            - to: root/places/utrecht
        utrecht:
          title: Utrecht
          icons:
            - 'yes'
            - flag
    to_do_before_we_go:
      title: 'To do: before we go'
      icons:
        - list
      children:
        book_hotel:
          title: Book hotel
          icons:
            - unchecked
        '2026_passports':
          title: 2026 passports
          icons:
            - checked
```

The root has four children, so Travel and Budget are drawn on the right and Places and To do on the left.

## Checklist for generating a map

1. One top-level key, `root`, with a string `title`.
2. Every node has a `title`; only `title`, `icons`, `image`, `note`, `link`, `connectors` and `children` appear.
3. `children` is a mapping with unique keys made of `a-z`, `A-Z`, `0-9` and `_`, ideally made from titles by the rule above.
4. Titles that look like numbers, booleans, dates or null, or that contain special characters, are quoted.
5. Notes are block scalars (`|`); LaTeX never appears in double quotes.
6. Every connector's `to` is `root` or `root/…/…` naming an existing node other than its own.
7. Icon names come from the table, spelled exactly.
8. Links are absolute `https://` URLs.
9. Each `image` is a relative `.png` or `.jpg` path, and that file is put in the zip beside the YAML.
10. Empty fields are left out.
11. `check_mind_map_zip` (or `check_mind_map` for YAML on its own) returns an empty list.
