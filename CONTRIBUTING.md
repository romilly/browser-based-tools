# Working on the tools

Each tool is a single self-contained HTML file in the root of the repository (`sqlite-browser.html`, `crudulator.html`, `mindmap-editor.html`). GitHub Pages publishes the repository at <https://romilly.github.io/browser-based-tools/>.

## Repository layout

| Path | What it is |
|---|---|
| `*.html` | The tools themselves. They stay at these paths so existing links keep working. |
| `index.md` | The home page of the published site. |
| `sqlite-browser/`, `crudulator/`, `mindmap-editor/` | Each tool's documentation, starting from its landing page, `index.md`. |
| `mindmap-schema.json` | JSON Schema for the Mind Map Editor's files. |
| `tests/` | Browser tests for every tool. |
| `demos/` | Scripts that record demo videos, and the videos (stored with Git LFS). |

The documentation pages are Markdown, turned into web pages by GitHub Pages (Jekyll). Link between them with relative links to the `.md` files; GitHub Pages turns those into links to the published pages, and they also work when browsing the repository on github.com.

## Running the tests

The tests are written with [pytest](https://pytest.org) and [Playwright](https://playwright.dev/python/): they open the pages in a real browser, click through them, and check what they download.

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

The tests serve the repository from a local web server, so no setup is needed beyond the above.

### Running the tests offline

The pages fetch their libraries from cdnjs. To run the tests without internet access, put these files in a folder and set `CRUD_LOCAL_LIBS` to its path:

| File | npm package |
|---|---|
| `sql-asm.js` | `sql.js@1.10.3` (`dist/sql-asm.js`) |
| `jszip.min.js` | `jszip@3.10.1` (`dist/jszip.min.js`) |
| `js-yaml.min.js` | `js-yaml@4.1.0` (`dist/js-yaml.min.js`) |
| `marked.min.js` | `marked@15.0.2` (`marked.min.js`) |
| `purify.min.js` | `dompurify@3.4.17` (`dist/purify.min.js`) |
| `tex-svg-full.js` | `mathjax@3.2.2` (`es5/tex-svg-full.js`) |

`npm pack <package>` downloads a package as a `.tgz` file you can unpack.

## Recording the demo video

`demos/mindmap_demo.py` records a captioned demo of the Mind Map Editor as an mp4, a little under two minutes long. It needs Playwright with Chromium (as for the tests) and `ffmpeg`.

In Jupyter, from the `demos` folder:

```python
from mindmap_demo import record_mindmap_demo
await record_mindmap_demo('mindmap-demo.mp4')
```

It records the published page by default; pass `url='file:///…/mindmap-editor.html'` to record your local copy.

The picture attached in the demo is `mindmap-editor/tutorials/images/harwich_ferry.png` (shared with the tutorial); pass `image=` to use another PNG or JPEG.

Videos are stored with Git LFS (see `.gitattributes`). GitHub Pages serves only the small LFS pointer file, not the video, so a page plays a video from GitHub's media server instead: `https://media.githubusercontent.com/media/romilly/browser-based-tools/main/demos/<file>.mp4`, used as the `src` of a `<video controls>` element.
