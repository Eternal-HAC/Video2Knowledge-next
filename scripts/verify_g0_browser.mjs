#!/usr/bin/env node
// Source-local G0 acceptance. Run against an ISOLATED workspace server only.
// All integration/key/model status is synthetic; no tasks, OS opens or provider calls.
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

const url = process.argv[2];
const output = process.argv[3];
if (!url || !output || new URL(url).hostname !== '127.0.0.1') {
    throw new Error('Usage: node scripts/verify_g0_browser.mjs http://127.0.0.1:<isolated-port>/ <evidence-directory>');
}
const evidenceDir = path.resolve(output);
fs.mkdirSync(evidenceDir, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'v2k-g0-browser-'));
const fixtures = `(() => {
    const original = window.fetch.bind(window);
    window.__g0Calls = [];
    window.__g0Forbidden = [];
    const fixture = {
        '/api/llm-keys': {storage: {secure: true}, match: null},
        '/api/integrations/note-destinations': {obsidian: {status: 'missing', vaults: []}, feishu: {status: 'missing'}},
        '/api/whisper-models': {models: [{id: 'small', status: 'cached'}, {id: 'paraformer-zh', status: 'cached'}]},
        '/api/bili-login/status': {status: 'idle'},
        '/api/douyin-login/status': {status: 'idle'},
        '/api/task/g0-synthetic/open-result': {opened: false},
    };
    window.fetch = async (input, options = {}) => {
        const target = new URL(typeof input === 'string' ? input : input.url, location.href);
        const route = target.pathname;
        const method = options.method || 'GET';
        window.__g0Calls.push({route, method});
        if (target.origin === location.origin && Object.hasOwn(fixture, route)) {
            return new Response(JSON.stringify(fixture[route]), {status: 200, headers: {'Content-Type': 'application/json'}});
        }
        if (target.origin === location.origin && method === 'GET'
            && ['/api/health', '/api/tasks', '/api/note-templates'].includes(route)) {
            return original(input, options);
        }
        window.__g0Forbidden.push({route, method});
        throw new Error('G0 blocked non-allowlisted request');
    };
})();`;

let proc;
let cdp;
const results = [];
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
    await cdp.send('Page.bringToFront');
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', {source: fixtures});
    for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]]) {
        for (const theme of ['light', 'dark', 'system']) {
            const key = `${width}-${theme}`;
            await cdp.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: false});
            await cdp.send('Emulation.setEmulatedMedia', {features: [
                {name: 'prefers-color-scheme', value: theme === 'light' ? 'light' : 'dark'},
                {name: 'prefers-reduced-motion', value: 'reduce'},
            ]});
            await navigateAndWait(cdp, url);
            await waitFor(cdp, 'window.__videoToNoReady === true && noteTemplatesStatus === "ready"');
            await evaluate(cdp, `document.documentElement.dataset.theme = '${theme}'; true`);
            await evaluate(cdp, `(() => {
                document.getElementById('sourceType').value = 'subtitle';
                const transfer = new DataTransfer();
                transfer.items.add(new File(['1\\n00:00:00,000 --> 00:00:02,000\\n合成验收'], 'synthetic.srt', {type: 'text/plain'}));
                document.getElementById('localFile').files = transfer.files;
                keyMatch = {key_state: 'saved'}; // availability only; contains no key
                updateReadinessCard();
                return true;
            })()`);
            const readiness = await evaluate(cdp, `(() => {
                const text = document.getElementById('readinessList').textContent;
                document.getElementById('readinessCard').scrollIntoView({block: 'center'});
                return {text, summary: document.getElementById('readinessSummary').textContent};
            })()`);
            assert.match(readiness.text, /未验证连接与权限/);
            assert.match(readiness.text, /未验证可写/);
            assert.doesNotMatch(readiness.text, /本地转录/);
            assert.doesNotMatch(readiness.summary, /已就绪/);
            const rowsFit = await evaluate(cdp, `Array.from(document.querySelectorAll('#readinessList li')).every(row => {
                const box = row.getBoundingClientRect();
                const label = row.querySelector('strong').getBoundingClientRect();
                const detail = row.querySelector('span').getBoundingClientRect();
                return Math.abs(label.left - detail.left) < 1 && Array.from(row.children).every(child => {
                    const r = child.getBoundingClientRect();
                    return r.left >= box.left && r.right <= box.right + 1;
                });
            })`);
            assert.equal(rowsFit, true, key + ': readiness contents clipped');
            await capture(cdp, path.join(evidenceDir, `${key}-readiness.png`));

            // Keyboard entry/exit and visible focus, using the real rendered controls.
            await evaluate(cdp, `document.getElementById('settingsToggleBtn').focus(); true`);
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'settingsToggleBtn');
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13});
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
            assert.equal(await evaluate(cdp, 'isSettingsPanelOpen()'), true);
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'settingsCloseBtn');
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'settingsToggleBtn');
            assert.equal(await evaluate(cdp, 'isSettingsPanelOpen()'), false);

            await evaluate(cdp, `(() => {
                const task = {status: 'processing', step: 4, step_name: '语音转写',
                    progress: 37, progress_message: '合成进度：正在转录音频',
                    processed_seconds: 40, total_seconds: 100, estimated_remaining_seconds: 180};
                document.getElementById('progressArea').hidden = false;
                isTaskActive = true;
                updateProgress(task.progress); updateStep(4);
                setTaskState('processing', '处理中');
                document.getElementById('networkState').textContent = '合成验收状态';
                renderTaskProgressDetails(task); updateActiveTaskStrip(task);
                document.getElementById('progressArea').scrollIntoView({block: 'center'});
                return true;
            })()`);
            const progress = await evaluate(cdp, 'document.getElementById("progressDetails").textContent');
            assert.match(progress, /转录阶段预计剩余约 2–4 分钟/);
            const stripVisible = await evaluate(cdp, `(() => {
                const strip = document.getElementById('activeTaskStrip');
                const r = strip.getBoundingClientRect();
                const header = document.querySelector('.app-bar').getBoundingClientRect();
                return r.top >= header.bottom && strip.contains(document.elementFromPoint(r.left + 10, r.top + 10));
            })()`);
            assert.equal(stripVisible, true, key + ': active strip obscured by header');
            await capture(cdp, path.join(evidenceDir, `${key}-progress.png`));
            await evaluate(cdp, `renderTaskProgressDetails({status: 'cancelling', step: 4,
                processed_seconds: 40, total_seconds: 100, estimated_remaining_seconds: 180}); true`);
            assert.equal(await evaluate(cdp, 'document.getElementById("progressDetails").hidden'), true);

            await evaluate(cdp, `(async () => {
                currentTaskId = 'g0-synthetic';
                setTaskActive(false);
                document.getElementById('progressArea').hidden = true;
                await showResult({output: 'note', markdown: '# 合成验收笔记\\n\\n## 结论\\n这份内容仅用于本地 UI 验收。',
                    archived_path: 'workspace/notes/合成验收笔记.md', output_directory: 'workspace/g0-synthetic'});
                document.getElementById('resultArea').scrollIntoView({block: 'center'});
                return true;
            })()`);
            const controls = await evaluate(cdp, `['openResultFileBtn', 'openResultFolderBtn', 'downloadMdBtn'].map(id => {
                const el = document.getElementById(id), box = el.getBoundingClientRect();
                return {id, text: el.textContent, enabled: !el.disabled, width: box.width, left: box.left, right: box.right};
            })`);
            for (const control of controls) {
                assert.equal(control.enabled, true, control.id);
                assert.ok(control.width > 0 && control.left >= 0 && control.right <= width, control.id);
            }
            assert.match(controls[2].text, /导出 Markdown/);
            await evaluate(cdp, 'document.getElementById("openResultFileBtn").focus(); true');
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9});
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9});
            assert.equal(await evaluate(cdp, 'document.activeElement.id'), 'openResultFolderBtn');
            const focus = await evaluate(cdp, `({visible: document.activeElement.matches(':focus-visible'),
                outline: getComputedStyle(document.activeElement).outlineStyle})`);
            assert.ok(focus.visible && focus.outline !== 'none');
            await capture(cdp, path.join(evidenceDir, `${key}-result.png`));
            // Exercise the actual click handler; the fixture prevents any OS dispatch.
            await evaluate(cdp, 'document.getElementById("openResultFolderBtn").click(); true');
            await waitFor(cdp, '!document.getElementById("openResultFolderBtn").disabled');
            const state = await evaluate(cdp, `({width: document.documentElement.clientWidth,
                scrollWidth: document.documentElement.scrollWidth, forbidden: window.__g0Forbidden,
                calls: window.__g0Calls, bodyText: document.body.innerText})`);
            assert.ok(state.scrollWidth <= state.width, `${key}: page overflow`);
            assert.deepEqual(state.forbidden, [], `${key}: forbidden request`);
            assert.ok(state.calls.some(call => call.route.endsWith('/open-result')));
            assert.match(state.bodyText, /系统未能自动打开/);
            results.push({key, viewport: [width, height], readiness, progress, controls, focus,
                noOverflow: true, noForbiddenRequests: true, keyboard: 'passed', openFallback: 'passed'});
            console.log(`[g0] ${key}: passed`);
        }
    }
    fs.writeFileSync(path.join(evidenceDir, 'browser-results.json'), JSON.stringify(results, null, 2));
} finally {
    if (cdp) {
        try { await cdp.send('Browser.close', {}, 3000); } catch { /* close may disconnect first */ }
        cdp.close();
    }
    if (proc && proc.exitCode === null) {
        await Promise.race([once(proc, 'exit'), sleep(3000)]);
        if (proc.exitCode === null) {
            const killer = spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F'], {stdio: 'ignore', windowsHide: true});
            await once(killer, 'exit');
        }
    }
    // The exact mkdtemp path is owned by this run; never recurse over its parent.
    assert.ok(path.dirname(profile) === os.tmpdir() && path.basename(profile).startsWith('v2k-g0-browser-'));
    fs.rmSync(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 300});
}
