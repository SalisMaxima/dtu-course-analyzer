"""Manual browser smoke checks: python tests/extension_ui_smoke.py [--chrome PATH].

Uses actual extension markup/scripts and bundled data with a local host fixture
and a chrome.storage adapter. Does not install into the user's browser profile.
Requires Playwright; browser output goes to --output (default: a temporary folder).
"""
import argparse
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
MOCK = """(() => {
  const listeners = [];
  window.chrome = {
    runtime: {getURL: path => 'https://review.local/extension/' + path,
      sendMessage: (message, callback) => {window.lastExtensionMessage = message; callback();}},
    storage: {
      local: {
        get: (key, callback) => {
          if (window.storageReadError) chrome.runtime.lastError = {message:'Storage unavailable'};
          callback({[key]:JSON.parse(localStorage.getItem(key) || '[]')});
          delete chrome.runtime.lastError;
        },
        set: (items, callback) => {
          if (window.storageWriteError) {
            chrome.runtime.lastError = {message:'Storage unavailable'};
            callback(); delete chrome.runtime.lastError; return;
          }
          const changes = {};
          for (const [key, value] of Object.entries(items)) {
            changes[key] = {newValue:value}; localStorage.setItem(key, JSON.stringify(value));
          }
          callback(); listeners.forEach(fn => fn(changes, 'local'));
        }
      },
      onChanged: {addListener: callback => listeners.push(callback)}
    }
  };
  window.addEventListener('storage', event => {
    if (event.key) listeners.forEach(fn => fn({[event.key]:{newValue:JSON.parse(event.newValue || '[]')}}, 'local'));
  });
})();"""
FIXTURE = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font:14px Arial;margin:16px}.box{max-width:370px}table{background:rgb(240,240,240)}td{padding:3px}h2{font-size:24px}button{border-radius:0}</style>
</head><body><main><h2>Course information</h2><div class="box information"><table id="host-table"><tr><td>Host course details</td></tr></table></div></main></body></html>"""


def run(chrome, output):
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome, headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.add_init_script(MOCK)
        errors = []
        context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))

        def route(request):
            path = request.request.url.split('review.local/')[-1].split('?')[0]
            if path.startswith('course/'):
                request.fulfill(content_type='text/html', body=FIXTURE)
            else:
                file = ROOT / path
                if file.is_file():
                    headers = {'Content-Security-Policy': "script-src 'self'; object-src 'self'"} if path.endswith('db.html') else {}
                    request.fulfill(path=str(file), headers=headers)
                else:
                    request.fulfill(status=404, body='Not found')

        context.route('https://review.local/**', route)
        page = context.new_page()
        page.goto('https://review.local/extension/db.html')
        expect(page.locator('#course-tbody tr')).to_have_count(50)
        expect(page.locator('#view-comparison')).to_be_enabled()
        expect(page.locator('#comparison-panel')).to_be_hidden()
        expect(page.locator('#prev-page')).to_be_disabled()
        first_course = page.locator('#course-tbody tr').first.locator('a').inner_text()
        page.locator('#next-page').click()
        assert first_course != page.locator('#course-tbody tr').first.locator('a').inner_text()
        page.locator('#prev-page').click()
        assert first_course == page.locator('#course-tbody tr').first.locator('a').inner_text()
        page.locator('[data-key="avg"] button').focus()
        page.keyboard.press('Enter')
        expect(page.locator('[data-key="avg"]')).to_have_attribute('aria-sort', 'descending')
        values = page.locator('#course-tbody tr td:nth-child(4)').all_text_contents()
        assert list(map(float, values)) == sorted(map(float, values), reverse=True)
        page.locator('#search-input').fill('no-such-course')
        expect(page.locator('#course-tbody')).to_contain_text('No courses match')
        page.locator('#search-input').fill('12143')
        page.get_by_role('button', name='Add 12143 to comparison').click()
        expect(page.locator('#view-comparison')).to_have_text('Compare (1/4)')
        assert page.evaluate('document.activeElement.dataset.focusKey') == '12143'
        page.locator('#search-input').fill('41927')
        page.get_by_role('button', name='Add 41927 to comparison').click()
        page.locator('#search-input').fill('')
        page.reload()
        expect(page.locator('#view-comparison')).to_have_text('Compare (2/4)')
        page.locator('#lang-da').click()
        expect(page.locator('#lang-da')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#comparison-table')).to_contain_text('Åben Bygningsinformationsmodellering')
        page.locator('#lang-en').click()
        page.locator('#comparison-title').click()
        assert not page.locator('#comparison-panel').evaluate('(node) => node.open')
        page.locator('#view-comparison').click()
        assert page.locator('#comparison-panel').evaluate('(node) => node.open')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(output / 'database.png'))

        other = context.new_page()
        other.goto('https://review.local/extension/db.html')
        expect(other.locator('#view-comparison')).to_have_text('Compare (2/4)')
        for course in ['01001', '01002']:
            page.locator('#search-input').fill(course)
            page.get_by_role('button', name=f'Add {course} to comparison').click()
        expect(other.locator('#view-comparison')).to_have_text('Compare (4/4)')
        page.locator('#search-input').fill('01017')
        page.get_by_role('button', name='Add 01017 to comparison').click()
        expect(page.locator('#comparison-status')).to_contain_text('Maximum 4')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth') == 390
        page.screenshot(path=str(output / 'narrow.png'))
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.evaluate('window.storageWriteError = true')
        page.locator('#clear-comparison').click()
        expect(page.locator('#comparison-status')).to_contain_text('Could not save')
        expect(page.locator('#view-comparison')).to_have_text('Compare (4/4)')
        page.evaluate('window.storageWriteError = false')
        page.locator('#clear-comparison').click()
        expect(other.locator('#view-comparison')).to_have_text('Compare (0/4)')

        panel = context.new_page()
        panel.goto('https://review.local/course/12143')
        before = panel.locator('#host-table').evaluate('(node) => getComputedStyle(node).backgroundColor')
        panel.add_style_tag(path=str(ROOT / 'extension/css/analyzer.css'))
        panel.add_script_tag(path=str(ROOT / 'extension/js/course-utils.js'))
        panel.add_script_tag(path=str(ROOT / 'extension/contentscript.js'))
        expect(panel.locator('#DTU-Course-Analyzer')).to_be_visible()
        assert panel.locator('#host-table').evaluate('(node) => getComputedStyle(node).backgroundColor') == before
        expect(panel.locator('#DTU-Course-Analyzer .metric-value')).to_have_count(6)
        assert panel.locator('.bar').first.evaluate('(node) => node.getBoundingClientRect().height') == 0
        panel.get_by_role('button', name='Add to comparison', exact=True).click()
        expect(other.locator('#view-comparison')).to_have_text('Compare (1/4)')
        panel.get_by_role('button', name='View comparison (1/4)').click()
        assert panel.evaluate('window.lastExtensionMessage.type') == 'openComparison'
        panel.set_viewport_size({'width': 390, 'height': 1000})
        assert panel.evaluate('document.documentElement.scrollWidth') == 390
        panel.screenshot(path=str(output / 'course-panel.png'), full_page=True)
        panel.set_viewport_size({'width': 320, 'height': 1000})
        assert panel.evaluate('document.documentElement.scrollWidth') == 320
        # Duplicate insertion, missing values and zero values.
        panel.evaluate('presentData({}, "12143")')
        expect(panel.locator('#DTU-Course-Analyzer')).to_have_count(1)
        panel.evaluate('document.getElementById("DTU-Course-Analyzer").remove(); presentData({avg:0}, "99999")')
        expect(panel.locator('#DTU-Course-Analyzer .metric-value')).to_have_count(1)
        expect(panel.locator('#DTU-Course-Analyzer [aria-label="No data"]')).to_have_count(5)
        panel.evaluate('document.getElementById("DTU-Course-Analyzer").remove(); presentData(null, "99999")')
        expect(panel.locator('#DTU-Course-Analyzer')).to_contain_text('No data found')
        panel.evaluate('document.getElementById("DTU-Course-Analyzer").remove(); presentData(null, "99999", "HTTP 500")')
        expect(panel.locator('#DTU-Course-Analyzer')).to_contain_text('could not be loaded')

        unavailable = context.new_page()
        unavailable.add_init_script('window.storageReadError = true')
        unavailable.goto('https://review.local/extension/db.html')
        expect(unavailable.locator('#comparison-status')).to_contain_text('unavailable')
        expect(unavailable.locator('#course-tbody tr')).to_have_count(50)
        expect(unavailable.locator('#course-tbody button').first).to_be_disabled()
        failed = context.new_page()
        failed.route('**/db/data.json', lambda route: route.fulfill(status=500, body='Failed'))
        failed.goto('https://review.local/extension/db.html')
        expect(failed.locator('#course-tbody')).to_contain_text('could not be loaded')
        expect(failed.locator('#search-input')).to_be_disabled()
        assert not errors, errors
        browser.close()
    print('Passed: full-dataset pagination, keyboard sorting, search, language, score rendering, persistence, cross-tab sync, comparison limit, focus, collapse, errors, panel actions, style isolation and 320/390px layouts.')
    print(f'Screenshots: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome', default='/usr/bin/google-chrome')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    run(args.chrome, args.output or Path(tempfile.mkdtemp(prefix='dtu-ui-smoke-')))
