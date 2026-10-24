#!/usr/bin/env node
// G1 real-DOM regression and visual matrix. Use an isolated workspace server.
// All credential/integration status and results are synthetic. No real task is submitted.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
    CdpClient, locateChrome, waitForDevToolsPort, findPageTarget,
    evaluate, waitFor, navigateAndWait, capture, sleep,
} from './capture_readme_screenshots.mjs';

const [url, output] = process.argv.slice(2);
if (!url || !output || new URL(url).hostname !== '127.0.0.1') {
    throw new Error('Usage: node scripts/verify_g1_browser.mjs http://127.0.0.1:<isolated-port>/ <evidence-directory>');
}
const evidenceDir = path.resolve(output);
fs.mkdirSync(evidenceDir, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'v2k-g1-browser-'));
const fixtures = `(() => {
    const original = window.fetch.bind(window);
    window.__g1Forbidden = [];
    window.__g1Calls = [];
    window.__g1DownloadKind = 'md';
    window.__g1Errors = [];
    // This installed browser asynchronously adds wfd-invisible to MathML annotations.
    // Ignore only that observed decoration on a clone; compare all formula content/styles.
    window.__g1MathMarkup = () => {
        const formula = document.getElementById('markdownContent').querySelector('.katex').cloneNode(true);
        formula.querySelectorAll('annotation[wfd-invisible]').forEach(node => node.removeAttribute('wfd-invisible'));
        return formula.outerHTML;
    };
    window.addEventListener('error', e => window.__g1Errors.push(e.message));
    window.addEventListener('unhandledrejection', e => window.__g1Errors.push(String(e.reason)));
    const fixture = {
        '/api/llm-keys': {storage: {secure: true}, match: null},
        '/api/integrations/note-destinations': {obsidian: {status: 'missing', vaults: []}, feishu: {status: 'missing'}},
        '/api/whisper-models': {models: [{id: 'small', status: 'cached'}]},
        '/api/bili-login/status': {status: 'idle'},
        '/api/douyin-login/status': {status: 'idle'},
    };
    window.fetch = async (input, options = {}) => {
        const target = new URL(typeof input === 'string' ? input : input.url, location.href);
        const route = target.pathname;
        const method = options.method || 'GET';
        window.__g1Calls.push({route, method});
        if (target.origin === location.origin && method === 'GET') {
            if (Object.hasOwn(fixture, route)) return Response.json(fixture[route]);
            if (['/api/health', '/api/tasks', '/api/note-templates'].includes(route)) return original(input, options);
            if (route === '/api/download/g1-synthetic') {
                const kind = window.__g1DownloadKind;
                return new Response('synthetic fixture', {headers: {
                    'Content-Type': kind === 'zip' ? 'application/zip' : 'text/markdown',
                    'Content-Disposition': 'attachment; filename="synthetic.' + kind + '"'
                }});
            }
        }
        window.__g1Forbidden.push({route, method});
        throw new Error('G1 blocked non-allowlisted request');
    };
})();`;

const sample = [
    '# 合成阅读验收', '',
    '<p id="v2k-reader-heading-1">保留的普通段落</p>', '',
    '## 重复标题', '',
    '跨**格式**查找，与普通格式查找都要匹配。', '',
    'English CASE check; literal [a+b].', '',
    '$E=mc^2$', '',
    '![合成图片](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jR1sAAAAASUVORK5CYII=)', '',
    '## 重复标题', '',
    '<h3 id="settingsPanel"><img src="x" onerror="window.__g1Xss=1">恶意标题&lt;script&gt;</h3>', '',
    '<script>window.__g1Xss=2</script>', '',
    '```text', '格式查找 code', '```', '',
    ...Array.from({length: 18}, (_, i) => `普通段落 ${i + 1}：阅读器只处理合成内容，不调用模型。`),
].join(String.fromCharCode(10));

let proc;
let cdp;
const results = [];
async function key(name, code) {
    await cdp.send('Input.dispatchKeyEvent', {type: 'keyDown', key: name, code: name,
        ...(name === 'Enter' ? {text: '\r'} : {}), windowsVirtualKeyCode: code});
    await cdp.send('Input.dispatchKeyEvent', {type: 'keyUp', key: name, code: name, windowsVirtualKeyCode: code});
}
function luminance(cssColor) {
    const rgb = cssColor.match(/[\d.]+/g).slice(0, 3).map(Number).map(channel => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
try {
    proc = spawn(locateChrome(), [
        '--headless=new', '--disable-gpu', '--disable-background-networking',
        '--no-first-run', '--no-default-browser-check', '--disable-extensions',
        '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
    ], {stdio: 'ignore', windowsHide: true});
    const port = await waitForDevToolsPort(profile, proc);
    cdp = new CdpClient((await findPageTarget(port)).webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', {source: fixtures});
    for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]]) {
        for (const theme of ['light', 'dark', 'system']) {
            const name = `${width}-${theme}`;
            await cdp.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: false});
            await cdp.send('Emulation.setEmulatedMedia', {features: [
                {name: 'prefers-color-scheme', value: theme === 'light' ? 'light' : 'dark'},
                {name: 'prefers-reduced-motion', value: 'reduce'},
            ]});
            await navigateAndWait(cdp, url);
            await waitFor(cdp, 'window.__videoToNoReady === true && noteTemplatesStatus === "ready"');
            await evaluate(cdp, `document.querySelector('[data-theme-option="${theme}"]').click(); window.scrollTo(0, 0); true`);
            const home = await evaluate(cdp, `(() => {
                const source = byId('videoUrl').getBoundingClientRect();
                const submit = byId('submitBtn').getBoundingClientRect();
                return {sourceBottom: source.bottom, submitBottom: submit.bottom,
                    sourceBeforeTemplates: Boolean(byId('videoUrl').compareDocumentPosition(byId('templateCards')) & Node.DOCUMENT_POSITION_FOLLOWING),
                    previewCollapsed: !byId('templatePreviewDetails').open,
                    count: byId('templateCards').children.length,
                    noOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
                    themeSelected: document.querySelector('[data-theme-option="${theme}"]').getAttribute('aria-pressed')};
            })()`);
            assert.equal(home.sourceBeforeTemplates, true, name);
            assert.equal(home.previewCollapsed, true, name);
            assert.ok(home.count >= 6, name);
            assert.equal(home.themeSelected, 'true');
            assert.equal(home.noOverflow, true);
            assert.ok(home.sourceBottom > 0 && home.sourceBottom < height, `${name}: source below fold`);
            assert.ok(home.submitBottom > 0 && home.submitBottom < height, `${name}: start below fold`);
            await capture(cdp, path.join(evidenceDir, `${name}-home.png`));

            // Every built-in and a custom card remain selectable; rebuilt cards retain focus.
            await evaluate(cdp, `(() => {
                const ids = noteTemplates.map(t => t.id);
                for (const id of ids) {
                    Array.from(byId('templateCards').children).find(c => c.dataset.templateId === id).click();
                    if (byId('noteTemplate').value !== id || document.activeElement.dataset.templateId !== id) throw Error('card focus/sync');
                }
                noteTemplates.push({id: 'custom-g1', name: '合成自定义模板', preview_markdown: '# 自定义示例', built_in: false});
                renderNoteTemplateOptions('custom-g1');
                byId('templateCards').lastElementChild.click();
                if (byId('noteTemplate').value !== 'custom-g1') throw Error('custom card');
                byId('templatePreviewToggle').focus();
                return true;
            })()`);
            await key('Enter', 13);
            assert.equal(await evaluate(cdp, 'byId("templatePreviewDetails").open'), true);
            await evaluate(cdp, 'byId("templatePreviewSourceBtn").focus(); true');
            await key('Escape', 27);
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'templatePreviewToggle');
            assert.equal(await evaluate(cdp, 'byId("templatePreviewDetails").open'), false);
            await evaluate(cdp, 'byId("manageTemplatesBtn").click(); true');
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'noteTemplate');
            await key('Escape', 27);
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'manageTemplatesBtn');
            await evaluate(cdp, `setOutputMode('transcript'); true`);
            assert.equal(await evaluate(cdp, 'byId("noteWorkflowOptions").hidden'), true);
            await evaluate(cdp, `setOutputMode('note'); true`);

            await evaluate(cdp, `(async () => {
                currentTaskId = 'g1-synthetic';
                window.__g1Source = ${JSON.stringify(sample)};
                await showResult({output: 'note', markdown: window.__g1Source,
                    archived_path: 'workspace/notes/合成阅读验收.md', output_directory: 'workspace/g1-synthetic'});
                window.__g1Math = __g1MathMarkup();
                window.__g1Images = Array.from(byId('markdownContent').querySelectorAll('img')).map(i => i.outerHTML);
                window.__g1RenderedText = byId('markdownContent').textContent;
                return true;
            })()`);
            const outline = await evaluate(cdp, `(() => {
                const list = byId('resultOutlineList');
                const links = Array.from(list.querySelectorAll('a'));
                return {ids: links.map(a => a.getAttribute('href')), names: links.map(a => a.textContent),
                    mobileCollapsed: !byId('resultOutline').open, xss: Boolean(window.__g1Xss),
                    badAttrs: byId('markdownContent').querySelectorAll('script, [onerror]').length};
            })()`);
            assert.equal(outline.ids.length, 4, await evaluate(cdp, `JSON.stringify({html: byId('markdownContent').innerHTML.slice(0, 1200), source: window.__g1Source.slice(0, 120), marked: typeof marked, purify: typeof DOMPurify})`));
            assert.equal(new Set(outline.ids).size, 4);
            assert.equal(outline.names.filter(s => s === '重复标题').length, 2);
            assert.equal(outline.xss, false);
            assert.equal(outline.badAttrs, 0);
            if (width === 390) assert.equal(outline.mobileCollapsed, true);
            await evaluate(cdp, `byId('resultOutline').open = true; byId('resultOutlineList').children[2].querySelector('a').click(); true`);
            const target = await evaluate(cdp, `({text: document.activeElement.textContent,
                top: document.activeElement.getBoundingClientRect().top,
                headerBottom: document.querySelector('.app-bar').getBoundingClientRect().bottom})`);
            assert.equal(target.text, '重复标题');
            assert.ok(target.top >= target.headerBottom, name + ': heading hidden behind header');

            const search = await evaluate(cdp, `(() => {
                const input = byId('noteSearch');
                input.value = '格式查找'; input.dispatchEvent(new Event('input'));
                const count = noteMatches.length;
                const pieces = noteMatches[0].map(m => m.textContent).join('');
                byId('noteSearchNextBtn').click();
                const afterNext = noteMatchIndex;
                byId('noteSearchPrevBtn').click();
                input.focus();
                return {count, pieces, afterNext, index: noteMatchIndex, status: byId('noteSearchStatus').textContent};
            })()`);
            assert.equal(search.count, 3);
            assert.equal(search.pieces, '格式查找');
            assert.equal(search.afterNext, 1);
            assert.equal(search.index, 0);
            // Flush the frame after scroll/focus before sampling painted highlight colors.
            await cdp.send('Page.captureScreenshot', {format: 'png'});
            const colors = await evaluate(cdp, `(() => {
                const style = getComputedStyle(noteMatches[0][0]);
                return {foreground: style.color, background: style.backgroundColor};
            })()`);
            const lightness = [luminance(colors.foreground), luminance(colors.background)].sort((a, b) => a - b);
            assert.ok((lightness[1] + 0.05) / (lightness[0] + 0.05) >= 4.5, name + ': highlight contrast ' + JSON.stringify({colors, lightness}));
            await key('Tab', 9);
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'noteSearchPrevBtn');
            assert.equal(await evaluate(cdp, "document.activeElement.matches(':focus-visible') && getComputedStyle(document.activeElement).outlineStyle !== 'none'"), true);
            await evaluate(cdp, 'byId("noteSearch").focus(); true');
            await key('Enter', 13);
            assert.equal(await evaluate(cdp, 'noteMatchIndex'), 1);
            await key('Escape', 27);
            assert.equal(await evaluate(cdp, 'noteMatches.length'), 0);
            const literals = await evaluate(cdp, `(() => {
                const counts = {};
                for (const query of ['case', '[a+b]', '<script>', 'not-present', 'E=mc']) {
                    byId('noteSearch').value = query; searchNote(); counts[query] = noteMatches.length;
                }
                return counts;
            })()`);
            assert.deepEqual(literals, {'case': 1, '[a+b]': 1, '<script>': 1, 'not-present': 0, 'E=mc': 0});
            await evaluate(cdp, `byId('noteSearch').value = '格式查找'; searchNote(); byId('resultReaderTools').scrollIntoView({block: 'start'}); true`);
            await capture(cdp, path.join(evidenceDir, `${name}-reader.png`));
            assert.equal(await evaluate(cdp, 'document.documentElement.scrollWidth <= document.documentElement.clientWidth'), true);
            const preserved = await evaluate(cdp, `(() => {
                clearNoteSearch(false);
                return {source: currentMarkdown === window.__g1Source,
                    math: __g1MathMarkup() === window.__g1Math,
                    images: JSON.stringify(Array.from(byId('markdownContent').querySelectorAll('img')).map(i => i.outerHTML)) === JSON.stringify(window.__g1Images),
                    text: byId('markdownContent').textContent === window.__g1RenderedText,
                    marks: byId('markdownContent').querySelectorAll('mark.note-search-match').length,
                    htmlExport: !convertToHtml(currentHtml).includes('note-search-match')};
            })()`);
            assert.deepEqual(preserved, {source: true, math: true, images: true, text: true, marks: 0, htmlExport: true},
                preserved.math ? name : await evaluate(cdp, `JSON.stringify({name: '${name}', mathBefore: __g1Math, mathAfter: byId('markdownContent').querySelector('.katex').outerHTML})`));
            // Exercise the real copy/download handlers, intercepting only the side-effect sink.
            const exportResult = await evaluate(cdp, `(async () => {
                let copied;
                const oldCopy = copyTextToClipboard;
                const oldDownload = triggerBlobDownload;
                copyTextToClipboard = async value => { copied = value; };
                const downloads = [];
                triggerBlobDownload = (blob, extension, filename) => downloads.push({filename, type: blob.type});
                try {
                    byId('noteSearch').value = '格式查找'; searchNote();
                    await copyFullNote();
                    window.__g1DownloadKind = 'zip'; await downloadMarkdownFile();
                    const zipHint = byId('resultExportHint').textContent;
                    window.__g1DownloadKind = 'md'; await downloadMarkdownFile();
                    return {copied: copied === window.__g1Source, downloads, zipHint, mdHint: byId('resultExportHint').textContent};
                } finally { copyTextToClipboard = oldCopy; triggerBlobDownload = oldDownload; }
            })()`);
            assert.equal(exportResult.copied, true);
            assert.deepEqual(exportResult.downloads.map(d => d.filename), ['synthetic.zip', 'synthetic.md']);
            assert.match(exportResult.zipHint, /已下载 ZIP/);
            assert.match(exportResult.mdHint, /已下载 .md/);

            // Large match counts are bounded, and opening another task clears old state.
            const resets = await evaluate(cdp, `(async () => {
                await showResult({output: 'note', markdown: '# 长合成笔记\\n\\n' + '测试 '.repeat(250)});
                byId('noteSearch').value = '测试'; searchNote();
                const limit = {count: noteMatches.length, limited: noteMatchesLimited, status: byId('noteSearchStatus').textContent};
                await showResult({output: 'transcript', markdown: '# 字幕\\n[00:00] 合成字幕'});
                byId('noteSearch').value = '合成'; searchNote();
                return {limit, transcript: noteMatches.length, outlineHidden: byId('resultOutline').hidden,
                    noOldHighlights: !byId('markdownContent').textContent.includes('测试')};
            })()`);
            assert.equal(resets.limit.count, 200);
            assert.equal(resets.limit.limited, true);
            assert.match(resets.limit.status, /前 200/);
            assert.equal(resets.transcript, 1);
            assert.equal(resets.outlineHidden, true);
            assert.equal(resets.noOldHighlights, true);

            const final = await evaluate(cdp, `({noOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
                forbidden: window.__g1Forbidden, errors: window.__g1Errors})`);
            assert.equal(final.noOverflow, true, name + ': overflow');
            assert.deepEqual(final.forbidden, []);
            assert.deepEqual(final.errors, []);
            results.push({name, home, outline, search, preserved, resets, exportResult, final});
            console.log(`[g1] ${name}: passed`);
        }
    }
    fs.writeFileSync(path.join(evidenceDir, 'browser-results.json'), JSON.stringify(results, null, 2));
} finally {
    if (cdp) {
        try { await cdp.send('Browser.close', {}, 3000); } catch { /* close may disconnect */ }
        cdp.close();
    }
    if (proc && proc.exitCode === null) {
        await Promise.race([once(proc, 'exit'), sleep(3000)]);
        if (proc.exitCode === null) {
            const killer = spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F'], {stdio: 'ignore', windowsHide: true});
            await once(killer, 'exit');
        }
    }
    assert.ok(path.dirname(profile) === os.tmpdir() && path.basename(profile).startsWith('v2k-g1-browser-'));
    fs.rmSync(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 300});
}
