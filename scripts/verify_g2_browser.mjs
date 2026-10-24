#!/usr/bin/env node
// Real DOM, synthetic failure/recovery requests only. Never calls a task backend.
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
    throw new Error('Usage: node scripts/verify_g2_browser.mjs http://127.0.0.1:<isolated-port>/ <evidence-directory>');
}
const evidenceDir = path.resolve(output);
fs.mkdirSync(evidenceDir, {recursive: true});
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'v2k-g2-browser-'));
const fixtures = `(() => {
    const original = window.fetch.bind(window);
    window.__g2Posts = [];
    window.__g2Calls = [];
    window.__g2Forbidden = [];
    window.__g2Errors = [];
    window.__g2DropPoll = true;
    window.addEventListener('error', event => window.__g2Errors.push(event.message));
    window.addEventListener('unhandledrejection', event => window.__g2Errors.push(String(event.reason)));
    const fixed = {
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
        window.__g2Calls.push({route, method});
        if (target.origin === location.origin) {
            if (method === 'POST' && route === '/api/source-inspect') {
                return Response.json({platform: 'other', platform_label: '其他平台', support_level: 'generic', reusable_task: null});
            }
            if (method === 'POST' && route === '/api/summarize') {
                window.__g2Posts.push(JSON.parse(options.body));
                if (window.__g2Posts.length === 1) throw new TypeError('synthetic lost submission response');
                return Response.json({task_id: 'g2-explicit-retry', reused_task_id: 'g2-original'});
            }
            if (method === 'GET') {
                if (Object.hasOwn(fixed, route)) return Response.json(fixed[route]);
                if (['/api/health', '/api/tasks', '/api/note-templates'].includes(route)) return original(input, options);
                if (route.startsWith('/api/submission/')) return Response.json({task_id: 'g2-original', replayed: true});
                if (route === '/api/task/g2-poll' && window.__g2DropPoll) throw new TypeError('synthetic disconnected poll');
                if (['/api/task/g2-original', '/api/task/g2-explicit-retry', '/api/task/g2-poll'].includes(route)) {
                    return Response.json({status: 'failed', output: 'transcript', step: 4, progress: 48,
                        elapsed_seconds: 12, logs: ['合成恢复验证'], error: '合成停止状态',
                        recovery: {can_resume: true, retained: ['transcript'], redo: [],
                            message: '已保留完整转录；继续可复用转录，不调用大模型。'}});
                }
            }
        }
        window.__g2Forbidden.push({route, method});
        throw new Error('G2 blocked non-allowlisted request');
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
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', {source: fixtures});
    for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]]) {
        for (const theme of ['light', 'dark', 'system']) {
            const name = `${width}-${theme}`;
            await cdp.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width === 390});
            await cdp.send('Emulation.setEmulatedMedia', {features: [
                {name: 'prefers-color-scheme', value: theme === 'light' ? 'light' : 'dark'},
            ]});
            await navigateAndWait(cdp, url);
            await waitFor(cdp, `typeof startSummary === 'function' && noteTemplatesStatus === 'ready'`);
            await evaluate(cdp, `(async () => {
                document.querySelector('[data-theme-option="${theme}"]').click();
                setOutputMode('transcript');
                byId('sourceType').value = 'url'; toggleSourceType();
                byId('videoUrl').value = 'https://example.invalid/synthetic-video';
                byId('whisperModel').value = 'small';
                await startSummary({forceRestart: true});
            })()`);
            const unknown = await evaluate(cdp, `({state: byId('taskState').textContent,
                check: byId('checkTaskBtn').textContent, hidden: byId('retryBtn').hidden,
                posts: __g2Posts.length, pending: pendingSubmission})`);
            assert.equal(unknown.state, '状态未知');
            assert.equal(unknown.check, '确认提交结果');
            assert.equal(unknown.hidden, true);
            assert.equal(unknown.posts, 1);
            assert.match(unknown.pending.id, /^[a-z0-9-]{36}$/);
            assert.deepEqual(Object.keys(unknown.pending).sort(), ['id', 'transcriptOnly']);
            await evaluate(cdp, `byId('taskError').scrollIntoView({block: 'center'})`);
            await capture(cdp, path.join(evidenceDir, `${name}-uncertain.png`));

            await evaluate(cdp, `byId('checkTaskBtn').focus()`);
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13});
            await cdp.send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
            await waitFor(cdp, `currentTaskId === 'g2-original' && byId('retryBtn').hidden === false`);
            const recovered = await evaluate(cdp, `({posts: __g2Posts.length,
                enabled: !byId('retryBtn').disabled, message: byId('taskRecoveryMessage').textContent})`);
            assert.equal(recovered.posts, 1);
            assert.equal(recovered.enabled, true);
            assert.match(recovered.message, /完整转录/);
            await capture(cdp, path.join(evidenceDir, `${name}-recovery.png`));

            // Explicit retry is a new request, linked to its parent. No automatic POST.
            await evaluate(cdp, `byId('retryBtn').click()`);
            await waitFor(cdp, `__g2Posts.length === 2 && currentTaskId === 'g2-explicit-retry' && !isTaskActive`);
            const explicit = await evaluate(cdp, `({first: __g2Posts[0], second: __g2Posts[1]})`);
            assert.equal(explicit.second.resume_task_id, 'g2-original');
            assert.notEqual(explicit.first.client_request_id, explicit.second.client_request_id);
            assert.equal(explicit.second.output, 'transcript');

            // An unavailable poll never turns a server task into a new submission.
            await evaluate(cdp, `(async () => {
                stopPolling(); currentTaskId = 'g2-poll'; setTaskActive(true); pollErrorCount = 0;
                for (let i = 0; i < MAX_POLL_ERRORS; i++) await pollTask(currentTaskId);
            })()`);
            assert.equal(await evaluate(cdp, `byId('taskState').textContent`), '状态未知');
            await evaluate(cdp, `__g2DropPoll = false; byId('checkTaskBtn').click()`);
            await waitFor(cdp, `byId('retryBtn').hidden === false && !isTaskActive`);
            await evaluate(cdp, `renderTaskRecovery({recovery: {can_resume: false, message: '缺少完整转录，需显式从头处理。'}})`);
            const final = await evaluate(cdp, `({posts: __g2Posts.length,
                disabled: byId('retryBtn').disabled, canRestart: !byId('restartBtn').hidden,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                forbidden: __g2Forbidden, errors: __g2Errors})`);
            assert.equal(final.posts, 2);
            assert.equal(final.disabled, true);
            assert.equal(final.canRestart, true);
            assert.equal(final.overflow, false);
            assert.deepEqual(final.forbidden, []);
            assert.deepEqual(final.errors, []);
            results.push({name, unknown, recovered, explicit, final});
            console.log(`[g2] ${name}: passed`);
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
    assert.ok(path.dirname(profile) === os.tmpdir() && path.basename(profile).startsWith('v2k-g2-browser-'));
    fs.rmSync(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 300});
}
