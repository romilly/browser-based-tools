"""JavaScript coverage for the tools (tests/js_coverage.py): which lines and functions of the
<script> blocks in the repo's HTML files ran, as reported by Chromium."""
from js_coverage import JsCoverage, watch

PAGE = '''<!doctype html>
<html><body><p>function not_script() {}</p>
<script>
// a comment
function used() {
  return 1;
}

function unused() {
  return 2;
}
used();
</script>
</body></html>
'''


def make(tmp_path, text=PAGE, name='tool.html'):
    (tmp_path / name).write_text(text, encoding='utf-8')
    return JsCoverage(tmp_path)


def script_of(text):
    return text.split('<script>')[1].split('</script>')[0]


def fn(source, name, count, *blocks):
    """A function's entry as Chromium reports it: its own range first, then blocks inside it.
    Offsets count UTF-16 units, as JavaScript does."""
    def units(s):
        return len(s.encode('utf-16-le')) // 2

    def span(piece, n):
        at = source.index(piece)
        return {'startOffset': units(source[:at]), 'endOffset': units(source[:at + len(piece)]), 'count': n}

    whole = source if not name else source[source.index(f'function {name}('):]
    if name:
        whole = whole[:whole.index('\n}') + 2]
    return {'functionName': name, 'ranges': [span(whole, count)] + [span(p, n) for p, n in blocks]}


def test_a_file_that_no_test_loaded_is_reported_with_nothing_covered(tmp_path):
    report = make(tmp_path).report()['tool.html']
    assert (report.lines, report.covered_lines) == (7, 0)      # blank and comment lines don't count
    assert report.percent == 0


def test_an_uncalled_function_is_listed_with_its_line_in_the_file(tmp_path):
    cov = make(tmp_path)
    src = script_of(PAGE)
    cov.add(src, [fn(src, '', 1), fn(src, 'used', 1), fn(src, 'unused', 0)])
    report = cov.report()['tool.html']
    assert report.uncovered_functions == [('unused', 9)]
    assert report.functions == 2
    assert report.uncovered_lines == [9, 10, 11]
    assert (report.lines, report.covered_lines) == (7, 4)
    assert report.percent == 57


def test_coverage_adds_up_over_tests(tmp_path):
    cov = make(tmp_path)
    src = script_of(PAGE)
    cov.add(src, [fn(src, '', 1), fn(src, 'used', 1), fn(src, 'unused', 0)])
    cov.add(src, [fn(src, '', 1), fn(src, 'used', 0), fn(src, 'unused', 1)])
    report = cov.report()['tool.html']
    assert report.uncovered_functions == []
    assert report.percent == 100


BRANCHY = '''<script>
function pick(a) {
  if (a) {
    return 1;
  }
  return 2;
}
pick(0);
</script>
'''


def test_a_block_that_never_ran_inside_a_called_function(tmp_path):
    cov = make(tmp_path, BRANCHY)
    src = script_of(BRANCHY)
    cov.add(src, [fn(src, '', 1), fn(src, 'pick', 1, ('{\n    return 1;\n  }', 0))])
    report = cov.report()['tool.html']
    assert report.uncovered_functions == []
    assert report.uncovered_lines == [4, 5]     # line 3 ran in part, so it counts as covered


EMOJI = '''<script>
const faces = '😀😀😀😀😀😀';
function unused() {}
const after = 1;
</script>
'''


def test_emoji_do_not_shift_the_positions(tmp_path):
    cov = make(tmp_path, EMOJI)
    src = script_of(EMOJI)
    cov.add(src, [fn(src, '', 1), {'functionName': 'unused', 'ranges': [
        {'startOffset': len(src[:src.index('function')].encode('utf-16-le')) // 2,
         'endOffset': len(src[:src.index('{}') + 2].encode('utf-16-le')) // 2, 'count': 0}]}])
    assert cov.report()['tool.html'].uncovered_lines == [3]


def test_scripts_that_are_not_in_the_repo_are_ignored(tmp_path):
    cov = make(tmp_path)
    cov.add('function library() {}', [{'functionName': 'library', 'ranges': [
        {'startOffset': 0, 'endOffset': 21, 'count': 0}]}])
    assert cov.report()['tool.html'].functions == 0


def test_anonymous_functions_are_named_by_what_they_are(tmp_path):
    text = '<script>\nconst f = [1].map(x => x + 1);\n</script>\n'
    cov = make(tmp_path, text)
    src = script_of(text)
    at = src.index('x =>')
    cov.add(src, [fn(src, '', 1), {'functionName': '', 'ranges': [
        {'startOffset': at, 'endOffset': src.index(')') , 'count': 0}]}])
    assert cov.report()['tool.html'].uncovered_functions == [('(anonymous)', 2)]


def test_html_report_marks_what_did_not_run(tmp_path):
    cov = make(tmp_path)
    src = script_of(PAGE)
    cov.add(src, [fn(src, '', 1), fn(src, 'used', 1), fn(src, 'unused', 0)])
    out = tmp_path / 'report'
    cov.write_html(out)
    index = (out / 'index.html').read_text(encoding='utf-8')
    assert 'tool.html' in index and '57%' in index
    page = (out / 'tool.html.html').read_text(encoding='utf-8')
    assert '<mark>function unused() {' in page
    assert '<mark>function used' not in page
    assert '&lt;script&gt;' in page             # the file's own HTML is shown as text


# --- with a real browser ---

LIVE = '''<!doctype html>
<html><body>
<button id="a" onclick="first()">a</button>
<button id="b" onclick="second()">b</button>
<script>
function first() {
  document.title = 'first';
}
function second() {
  document.title = 'second';
}
function never() {
  document.title = 'never';
}
</script>
</body></html>
'''


def test_chromium_reports_what_ran_on_a_page(page, tmp_path):
    cov = make(tmp_path, LIVE)
    stop = watch(page, cov)
    page.goto((tmp_path / 'tool.html').as_uri())
    page.click('#a')
    stop()
    assert cov.report()['tool.html'].uncovered_functions == [('second', 9), ('never', 12)]


def test_what_ran_before_a_reload_still_counts(page, tmp_path):
    cov = make(tmp_path, LIVE)
    stop = watch(page, cov)
    page.goto((tmp_path / 'tool.html').as_uri())
    page.click('#a')
    page.reload()
    page.click('#b')
    stop()
    assert cov.report()['tool.html'].uncovered_functions == [('never', 12)]
