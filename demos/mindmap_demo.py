"""Record a demo video of the Mind Map Editor as an mp4.

The demo starts a new map, adds and edits branches, adds a note, connects two
branches and saves the map. Captions describe each step, and a drawn pointer
shows where the clicks go (a headless browser has no visible mouse).

In Jupyter:     await record_mindmap_demo('mindmap-demo.mp4')
In a script:    asyncio.run(record_mindmap_demo('mindmap-demo.mp4'))

To record your local copy instead of the published page, pass its address,
e.g. url='file:///home/me/browser-based-tools/mindmap-editor.html'.

Needs Playwright with Chromium (pip install playwright; playwright install chromium)
and ffmpeg on the PATH.
"""
import asyncio
import re
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.async_api import async_playwright

PAGES_URL = 'https://romilly.github.io/browser-based-tools/mindmap-editor.html'
SIZE = {'width': 1280, 'height': 720}

# A pointer that follows the mouse, a ring on each click, and a caption box.
OVERLAY_JS = r"""
window.addEventListener('DOMContentLoaded', () => {
  const css = document.createElement('style');
  css.textContent = `
    #demo-pointer{position:fixed;left:0;top:0;width:22px;height:22px;z-index:99999;pointer-events:none;
      transform:translate(-3px,-2px);filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))}
    .demo-ring{position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;z-index:99998;
      pointer-events:none;border:3px solid #e8a33d;animation:demo-ring .5s ease-out forwards}
    @keyframes demo-ring{from{transform:scale(.3);opacity:1}to{transform:scale(1.4);opacity:0}}
    #demo-caption{position:fixed;left:24px;bottom:24px;z-index:99997;max-width:46%;pointer-events:none;
      background:rgba(20,30,34,.88);color:#fff;font:600 19px/1.35 "IBM Plex Sans",system-ui,sans-serif;
      padding:10px 16px;border-radius:8px;transition:opacity .25s}
    #demo-caption:empty{opacity:0}`;
  document.head.append(css);
  const p = document.createElement('div');
  p.id = 'demo-pointer';
  p.innerHTML = '<svg viewBox="0 0 22 22" width="22" height="22"><path d="M2 1l16 10-7 1.5L7.5 20z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  const cap = document.createElement('div');
  cap.id = 'demo-caption';
  document.body.append(p, cap);
  document.addEventListener('mousemove', e => { p.style.left = e.clientX + 'px'; p.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div');
    r.className = 'demo-ring'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.body.append(r); setTimeout(() => r.remove(), 600);
  }, true);
});
"""


class Demo:
    """Small, paced actions that read well on video."""

    def __init__(self, page):
        self.page = page

    async def pause(self, seconds=0.5):
        await self.page.wait_for_timeout(seconds * 1000)

    async def caption(self, text, hold=1.2):
        await self.page.evaluate('t => { document.querySelector("#demo-caption").textContent = t; }', text)
        await self.pause(hold)

    def node(self, title):
        exact = re.compile('^' + re.escape(title) + '$')
        return self.page.locator('.node').filter(has=self.page.locator('.t', has_text=exact)).first

    async def point_at(self, target):
        locator = self.page.locator(target) if isinstance(target, str) else target
        box = await locator.bounding_box()
        await self.page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, steps=25)
        await self.pause(0.25)

    async def click(self, target):
        await self.point_at(target)
        await self.page.mouse.down()
        await self.page.mouse.up()
        await self.pause(0.5)

    async def double_click(self, target):
        await self.point_at(target)
        await self.page.mouse.dblclick(*(await self._pointer()))
        await self.pause(0.4)

    async def _pointer(self):
        return await self.page.evaluate(
            '() => { const p = document.querySelector("#demo-pointer"); return [parseFloat(p.style.left), parseFloat(p.style.top)]; }')

    async def type(self, text, then=None):
        await self.page.keyboard.type(text, delay=85)
        await self.pause(0.3)
        if then:
            await self.press(then)

    async def press(self, key):
        await self.page.keyboard.press(key)
        await self.pause(0.6)


async def run_script(demo):
    """The steps shown in the video."""
    page = demo.page
    await demo.caption('Mind Map Editor: a Freeplane-style mind map in your browser', 2.5)

    await demo.caption('Start a new map')
    await demo.click('#bNew')

    await demo.caption('Double-click the central topic to name it')
    await demo.double_click(demo.node('New mind map'))
    await demo.type('Holiday in the Netherlands', then='Enter')

    await demo.caption('Tab adds a branch; Enter adds the next one')
    await demo.press('Tab')
    await demo.type('Travel', then='Enter')
    await demo.press('Enter')
    await demo.type('Where to stay', then='Enter')

    await demo.caption('New branches on the central topic balance the two sides')
    await demo.click(demo.node('Holiday in the Netherlands'))
    await demo.press('Tab')
    await demo.type('Things to do', then='Enter')

    await demo.caption('Select a branch and add branches below it')
    await demo.click(demo.node('Travel'))
    await demo.press('Tab')
    await demo.type('Harwich ferry', then='Enter')
    await demo.press('Enter')
    await demo.type('Train to Amsterdam', then='Enter')
    await demo.click(demo.node('Things to do'))
    await demo.press('Tab')
    await demo.type('Museums', then='Enter')
    await demo.press('Enter')
    await demo.type('Cycling', then='Enter')

    await demo.caption('Double-click a branch to change its title')
    await demo.double_click(demo.node('Where to stay'))
    await demo.type('Hotel in Utrecht', then='Enter')

    await demo.caption('Add a note in the Note panel')
    await demo.click(demo.node('Harwich ferry'))
    await demo.click('#note')
    await demo.type('Book a cabin for the overnight crossing.')
    await demo.press('Escape')

    await demo.caption('Connect two branches, with an optional label')
    await demo.click(demo.node('Cycling'))
    await demo.click('#bConnect')
    await demo.click(demo.node('Hotel in Utrecht'))
    await demo.type('hire bikes here', then='Enter')
    await demo.press('Escape')
    await demo.pause(0.8)

    await demo.caption('Save the map as a zipped YAML file')
    async with page.expect_download():
        await demo.click('#bSave')
    await demo.pause(2.5)
    await demo.caption('', 0.8)


async def record_mindmap_demo(out='mindmap-demo.mp4', url=PAGES_URL, prepare_page=None, headless=True):
    """Record the demo and write it to `out` as an mp4. Returns the path.

    prepare_page: optional `async def f(page)` run before the page loads,
    e.g. to route requests to local files when working offline.
    """
    out = Path(out).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport=SIZE, device_scale_factor=1, color_scheme='light', accept_downloads=True,
                record_video_dir=tmp, record_video_size=SIZE)
            await context.add_init_script(OVERLAY_JS)
            started = time.monotonic()
            page = await context.new_page()
            if prepare_page:
                await prepare_page(page)
            await page.goto(url)
            await page.wait_for_selector('.node.root')
            await page.evaluate('document.fonts.ready')
            await page.mouse.move(640, 300)
            ready = time.monotonic() - started   # skip the blank frames before the page appears
            await run_script(Demo(page))
            await context.close()
            webm = await page.video.path()
            await browser.close()
        subprocess.run(
            ['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{max(ready - 0.1, 0):.2f}', '-i', str(webm),
             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
             '-movflags', '+faststart', '-an', str(out)],
            check=True)
    return out


if __name__ == '__main__':
    print(asyncio.run(record_mindmap_demo()))
