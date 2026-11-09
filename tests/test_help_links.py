"""Each tool's Help links to its documentation on the published site, and that page exists in the repo."""
import pytest

from conftest import LOCAL_LIBS, ROOT, _use_local_libs

SITE = 'https://romilly.github.io/browser-based-tools/'

TOOLS = [
    # page, Help button, Help dialog, docs folder
    ('sqlite-browser.html', '#help-btn', 'dialog#help', 'sqlite-browser'),
    ('crudulator.html', '#help-btn', 'dialog#help', 'crudulator'),
    ('mindmap-editor.html', '#bHelp', '#dlg', 'mindmap-editor'),
]


@pytest.mark.parametrize('tool, button, dialog, folder', TOOLS)
def test_help_links_to_the_tools_documentation(page, server, tool, button, dialog, folder):
    if LOCAL_LIBS:
        _use_local_libs(page)
    page.goto(f'{server}/{tool}')
    page.click(button)
    link = page.locator(dialog).get_by_role('link', name='Full documentation')
    assert link.get_attribute('href') == f'{SITE}{folder}/'
    assert link.get_attribute('target') == '_blank'
    assert (ROOT / folder / 'index.md').exists()
