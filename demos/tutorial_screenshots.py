"""Make the screenshots for the Mind Map Editor tutorial, "Your first mind map".

It follows the tutorial's steps in a real browser and saves a PNG after each one,
so the pictures can be made again whenever the editor changes.

In Jupyter:     await make_tutorial_screenshots()
In a script:    asyncio.run(make_tutorial_screenshots())

To use your local copy instead of the published page, pass its address,
e.g. url='file:///home/me/browser-based-tools/mindmap-editor.html'.

Needs Playwright with Chromium (pip install playwright; playwright install chromium).
"""
import asyncio
import re
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

PAGES_URL = 'https://romilly.github.io/browser-based-tools/mindmap-editor.html'
OUT = Path(__file__).resolve().parent.parent / 'mindmap-editor' / 'tutorials' / 'images'
IMAGE = OUT / 'harwich_ferry.png'
SIZE = {'width': 1280, 'height': 720}
MARGIN = 20   # space left round the cropped part, in pixels
PANEL = ('#noteFor', '#link', '#noteView:not([hidden]) > *')   # the side panel, for steps about notes and links

# The smallest box round every branch, connector and label (and any extra elements), plus MARGIN, inside the window.
CROP = """([extra, wholeMap]) => {
  const els = [...document.querySelectorAll(wholeMap ? '#stage .node, #edges path:not(.hit), #edges text' : wholeMap === false ? '#stage .node.sel' : ':not(*)')];
  for (const sel of extra) els.push(...document.querySelectorAll(sel));
  const rects = els.map(e => e.getBoundingClientRect()).filter(r => r.width && r.height);
  const x0 = Math.max(0, Math.min(...rects.map(r => r.left)) - %(m)d);
  const y0 = Math.max(0, Math.min(...rects.map(r => r.top)) - %(m)d);
  const x1 = Math.min(innerWidth, Math.max(...rects.map(r => r.right)) + %(m)d);
  const y1 = Math.min(innerHeight, Math.max(...rects.map(r => r.bottom)) + %(m)d);
  return {x: x0, y: y0, width: x1 - x0, height: y1 - y0};
}""" % {'m': MARGIN}

# Every screenshot the tutorial uses, in the order they are made.
SHOTS = ['new-map', 'main-branches', 'detail', 'note', 'link', 'picture', 'icons',
         'connector', 'maths', 'folded', 'opened', 'finished']


class Tutorial:
    def __init__(self, page, out):
        self.page, self.out = page, Path(out)

    def node(self, title):
        exact = re.compile('^' + re.escape(title) + '$')
        return self.page.locator('.node').filter(has=self.page.locator('.t', has_text=exact)).first

    async def select(self, title):
        await self.node(title).click()

    async def keys(self, *keys):
        for k in keys:
            await self.page.keyboard.press(k)

    async def type(self, text, then='Enter'):
        await self.page.keyboard.type(text)
        if then:
            await self.page.keyboard.press(then)

    async def menu(self, name, item):
        await self.page.click(f'#menubar button.mb:text-is("{name}")')
        await self.page.click(item)

    async def shot(self, name, *also, whole_map=True):
        """Save a picture cropped to the map's branches and connectors (or, with whole_map=False,
        just the selected branch; with whole_map=None, nothing from the map), plus any `also` selectors."""
        await self.page.wait_for_timeout(300)
        await self.page.mouse.move(0, SIZE['height'] - 1)   # no hover tooltips in the pictures
        box = await self.page.evaluate(CROP, [list(also), whole_map])
        await self.page.screenshot(path=str(self.out / f'{name}.png'), clip=box)

async def run_steps(t, image, folder):
    page = t.page

    # 2. Start a new map
    await t.menu('File', '#bNew')
    await t.node('New mind map').dblclick()
    await t.type('Holiday in the Netherlands')
    await t.shot('new-map')

    # 3. Main branches
    await t.keys('Tab'); await t.type('Travel')
    await t.keys('Enter'); await t.type('Where to stay')
    await t.select('Holiday in the Netherlands')
    await t.keys('Tab'); await t.type('Things to do')
    await t.shot('main-branches')

    # 4. Detail, a title change, and undo
    await t.select('Travel')
    await t.keys('Tab'); await t.type('Harwich ferry')
    await t.keys('Enter'); await t.type('Train to Amsterdam')
    await t.select('Things to do')
    await t.keys('Tab'); await t.type('Museums')
    await t.keys('Enter'); await t.type('Cycling')
    await t.select('Where to stay')
    await t.keys('F2'); await t.type('Hotel in Utrecht')
    await t.select('Museums')
    await t.keys('Delete', 'Control+z')
    await t.shot('detail')

    # 5. A note
    await t.select('Harwich ferry')
    await page.click('#note')
    await t.type('Book the **night ferry** from Harwich.\n\n- bikes go free\n- cabin for two', then='Escape')
    await t.shot('note', *PANEL, whole_map=False)

    # 6. A web link
    await page.click('#link')
    await t.type('www.stenaline.co.uk', then='Enter')
    await t.shot('link', *PANEL, whole_map=False)

    # 7. A picture
    async with page.expect_file_chooser() as chooser:
        await t.menu('Image', '#bAttach')
    await (await chooser.value).set_files(str(image))
    await page.wait_for_selector('.pic img')
    await t.shot('picture')

    # 8. Icons
    await t.select('Travel')
    await t.menu('Icons', '#mIcons [data-icon="full-1"]')
    await t.keys('Escape')
    await t.select('Museums')
    await t.menu('Icons', '#mIcons [data-icon="idea"]')
    await t.keys('Escape')
    await t.shot('icons')

    # 9. A connector
    await t.select('Cycling')
    await page.click('#bConnect')
    await t.select('Hotel in Utrecht')
    await t.type('hire bikes here', then='Enter')
    await t.shot('connector')
    await t.keys('Escape')

    # 10. Maths
    await t.select('Holiday in the Netherlands')
    await t.keys('Tab'); await t.type('Budget')
    await page.click('#note')
    await t.type('Total for $n$ nights:\n\n$$C = n \\times (h + f)$$', then='Escape')
    await page.wait_for_selector('#noteView mjx-container', timeout=20000)
    await t.shot('maths', *PANEL, whole_map=None)

    # 11. Tidy up: move Cycling up, fold Things to do
    await t.select('Cycling')
    await t.keys('Control+ArrowUp')
    await t.select('Things to do')
    await t.keys('Space')
    await t.shot('folded')
    await t.keys('Space')

    # 12. Save, start again, open
    async with page.expect_download() as download:
        await t.menu('File', '#bSave')
    saved = Path(folder) / (await download.value).suggested_filename
    await (await download.value).save_as(saved)
    await t.menu('File', '#bNew')
    async with page.expect_file_chooser() as chooser:
        await t.menu('File', '#bOpen')
    await (await chooser.value).set_files(str(saved))
    await page.wait_for_selector('.pic img')
    await t.select('Harwich ferry')
    await t.shot('opened', '#toast')

    await t.select('Holiday in the Netherlands')
    await page.evaluate('document.querySelector("#toast").hidden = true')
    await t.shot('finished')


async def make_tutorial_screenshots(out=OUT, url=PAGES_URL, prepare_page=None, image=IMAGE):
    """Make the tutorial's screenshots and save them in `out`. Returns the list of files.

    prepare_page: optional `async def f(page)` run before the page loads,
    e.g. to route requests to local files when working offline.
    """
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(viewport=SIZE, device_scale_factor=2,
                                                color_scheme='light', accept_downloads=True)
            page = await context.new_page()
            if prepare_page:
                await prepare_page(page)
            await page.goto(url)
            await page.wait_for_selector('.node.root')
            await page.evaluate('document.fonts.ready')
            await run_steps(Tutorial(page, out), image, folder)
            await browser.close()
    return [out / f'{name}.png' for name in SHOTS]


if __name__ == '__main__':
    print(asyncio.run(make_tutorial_screenshots()))
