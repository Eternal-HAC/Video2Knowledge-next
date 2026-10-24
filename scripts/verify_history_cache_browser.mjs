#!/usr/bin/env node
// Real DOM and isolated synthetic GETs. Never submits a job or reads credentials.
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
const target = new URL(url);
assert.equal(target.hostname, '127.0.0.1');
assert.ok(target.port && target.port !== '8000', 'Use an owned isolated server, never the user service');
const evidenceDir = path.resolve(output);
assert.ok(evidenceDir.startsWith(path.resolve('.test-tmp') + path.sep));
fs.mkdirSync(evidenceDir, {recursive: true});
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'v2k-history-cache-'));
const fixtures = `(() => {
    const original = window.fetch.bind(window);
    window.__hcCalls = []; window.__hcForbidden = []; window.__hcErrors = [];
    window.__hcQueue = []; window.__hcNext = ''; window.__hcReal = true;
    window.addEventListener('error', e => __hcErrors.push(e.message));
    window.addEventListener('unhandledrejection', e => __hcErrors.push(String(e.reason)));
    const fixed = {
        '/api/llm-keys': {storage: {secure: true}, match: null},
        '/api/integrations/note-destinations': {obsidian: {status: 'missing', vaults: []}, feishu: {status: 'missing'}},
        '/api/whisper-models': {models: [{id: 'small', status: 'cached'}]},
        '/api/bili-login/status': {status: 'idle'}, '/api/douyin-login/status': {status: 'idle'},
    };
    window.fetch = async (input, options = {}) => {
        const address = new URL(typeof input === 'string' ? input : input.url, location.href);
        const route = address.pathname; const method = options.method || 'GET';
        __hcCalls.push({route, method, search: address.search});
        if (address.origin === location.origin && method === 'GET') {
            if (Object.hasOwn(fixed, route)) return Response.json(fixed[route]);
            if (route === '/api/tasks') {
                const mode = __hcNext; __hcNext = '';
                const label = 'synthetic-' + __hcCalls.length;
                const data = {tasks: [{task_id: label, title: label, status: 'completed', output: 'note',
                    platform: 'local', favorite: false, elapsed_seconds: 3}], total: 1,
                    offset: Number(address.searchParams.get('offset')), limit: 20, has_more: false};
                if (mode === 'hold') {
                    // Deliberately ignore AbortSignal. Cancellation alone is not proof of ownership.
                    return new Promise(resolve => __hcQueue.push({label, resolve: () => resolve(Response.json(data))}));
                }
                if (mode === 'error') return Response.json({detail: 'UNTRUSTED_BACKEND_SENTINEL'}, {status: 500});
                if (mode === 'empty') return Response.json({...data, tasks: [], total: 0});
                return __hcReal ? original(input, options) : Response.json(data);
            }
            if (['/api/health', '/api/note-templates'].includes(route)) return original(input, options);
        }
        __hcForbidden.push({route, method});
        throw new Error('History test blocked non-allowlisted request');
    };
})();`;
let proc, cdp;
const results = [];
const ids = `Array.from(document.querySelectorAll('.recent-task-item'), e => e.dataset.taskId)`;
async function enter() {
    await cdp.send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13});
    await cdp.send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
}
try {
    proc = spawn(locateChrome(), ['--headless=new', '--disable-gpu', '--disable-background-networking',
        '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--remote-debugging-port=0',
        `--user-data-dir=${profile}`, 'about:blank'], {stdio: 'ignore', windowsHide: true});
    cdp = new CdpClient((await findPageTarget(await waitForDevToolsPort(profile, proc))).webSocketDebuggerUrl);
    await cdp.connect(); await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', {source: fixtures});
    for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]]) {
        for (const theme of ['light', 'dark', 'system']) {
            await cdp.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width === 390});
            await cdp.send('Emulation.setEmulatedMedia', {features: [
                {name: 'prefers-color-scheme', value: theme === 'light' ? 'light' : 'dark'},
                {name: 'prefers-reduced-motion', value: 'reduce'},
            ]});
            await navigateAndWait(cdp, url);
            await waitFor(cdp, `window.__videoToNoReady === true && noteTemplatesStatus === 'ready' && !byId('refreshRecentTasksBtn').disabled && recentTaskRows.size === 20`);
            await evaluate(cdp, `document.querySelector('[data-theme-option="${theme}"]').click()`);
            // Real filter + refresh, including cancelling a pending debounce: exactly one explicit refresh.
            const before = await evaluate(cdp, `__hcCalls.filter(c => c.route === '/api/tasks').length`);
            await evaluate(cdp, `byId('historyQuery').value = '合成'; byId('historyStatus').value = 'completed';
                byId('historyOutput').value = 'note'; byId('historyPlatform').value = 'local'; byId('historyFavorite').checked = true;
                byId('historyQuery').dispatchEvent(new Event('input')); byId('refreshRecentTasksBtn').focus()`);
            await enter();
            await waitFor(cdp, `!byId('refreshRecentTasksBtn').disabled`); await sleep(350);
            const refreshed = await evaluate(cdp, `__hcCalls.filter(c => c.route === '/api/tasks').slice(${before})`);
            assert.equal(refreshed.length, 1);
            const params = new URLSearchParams(refreshed[0].search);
            assert.equal(params.get('refresh'), 'true'); assert.equal(params.get('offset'), '0');
            assert.equal(params.get('query'), '合成'); assert.equal(params.get('favorite'), 'true');
            assert.equal(params.get('status'), 'completed'); assert.equal(params.get('output'), 'note');
            assert.equal(params.get('platform'), 'local');
            // Ordinary loading and page two must not request a whole-cache refresh.
            await evaluate(cdp, `(async () => { byId('historyQuery').value = ''; byId('historyStatus').value = 'all';
                byId('historyOutput').value = 'all'; byId('historyPlatform').value = 'all'; byId('historyFavorite').checked = false;
                await loadRecentTasks(true); })()`);
            await evaluate(cdp, `byId('historyLoadMoreBtn').click()`);
            await waitFor(cdp, `!byId('refreshRecentTasksBtn').disabled`);
            const pageTwo = new URLSearchParams(await evaluate(cdp, `__hcCalls.filter(c => c.route === '/api/tasks').at(-1).search`));
            assert.equal(pageTwo.get('offset'), '20'); assert.equal(pageTwo.has('refresh'), false);
            // Old search response arrives after a newer filter response.
            await evaluate(cdp, `__hcReal = false; __hcNext = 'hold'; window.__hcOld = loadRecentTasks(true); void 0`);
            await waitFor(cdp, `__hcQueue.length === 1`);
            await evaluate(cdp, `(async () => { byId('historyQuery').value = 'new-filter'; await loadRecentTasks(true); })()`);
            const newest = await evaluate(cdp, ids);
            await evaluate(cdp, `(async () => { __hcQueue[0].resolve(); await __hcOld; })()`);
            assert.deepEqual(await evaluate(cdp, ids), newest);
            // Old append completes while a newer refresh still owns disabled buttons.
            await evaluate(cdp, `__hcQueue = []; __hcNext = 'hold'; window.__hcAppend = loadRecentTasks(false, true); void 0`);
            await waitFor(cdp, `__hcQueue.length === 1`);
            await evaluate(cdp, `__hcNext = 'hold'; window.__hcRefresh = loadRecentTasks(false, false, true); void 0`);
            await waitFor(cdp, `__hcQueue.length === 2`);
            await evaluate(cdp, `(async () => { __hcQueue[0].resolve(); await __hcAppend; })()`);
            assert.equal(await evaluate(cdp, `byId('refreshRecentTasksBtn').disabled`), true);
            assert.deepEqual(await evaluate(cdp, ids), newest);
            await evaluate(cdp, `__hcQueue[1].resolve()`);
            await waitFor(cdp, `!byId('refreshRecentTasksBtn').disabled`);
            assert.deepEqual(await evaluate(cdp, ids), [await evaluate(cdp, `__hcQueue[1].label`)]);
            // Guard the debounce window too: changed controls already invalidate the old snapshot.
            const preDebounce = await evaluate(cdp, ids);
            await evaluate(cdp, `__hcQueue = []; __hcNext = 'hold'; window.__hcOld = loadRecentTasks(true); void 0`);
            await waitFor(cdp, `__hcQueue.length === 1`);
            await evaluate(cdp, `(async () => { byId('historyQuery').value = 'debounced';
                byId('historyQuery').dispatchEvent(new Event('input')); __hcQueue[0].resolve(); await __hcOld; })()`);
            assert.deepEqual(await evaluate(cdp, ids), preDebounce);
            await sleep(350); await waitFor(cdp, `!byId('refreshRecentTasksBtn').disabled`);
            // Failures preserve rows/pagination; untrusted backend details never appear.
            const retained = await evaluate(cdp, `({ids: ${ids}, offset: historyOffset, more: historyHasMore})`);
            await evaluate(cdp, `__hcNext = 'error'; byId('refreshRecentTasksBtn').click()`);
            await waitFor(cdp, `!byId('refreshRecentTasksBtn').disabled`);
            assert.deepEqual(await evaluate(cdp, `({ids: ${ids}, offset: historyOffset, more: historyHasMore})`), retained);
            assert.equal(await evaluate(cdp, `byId('toastRegion').textContent.includes('读取历史记录失败，请重试')`), true);
            assert.equal(await evaluate(cdp, `document.body.textContent.includes('UNTRUSTED_BACKEND_SENTINEL')`), false);
            await evaluate(cdp, `__hcNext = 'empty'; byId('refreshRecentTasksBtn').focus()`); await enter();
            await waitFor(cdp, `!byId('refreshRecentTasksBtn').disabled`);
            assert.equal(await evaluate(cdp, `!byId('historyEmpty').hidden && byId('historyEmpty').textContent.includes('筛选') && byId('historyLoadMoreBtn').hidden`), true);
            await evaluate(cdp, `byId('refreshRecentTasksBtn').click()`);
            await waitFor(cdp, `!byId('refreshRecentTasksBtn').disabled && recentTaskRows.size === 1`);
            await evaluate(cdp, `byId('refreshRecentTasksBtn').focus()`);
            const final = await evaluate(cdp, `({forbidden: __hcForbidden, errors: __hcErrors,
                posts: __hcCalls.filter(c => c.method !== 'GET'), focus: document.activeElement.id,
                busy: byId('recentTaskList').getAttribute('aria-busy'),
                overflow: document.documentElement.scrollWidth > innerWidth + 1})`);
            assert.deepEqual(final.forbidden, []); assert.deepEqual(final.errors, []); assert.deepEqual(final.posts, []);
            assert.equal(final.focus, 'refreshRecentTasksBtn'); assert.equal(final.busy, null); assert.equal(final.overflow, false);
            const name = `${width}-${theme}`;
            await capture(cdp, path.join(evidenceDir, `${name}.png`));
            results.push({name, passed: true, refreshed: refreshed[0].search, final});
            console.log(`[history-cache] ${name}: passed`);
        }
    }
    fs.writeFileSync(path.join(evidenceDir, 'browser-results.json'), JSON.stringify(results, null, 2));
} finally {
    if (cdp) {
        try { await cdp.send('Browser.close', {}, 3000); } catch { /* CDP disconnect is expected */ }
        cdp.close();
    }
    if (proc && proc.exitCode === null) {
        await Promise.race([once(proc, 'exit'), sleep(3000)]);
        if (proc.exitCode === null) {
            const killer = spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F'], {stdio: 'ignore', windowsHide: true});
            await once(killer, 'exit');
        }
    }
    assert.equal(path.dirname(profile), os.tmpdir());
    assert.ok(path.basename(profile).startsWith('v2k-history-cache-'));
    fs.rmSync(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 300});
}
