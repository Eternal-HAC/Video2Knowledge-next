#!/usr/bin/env node
// Isolated synthetic workspace only. Real GET context API; all mutations blocked.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
    CdpClient, locateChrome, waitForDevToolsPort, findPageTarget,
    evaluate, waitFor, navigateAndWait, capture, sleep,
} from './capture_readme_screenshots.mjs';

const [url, output] = process.argv.slice(2);
if (!url || !output || new URL(url).hostname !== '127.0.0.1') {
    throw new Error('Usage: node scripts/verify_g3_browser.mjs http://127.0.0.1:<isolated-port>/ <evidence-directory>');
}
const evidenceDir = path.resolve(output);
fs.mkdirSync(evidenceDir, {recursive: true});
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'v2k-g3-browser-'));
const fixtures = `(() => {
    const original = window.fetch.bind(window);
    window.__g3Calls = []; window.__g3Forbidden = []; window.__g3Errors = [];
    window.__g3Mode = 'normal';
    window.addEventListener('error', e => window.__g3Errors.push(e.message));
    window.addEventListener('unhandledrejection', e => window.__g3Errors.push(String(e.reason)));
    const fixed = {
        '/api/llm-keys': {storage: {secure: true}, match: null},
        '/api/integrations/note-destinations': {obsidian: {status: 'missing', vaults: []}, feishu: {status: 'missing'}},
        '/api/whisper-models': {models: [{id: 'small', status: 'cached'}]},
        '/api/bili-login/status': {status: 'idle'}, '/api/douyin-login/status': {status: 'idle'},
    };
    window.fetch = async (input, options = {}) => {
        const target = new URL(typeof input === 'string' ? input : input.url, location.href);
        const route = target.pathname; const method = options.method || 'GET';
        window.__g3Calls.push({route, method, search: target.search});
        if (target.origin === location.origin && method === 'GET') {
            if (Object.hasOwn(fixed, route)) return Response.json(fixed[route]);
            if (['/api/health', '/api/tasks', '/api/note-templates', '/api/task/g3-synthetic'].includes(route)) return original(input, options);
            if (route === '/api/task/g3-synthetic/transcript-context') {
                if (__g3Mode === 'error') return Response.json({detail: 'deliberately untrusted backend error'}, {status: 409});
                if (__g3Mode === 'delay') {
                    // Deliberately ignore AbortSignal: a late completed request must still be discarded.
                    const data = await (await original(input, {cache: 'no-store'})).json();
                    return new Promise(resolve => { window.__g3Release = () => resolve(Response.json(data)); });
                }
                return original(input, options);
            }
        }
        window.__g3Forbidden.push({route, method});
        throw new Error('G3 blocked non-allowlisted request');
    };
})();`;

let proc;
let cdp;
const results = [];
async function key(name, code) {
    await cdp.send('Input.dispatchKeyEvent', {type: 'keyDown', key: name, code: name,
        ...(name === 'Enter' ? {text: '\r'} : {}), windowsVirtualKeyCode: code});
    await cdp.send('Input.dispatchKeyEvent', {type: 'keyUp', key: name, code: name, windowsVirtualKeyCode: code});
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
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', {source: fixtures});
    for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]]) {
        for (const theme of ['light', 'dark', 'system']) {
            const name = `${width}-${theme}`;
            await cdp.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width === 390});
            await cdp.send('Emulation.setEmulatedMedia', {features: [
                {name: 'prefers-color-scheme', value: theme === 'light' ? 'light' : 'dark'},
                {name: 'prefers-reduced-motion', value: 'reduce'},
            ]});
            await navigateAndWait(cdp, url);
            await waitFor(cdp, 'window.__videoToNoReady === true && noteTemplatesStatus === "ready"');
            await evaluate(cdp, `(async () => {
                document.querySelector('[data-theme-option="${theme}"]').click();
                const task = await (await fetch('/api/task/g3-synthetic')).json();
                window.__g3Result = task.result;
                currentTaskId = 'g3-synthetic'; await showResult(task.result);
                window.__g3Markdown = currentMarkdown;
                window.__g3Html = currentHtml;
                window.__g3First = document.querySelector('.note-time-button');
                __g3First.focus();
            })()`);
            const before = await evaluate(cdp, `({buttons: document.querySelectorAll('.note-time-button').length,
                excluded: document.querySelectorAll('a .note-time-button, code .note-time-button, .katex .note-time-button').length,
                requests: __g3Calls.filter(c => c.route.endsWith('transcript-context')).length})`);
            assert.equal(before.buttons, 3); assert.equal(before.excluded, 0); assert.equal(before.requests, 0);
            await key('Enter', 13);
            await waitFor(cdp, `!byId('transcriptContextPanel').hasAttribute('aria-busy')`);
            const opened = await evaluate(cdp, `({rows: byId('transcriptContextRows').children.length,
                status: byId('transcriptContextStatus').textContent,
                metadata: byId('transcriptContextMetadata').textContent,
                more: !byId('transcriptContextMoreBtn').hidden,
                scripts: byId('transcriptContextRows').querySelectorAll('script, img').length,
                xss: Boolean(window.__g3Xss), focus: document.activeElement.id})`);
            assert.equal(opened.rows, 100); assert.equal(opened.more, true);
            assert.equal(opened.scripts, 0); assert.equal(opened.xss, false);
            assert.equal(opened.focus, 'transcriptContextTitle');
            assert.match(opened.metadata, /多 P 累计时间轴/); assert.match(opened.metadata, /媒体未保留/);
            await capture(cdp, path.join(evidenceDir, `${name}-context.png`));
            await evaluate(cdp, `byId('transcriptContextMoreBtn').click()`);
            await waitFor(cdp, `!byId('transcriptContextPanel').hasAttribute('aria-busy')`);
            assert.equal(await evaluate(cdp, `byId('transcriptContextRows').children.length`), 125);
            await evaluate(cdp, `byId('transcriptContextCloseBtn').focus()`);
            await key('Escape', 27);
            assert.equal(await evaluate(cdp, `byId('transcriptContextPanel').hidden && document.activeElement === __g3First`), true);

            // A request using a stale note hash must fail closed against the real API.
            await evaluate(cdp, `(async () => {
                await showResult({...__g3Result, markdown: __g3Markdown + '\\n已变化'});
                openTranscriptContext(0, 30, byId('viewTranscriptBtn'));
            })()`);
            await waitFor(cdp, `!byId('transcriptContextPanel').hasAttribute('aria-busy')`);
            assert.equal(await evaluate(cdp, `byId('transcriptContextRows').children.length`), 0);
            assert.match(await evaluate(cdp, `byId('transcriptContextStatus').textContent`), /版本已变化/);

            // A delayed previous reader must not paint over a new task/result.
            await evaluate(cdp, `(async () => {
                await showResult(__g3Result); __g3Mode = 'delay';
                openTranscriptContext(0, 30, byId('viewTranscriptBtn'));
            })()`);
            await waitFor(cdp, `typeof __g3Release === 'function'`);
            await evaluate(cdp, `(async () => {
                await showResult({...__g3Result, markdown: '# 没有时间戳的合成笔记'});
                __g3Release(); __g3Mode = 'normal';
            })()`);
            await sleep(100);
            assert.equal(await evaluate(cdp, `byId('transcriptContextPanel').hidden && byId('transcriptContextRows').children.length === 0`), true);
            assert.match(await evaluate(cdp, `byId('noteTimestampHint').textContent`), /没有可定位/);

            await evaluate(cdp, `(async () => {
                await showResult(__g3Result);
                __g3Release = null; __g3Mode = 'delay';
                openTranscriptContext(0, 30, byId('viewTranscriptBtn'));
            })()`);
            await waitFor(cdp, `typeof __g3Release === 'function'`);
            await evaluate(cdp, `__g3Mode = 'normal'; openTranscriptContext(540, null, byId('viewTranscriptBtn'))`);
            await waitFor(cdp, `!byId('transcriptContextPanel').hasAttribute('aria-busy')`);
            await evaluate(cdp, `__g3Release()`);
            await sleep(100);
            assert.equal(await evaluate(cdp, `byId('transcriptContextRows').children.length`), 0);
            assert.match(await evaluate(cdp, `byId('transcriptContextStatus').textContent`), /超出已保存/);
            await evaluate(cdp, `(async () => {
                // A large note never creates unbounded interactive controls.
                await showResult({...__g3Result, markdown: '# 合成上限\\n' + '[00:03] '.repeat(220)});
            })()`);
            assert.equal(await evaluate(cdp, `document.querySelectorAll('.note-time-button').length`), 200);
            await evaluate(cdp, `(async () => {
                await showResult(__g3Result);
                openTranscriptContext(540, null, byId('viewTranscriptBtn'));
            })()`);
            await waitFor(cdp, `!byId('transcriptContextPanel').hasAttribute('aria-busy')`);
            assert.match(await evaluate(cdp, `byId('transcriptContextStatus').textContent`), /超出已保存/);
            await capture(cdp, path.join(evidenceDir, `${name}-no-match.png`));

            await evaluate(cdp, `__g3Mode = 'error'; openTranscriptContext(0, 30, byId('viewTranscriptBtn'))`);
            await waitFor(cdp, `!byId('transcriptContextPanel').hasAttribute('aria-busy')`);
            const final = await evaluate(cdp, `({rows: byId('transcriptContextRows').children.length,
                safeError: !byId('transcriptContextStatus').textContent.includes('untrusted'),
                sameMarkdown: currentMarkdown === __g3Markdown, sameHtml: currentHtml === __g3Html,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                forbidden: __g3Forbidden, errors: __g3Errors,
                posts: __g3Calls.filter(c => c.method !== 'GET'),
                hashes: __g3Calls.filter(c => c.route.endsWith('transcript-context')).map(c => c.search)})`);
            assert.equal(final.rows, 0); assert.equal(final.safeError, true);
            assert.equal(final.sameMarkdown, true); assert.equal(final.sameHtml, true);
            assert.equal(final.overflow, false); assert.deepEqual(final.forbidden, []);
            assert.deepEqual(final.errors, []); assert.deepEqual(final.posts, []);
            assert.ok(final.hashes[1].includes('transcript_hash='));
            // Explicit refresh uses the saved note, never a new job or cached changed text.
            await evaluate(cdp, `__g3Mode = 'normal'; byId('transcriptContextReloadNoteBtn').click()`);
            await waitFor(cdp, `byId('transcriptContextPanel').hidden && currentMarkdown === __g3Markdown`);
            assert.equal(await evaluate(cdp, `__g3Calls.some(c => c.route === '/api/task/g3-synthetic' && c.search === '?refresh_note=true')`), true);
            assert.equal(await evaluate(cdp, `__g3Calls.filter(c => c.method !== 'GET').length`), 0);
            results.push({name, before, opened, final});
            console.log(`[g3] ${name}: passed`);
        }
    }
    fs.writeFileSync(path.join(evidenceDir, 'browser-results.json'), JSON.stringify(results, null, 2));
} finally {
    if (cdp) {
        try { await cdp.send('Browser.close', {}, 3000); } catch { /* closing disconnects CDP */ }
        cdp.close();
    }
    if (proc && proc.exitCode === null) {
        await Promise.race([once(proc, 'exit'), sleep(3000)]);
        if (proc.exitCode === null) {
            const killer = spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F'], {stdio: 'ignore', windowsHide: true});
            await once(killer, 'exit');
        }
    }
    assert.ok(path.dirname(profile) === os.tmpdir() && path.basename(profile).startsWith('v2k-g3-browser-'));
    fs.rmSync(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 300});
}
