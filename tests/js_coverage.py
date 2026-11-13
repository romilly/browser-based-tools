"""JavaScript coverage for the tools, measured by Chromium while the Playwright tests run.

    pytest --js-coverage

prints a table for the <script> blocks in the repo's HTML files and writes a report to
js-coverage/index.html, with the code that never ran highlighted.

Chromium reports character ranges that ran or didn't. A line counts as covered if any of it ran;
blank lines and // comment lines aren't counted. Chromium doesn't list functions defined inside
a function that was never called, so the function counts can be a little low.
"""
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

SCRIPT = re.compile(r'<script>(.*?)</script>', re.S)


@dataclass
class FileReport:
    lines: int = 0
    covered_lines: int = 0
    uncovered_lines: list = field(default_factory=list)
    functions: int = 0
    uncovered_functions: list = field(default_factory=list)   # (name, line)

    @property
    def percent(self):
        return round(100 * self.covered_lines / self.lines) if self.lines else 100


class JsCoverage:
    def __init__(self, root):
        self.text = {p.name: p.read_text(encoding='utf-8') for p in sorted(Path(root).glob('*.html'))}
        self.ran = {name: bytearray(len(text)) for name, text in self.text.items()}   # 1 per character that ran
        self.called = {name: {} for name in self.text}          # (start, name) -> was it ever called
        self._places = {}

    def _place(self, source):
        """Where a script sits in a repo file: (file name, start, position of each UTF-16 unit)."""
        if source not in self._places:
            found = None
            for name, text in self.text.items():
                at = text.find(source) if source.strip() else -1
                if at >= 0:
                    units = [0]
                    for i, ch in enumerate(source):
                        units += [i + 1] * (2 if ord(ch) > 0xFFFF else 1)
                    found = name, at, units
                    break
            self._places[source] = found
        return self._places[source]

    def add(self, source, functions):
        """Add Chromium's report for one script: its source and its list of function ranges."""
        place = self._place(source)
        if not place:
            return
        name, base, units = place
        ran = bytearray(len(source))
        ranges = []
        for f in functions:
            first = f['ranges'][0]
            start, end = units[first['startOffset']], units[first['endOffset']]
            if (start, end) != (0, len(source)):        # the script itself is listed as a function
                key = base + start, f['functionName'] or '(anonymous)'
                self.called[name][key] = self.called[name].get(key, False) or first['count'] > 0
            ranges += [(units[r['startOffset']], units[r['endOffset']], r['count']) for r in f['ranges']]
        for start, end, count in sorted(ranges, key=lambda r: (r[0], -r[1])):    # inner ranges last
            ran[start:end] = (b'\1' if count else b'\0') * (end - start)
        old = self.ran[name][base:base + len(source)]
        both = int.from_bytes(old, 'big') | int.from_bytes(ran, 'big')
        self.ran[name][base:base + len(source)] = both.to_bytes(len(source), 'big')

    def _script_lines(self, name):
        """(line number, start, end) for each line of the file's scripts that holds code."""
        text = self.text[name]
        for m in SCRIPT.finditer(text):
            at = m.start(1)
            number = text.count('\n', 0, at) + 1
            for line in m.group(1).split('\n'):
                code = line.strip()
                if code and not code.startswith('//'):
                    yield number, at + len(line) - len(line.lstrip()), at + len(line.rstrip())
                at += len(line) + 1
                number += 1

    def report(self):
        result = {}
        for name, text in self.text.items():
            r = FileReport()
            for number, start, end in self._script_lines(name):
                r.lines += 1
                if any(self.ran[name][start:end]):
                    r.covered_lines += 1
                else:
                    r.uncovered_lines.append(number)
            r.functions = len(self.called[name])
            r.uncovered_functions = [(fn, text.count('\n', 0, start) + 1)
                                     for (start, fn), called in sorted(self.called[name].items()) if not called]
            result[name] = r
        return result

    def table(self):
        rows = [f'{"File":<24}{"Lines":>7}{"Missed":>8}{"Cover":>7}   {"Functions":>9}{"Never called":>14}']
        for name, r in self.report().items():
            rows.append(f'{name:<24}{r.lines:>7}{r.lines - r.covered_lines:>8}{r.percent:>6}%   '
                        f'{r.functions:>9}{len(r.uncovered_functions):>14}')
        return '\n'.join(rows)

    def write_html(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        style = ('<style>body{font:14px/1.45 system-ui,sans-serif;margin:2rem;max-width:70rem}'
                 'pre{font:12.5px/1.45 ui-monospace,monospace}mark{background:#ffd0d0}'
                 'td,th{padding:.2rem .8rem;text-align:right}td:first-child,th:first-child{text-align:left}'
                 '.n{color:#999;user-select:none}li code{color:#666;margin-left:.5rem}</style>')
        rows = []
        for name, r in self.report().items():
            rows.append(f'<tr><td><a href="{name}.html">{name}</a></td><td>{r.lines}</td>'
                        f'<td>{r.lines - r.covered_lines}</td><td>{r.percent}%</td>'
                        f'<td>{r.functions}</td><td>{len(r.uncovered_functions)}</td></tr>')
            source = self.text[name].split('\n')
            never = ''.join(f'<li><a href="#L{line}">{html.escape(fn)}</a> (line {line}) '
                            f'<code>{html.escape(source[line - 1].strip()[:90])}</code></li>'
                            for fn, line in r.uncovered_functions)
            (folder / f'{name}.html').write_text(
                f'<!doctype html><meta charset="utf-8"><title>{name} coverage</title>{style}'
                f'<p><a href="index.html">All files</a></p><h1>{name}</h1>'
                f'<p>{r.percent}% of {r.lines} script lines ran. Code that never ran is highlighted.</p>'
                f'<h2>Functions never called ({len(r.uncovered_functions)} of {r.functions})</h2><ul>{never}</ul>'
                f'<h2>Source</h2><pre>{self._marked(name)}</pre>', encoding='utf-8')
        (folder / 'index.html').write_text(
            f'<!doctype html><meta charset="utf-8"><title>JavaScript coverage</title>{style}'
            '<h1>JavaScript coverage</h1><table><tr><th>File</th><th>Lines</th><th>Missed</th><th>Cover</th>'
            f'<th>Functions</th><th>Never called</th></tr>{"".join(rows)}</table>', encoding='utf-8')

    def _marked(self, name):
        """The file as HTML text, numbered, with <mark> round script code that never ran."""
        text, ran = self.text[name], self.ran[name]
        missed = bytearray(len(text))
        for _, start, end in self._script_lines(name):
            for i in range(start, end):
                missed[i] = not ran[i] and not text[i].isspace()
        out, at = [], 0
        for number, line in enumerate(text.split('\n'), 1):
            parts, i = [], 0
            while i < len(line):
                j = i
                if missed[at + i]:
                    while j < len(line) and (missed[at + j] or line[j].isspace()):
                        j += 1
                    piece = line[i:j].rstrip()
                    j = i + len(piece)
                    parts.append(f'<mark>{html.escape(piece)}</mark>')
                else:
                    while j < len(line) and not missed[at + j]:
                        j += 1
                    parts.append(html.escape(line[i:j]))
                i = j
            out.append(f'<span class="n" id="L{number}">{number:>5}  </span>{"".join(parts)}')
            at += len(line) + 1
        return '\n'.join(out)


def watch(page, coverage):
    """Start measuring on a Playwright page (Chromium only). Returns a function that stops
    and adds what ran to `coverage`."""
    session = page.context.new_cdp_session(page)
    sources = {}

    def parsed(event):
        if event['url'] and not urlparse(event['url']).path.endswith('.js'):
            sources[event['scriptId']] = None

    session.on('Debugger.scriptParsed', parsed)
    session.send('Debugger.enable')
    session.send('Debugger.setSkipAllPauses', {'skip': True})
    session.send('Profiler.enable')
    session.send('Profiler.startPreciseCoverage', {'callCount': False, 'detailed': True})

    def collect():
        for script in session.send('Profiler.takePreciseCoverage')['result']:
            if script['scriptId'] in sources:
                source = session.send('Debugger.getScriptSource', {'scriptId': script['scriptId']})['scriptSource']
                coverage.add(source, script['functions'])

    def collect_first(navigate):
        def wrapper(*args, **kwargs):
            collect()               # Chromium forgets a document's coverage when the page leaves it
            return navigate(*args, **kwargs)
        return wrapper

    page.goto, page.reload = collect_first(page.goto), collect_first(page.reload)

    def stop():
        collect()
        session.detach()

    return stop
