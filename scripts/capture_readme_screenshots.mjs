#!/usr/bin/env node
/**
 * capture_readme_screenshots.mjs
 *
 * 生成 README 用的三张界面截图（home / progress / result）。
 *
 * 约束（与任务要求一致）：
 * - 仅使用 Node 22 内置模块与全局 WebSocket / fetch，不安装任何依赖。
 * - 通过 headless Chrome + CDP（DevTools Protocol）访问本机服务页面，
 *   截图是真实 CSS/DOM 渲染结果，不手工绘制、不使用外部图片。
 * - progress / result 两个状态只通过 Runtime.evaluate 把当前 DOM 改成
 *   合成、无隐私的演示状态，不触发任何后端任务。
 * - 使用一次性临时 user-data-dir；无论成功失败，finally 中精确结束
 *   本脚本启动的 Chrome 进程并删除临时 profile；绝不删除输出图片。
 * - CDP 连接或截图失败时以非零码退出。
 *
 * 用法：
 *   node scripts/capture_readme_screenshots.mjs [--url http://127.0.0.1:8000]
 *   CHROME_PATH="C:\path\chrome.exe" node scripts/capture_readme_screenshots.mjs
 */

import { spawn } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

const VIEWPORT = {
    width: Number(process.env.V2K_CAPTURE_WIDTH) || 1440,
    height: Number(process.env.V2K_CAPTURE_HEIGHT) || 900,
};
const DEFAULT_URL = 'http://127.0.0.1:8000/';
const CAPTURE_THEME = ['light', 'dark'].includes(process.env.V2K_CAPTURE_THEME)
    ? process.env.V2K_CAPTURE_THEME
    : null;
const OUTPUT_DIR = process.env.V2K_CAPTURE_OUTPUT_DIR
    ? path.resolve(process.env.V2K_CAPTURE_OUTPUT_DIR)
    : path.join(REPO_ROOT, 'sources');

const SHOTS = [
    { name: 'home', file: path.join(OUTPUT_DIR, 'knowledge-studio-home.png') },
    { name: 'history', file: path.join(OUTPUT_DIR, 'knowledge-studio-history.png') },
    { name: 'template', file: path.join(OUTPUT_DIR, 'knowledge-studio-template-preview.png') },
];

// ---------------------------------------------------------------------------
// 参数与 Chrome 定位
// ---------------------------------------------------------------------------

function parseArgs(argv) {
    let url = DEFAULT_URL;
    for (let i = 0; i < argv.length; i += 1) {
        if (argv[i] === '--url' && argv[i + 1]) {
            url = argv[i + 1];
            i += 1;
        }
    }
    return { url };
}

function locateChrome() {
    const candidates = [
        process.env.CHROME_PATH,
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        process.env.LOCALAPPDATA
            ? path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe')
            : null,
    ].filter(Boolean);
    for (const candidate of candidates) {
        if (fs.existsSync(candidate)) return candidate;
    }
    throw new Error('未找到 Chrome，请设置 CHROME_PATH 环境变量');
}

// ---------------------------------------------------------------------------
// 最小 CDP 客户端（全局 WebSocket）
// ---------------------------------------------------------------------------

class CdpClient {
    constructor(wsUrl) {
        this.wsUrl = wsUrl;
        this.ws = null;
        this.nextId = 1;
        this.pending = new Map();
        this.eventWaiters = new Map();
    }

    async connect(timeoutMs = 15000) {
        this.ws = new WebSocket(this.wsUrl);
        this.ws.addEventListener('message', (event) => this.#onMessage(event));
        const opened = once(this.ws, 'open');
        const errored = once(this.ws, 'error').then(([err]) => {
            throw new Error(`CDP WebSocket 连接失败: ${err?.message || 'unknown'}`);
        });
        await Promise.race([
            Promise.race([opened, errored]),
            new Promise((_, reject) => setTimeout(
                () => reject(new Error('CDP WebSocket 连接超时')), timeoutMs)),
        ]);
    }

    #onMessage(event) {
        let msg;
        try {
            msg = JSON.parse(typeof event.data === 'string' ? event.data : String(event.data));
        } catch {
            return;
        }
        if (msg.id) {
            const entry = this.pending.get(msg.id);
            if (!entry) return;
            this.pending.delete(msg.id);
            if (msg.error) {
                entry.reject(new Error(`CDP ${entry.method} 失败: ${msg.error.message}`));
            } else {
                entry.resolve(msg.result);
            }
            return;
        }
        if (msg.method) {
            const waiters = this.eventWaiters.get(msg.method);
            if (waiters && waiters.length) {
                this.eventWaiters.delete(msg.method);
                waiters.forEach((resolve) => resolve(msg.params));
            }
        }
    }

    send(method, params = {}, timeoutMs = 30000) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return Promise.reject(new Error(`CDP WebSocket 未连接，无法发送 ${method}`));
        }
        const id = this.nextId;
        this.nextId += 1;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(`CDP ${method} 超时`));
            }, timeoutMs);
            this.pending.set(id, {
                method,
                resolve: (value) => { clearTimeout(timer); resolve(value); },
                reject: (err) => { clearTimeout(timer); reject(err); },
            });
            this.ws.send(JSON.stringify({ id, method, params }));
        });
    }

    waitEvent(method, timeoutMs = 30000) {
        return new Promise((resolve, reject) => {
            const timer = setTimeout(
                () => reject(new Error(`等待 CDP 事件 ${method} 超时`)), timeoutMs);
            const list = this.eventWaiters.get(method) || [];
            list.push((params) => { clearTimeout(timer); resolve(params); });
            this.eventWaiters.set(method, list);
        });
    }

    close() {
        try { this.ws?.close(); } catch { /* 忽略关闭异常 */ }
    }
}

// ---------------------------------------------------------------------------
// 页面内合成状态脚本（只改 DOM，不触发后端任务）
// ---------------------------------------------------------------------------

// 公共：隐藏可能含真实任务标题的“最近任务”面板，回到顶部。
const PAGE_PREPARE_JS = `
(() => {
    let captureStyle = document.getElementById('readme-capture-style');
    if (!captureStyle) {
        captureStyle = document.createElement('style');
        captureStyle.id = 'readme-capture-style';
        captureStyle.textContent = '* { animation: none !important; transition: none !important; }';
        document.head.appendChild(captureStyle);
    }
    const recent = document.getElementById('recentTasksPanel');
    if (recent) recent.hidden = true;
    window.scrollTo(0, 0);
    return true;
})()`;

// history：使用页面自己的历史渲染函数合成任务摘要，不读取本机真实任务。
const HISTORY_STATE_JS = `
(() => {
    const byId = (id) => document.getElementById(id);
    const recent = byId('recentTasksPanel');
    if (recent) recent.hidden = false;
    const source = document.querySelector('.source-panel');
    if (source) source.hidden = true;
    byId('progressArea').hidden = true;
    byId('resultArea').hidden = true;
    byId('historyEmpty').hidden = true;
    byId('historyLoadMoreBtn').hidden = false;
    renderRecentTasks([
        { task_id: 'demo-1', title: '如何建立可复用的个人知识系统', status: 'completed',
          output: 'note', platform: 'youtube', template_name: '学习讲义', favorite: true,
          created_at: '2026-10-22T08:10:00+08:00', finished_at: '2026-10-22T08:14:20+08:00', elapsed_seconds: 260 },
        { task_id: 'demo-2', title: '产品访谈：从用户问题到行动项', status: 'completed',
          output: 'note', platform: 'bilibili', template_name: '访谈 / 观点分析', favorite: false,
          created_at: '2026-10-22T07:30:00+08:00', finished_at: '2026-10-22T07:33:05+08:00', elapsed_seconds: 185 },
        { task_id: 'demo-3', title: '本地课程录音转录稿', status: 'completed',
          output: 'transcript', platform: 'local', template_name: '', favorite: false,
          created_at: '2026-10-21T21:00:00+08:00', finished_at: '2026-10-21T21:08:40+08:00', elapsed_seconds: 520 },
        { task_id: 'demo-4', title: '短视频运营复盘', status: 'failed',
          output: 'note', platform: 'douyin', template_name: '知识精华', favorite: false,
          created_at: '2026-10-21T20:10:00+08:00', finished_at: '2026-10-21T20:10:45+08:00', elapsed_seconds: 45 },
    ]);

    window.scrollTo(0, 0);
    return true;
})()`;

// template：选择“学习讲义”并展示确定性预览；隐藏其余任务区，避免私人数据进入截图。
const TEMPLATE_STATE_JS = `
(() => {
    const byId = (id) => document.getElementById(id);
    const recent = byId('recentTasksPanel');
    if (recent) recent.hidden = true;
    const source = document.querySelector('.source-panel');
    if (source) source.hidden = false;
    byId('progressArea').hidden = true;
    byId('resultArea').hidden = true;
    byId('destinationChooserSection').hidden = true;
    document.querySelector('.source-controls').hidden = true;
    byId('sourceInspectPanel').hidden = true;
    byId('planSummary').hidden = true;
    byId('exportHint').hidden = true;
    byId('localImportHint').hidden = true;
    document.querySelector('.source-meta').hidden = true;
    const select = byId('noteTemplate');
    select.value = 'builtin-study-lecture';
    updateNoteTemplateDetails();
    renderNoteTemplateCards();
    setTemplatePreviewMode('rendered');
    byId('templatePreviewDetails').open = true;

    window.scrollTo(0, 0);
    return true;
})()`;

// ---------------------------------------------------------------------------
// CDP 辅助
// ---------------------------------------------------------------------------

async function evaluate(cdp, expression) {
    const result = await cdp.send('Runtime.evaluate', {
        expression,
        returnByValue: true,
        awaitPromise: true,
    });
    if (result.exceptionDetails) {
        throw new Error(`页面脚本执行失败: ${JSON.stringify(result.exceptionDetails)}`);
    }
    return result.result?.value;
}

async function waitFor(cdp, expression, { timeoutMs = 20000, intervalMs = 200 } = {}) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
        const value = await evaluate(cdp, expression).catch(() => false);
        if (value) return;
        if (Date.now() > deadline) {
            throw new Error(`等待页面条件超时: ${expression}`);
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForDevToolsPort(userDataDir, proc, timeoutMs = 30000) {
    const portFile = path.join(userDataDir, 'DevToolsActivePort');
    const deadline = Date.now() + timeoutMs;
    for (;;) {
        if (proc.exitCode !== null) {
            throw new Error(`Chrome 提前退出，exitCode=${proc.exitCode}`);
        }
        try {
            const content = fs.readFileSync(portFile, 'utf8').trim().split(/\r?\n/);
            const port = Number(content[0]);
            if (port > 0) return port;
        } catch { /* 文件尚未写入 */ }
        if (Date.now() > deadline) throw new Error('等待 Chrome DevTools 端口超时');
        await sleep(150);
    }
}

async function findPageTarget(port, timeoutMs = 15000) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
        try {
            const response = await fetch(`http://127.0.0.1:${port}/json/list`);
            const targets = await response.json();
            const page = targets.find((t) => t.type === 'page');
            if (page) return page;
        } catch { /* DevTools HTTP 尚未就绪 */ }
        if (Date.now() > deadline) throw new Error('未找到可连接的 page target');
        await sleep(200);
    }
}

async function navigateAndWait(cdp, url) {
    const loaded = cdp.waitEvent('Page.loadEventFired', 45000);
    await cdp.send('Page.navigate', { url });
    await loaded;
}

async function capture(cdp, file, { fullPage = false } = {}) {
    // fullPage：整页高度截图（结果区长内容需要一次看全标题→行动清单），
    // 仍是当前真实 CSS/DOM 的渲染结果，只是超出 1440x900 视口。
    const result = await cdp.send('Page.captureScreenshot', {
        format: 'png',
        captureBeyondViewport: fullPage,
    }, 60000);
    const buffer = Buffer.from(result.data, 'base64');
    if (buffer.length < 8
        || buffer[0] !== 0x89 || buffer[1] !== 0x50
        || buffer[2] !== 0x4e || buffer[3] !== 0x47) {
        throw new Error(`截图不是有效 PNG: ${file}`);
    }
    fs.writeFileSync(file, buffer);
    const width = buffer.readUInt32BE(16);
    const height = buffer.readUInt32BE(20);
    return { file, bytes: buffer.length, width, height };
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------

async function main() {
    const { url } = parseArgs(process.argv.slice(2));
    const chromePath = locateChrome();
    const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'v2k-readme-shots-'));

    let proc = null;
    let cdp = null;

    try {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
        console.log(`[shots] Chrome: ${chromePath}`);
        console.log(`[shots] 目标页面: ${url}`);
        proc = spawn(chromePath, [
            '--headless=new',
            '--disable-gpu',
            '--hide-scrollbars',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            '--force-device-scale-factor=1',
            '--remote-debugging-port=0',
            `--user-data-dir=${userDataDir}`,
            'about:blank',
        ], { stdio: ['ignore', 'ignore', 'pipe'] });
        let chromeStderr = '';
        proc.stderr.on('data', (chunk) => {
            chromeStderr += chunk.toString();
            if (chromeStderr.length > 4000) chromeStderr = chromeStderr.slice(-4000);
        });
        proc.on('error', (err) => {
            throw new Error(`无法启动 Chrome: ${err.message}`);
        });

        const port = await waitForDevToolsPort(userDataDir, proc);
        const page = await findPageTarget(port);
        cdp = new CdpClient(page.webSocketDebuggerUrl);
        await cdp.connect();
        console.log(`[shots] CDP 已连接（DevTools 端口 ${port}）`);

        await cdp.send('Page.enable');
        await cdp.send('Runtime.enable');
        await cdp.send('Emulation.setDeviceMetricsOverride', {
            width: VIEWPORT.width,
            height: VIEWPORT.height,
            deviceScaleFactor: 1,
            mobile: false,
        });

        // 首次加载后清空 localStorage 再重载，保证“干净初始页面”。
        await navigateAndWait(cdp, url);
        await evaluate(cdp, 'localStorage.clear(); true');
        await cdp.send('Page.reload', { ignoreCache: true });
        await cdp.waitEvent('Page.loadEventFired', 45000);

        // 等待应用完成初始化：脚本就绪标记 + 版本号回写 + 字体就绪。
        await waitFor(cdp, 'window.__videoToNoReady === true');
        await waitFor(cdp,
            "document.getElementById('appVersion')?.textContent === 'v1.0.0-beta.4'",
            { timeoutMs: 10000 });
        await waitFor(cdp,
            "document.querySelectorAll('#templateCards .template-card').length >= 6",
            { timeoutMs: 10000 });
        if (CAPTURE_THEME) {
            await evaluate(cdp,
                `document.documentElement.dataset.theme = ${JSON.stringify(CAPTURE_THEME)}; true`);
        }
        await evaluate(cdp, 'document.fonts && document.fonts.ready.then(() => true)');
        await sleep(400);
        const layout = await evaluate(cdp, `({
            clientWidth: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth
        })`);
        if (layout.scrollWidth > layout.clientWidth) {
            throw new Error(`页面发生整体横向滚动: ${layout.scrollWidth} > ${layout.clientWidth}`);
        }
        console.log(`[shots] 页面宽度检查通过: ${layout.scrollWidth}/${layout.clientWidth}`);

        // 1) home：干净初始页面
        await evaluate(cdp, PAGE_PREPARE_JS);
        await sleep(300);
        const home = await capture(cdp, SHOTS[0].file);
        console.log(`[shots] home -> ${path.relative(REPO_ROOT, home.file)}`
            + ` (${home.width}x${home.height}, ${home.bytes} bytes)`);

        // 2) history：合成历史与收藏状态
        // 初始化阶段的真实空历史请求是异步的；先让它落定，再写入合成行，避免回包覆盖。
        await sleep(1200);
        await evaluate(cdp, HISTORY_STATE_JS);
        await sleep(300);
        const history = await capture(cdp, SHOTS[1].file);
        console.log(`[shots] history -> ${path.relative(REPO_ROOT, history.file)}`
            + ` (${history.width}x${history.height}, ${history.bytes} bytes)`);

        // 3) template：展示确定性模板预览
        const reloaded = cdp.waitEvent('Page.loadEventFired', 45000);
        await cdp.send('Page.reload', { ignoreCache: true });
        await reloaded;
        await waitFor(cdp, 'window.__videoToNoReady === true');
        await waitFor(cdp,
            "document.querySelectorAll('#templateCards .template-card').length >= 6",
            { timeoutMs: 10000 });
        if (CAPTURE_THEME) {
            await evaluate(cdp,
                `document.documentElement.dataset.theme = ${JSON.stringify(CAPTURE_THEME)}; true`);
        }
        await evaluate(cdp, TEMPLATE_STATE_JS);
        await sleep(400);
        const template = await capture(cdp, SHOTS[2].file);
        console.log(`[shots] template -> ${path.relative(REPO_ROOT, template.file)}`
            + ` (${template.width}x${template.height}, ${template.bytes} bytes)`);

        console.log('[shots] 三张截图已生成');
    } finally {
        if (cdp) cdp.close();
        if (proc && proc.exitCode === null) {
            // 只结束本脚本启动的这个 Chrome：先正常 kill，再用 taskkill /T
            // 兜底连带子进程，最后用退出事件确认进程确实结束。
            try { proc.kill(); } catch { /* 已退出 */ }
            const exited = await Promise.race([
                once(proc, 'exit').then(() => true),
                sleep(5000).then(() => false),
            ]);
            if (!exited && proc.pid) {
                spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F'],
                    { stdio: 'ignore' });
                await Promise.race([once(proc, 'exit'), sleep(5000)]);
            }
        }
        // 删除临时 profile（Windows 上 Chrome 退出后句柄释放可能稍慢，重试几次）。
        for (let attempt = 0; attempt < 10; attempt += 1) {
            try {
                fs.rmSync(userDataDir, { recursive: true, force: true });
                break;
            } catch {
                await sleep(300);
            }
        }
        if (fs.existsSync(userDataDir)) {
            console.warn(`[shots] 警告：临时 profile 未能完全删除: ${userDataDir}`);
        }
    }
}

export { CdpClient, locateChrome, waitForDevToolsPort, findPageTarget,
    evaluate, waitFor, navigateAndWait, capture, sleep };

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    main().catch((error) => {
        console.error(`[shots] 失败: ${error.message}`);
        process.exitCode = 1;
    });
}
