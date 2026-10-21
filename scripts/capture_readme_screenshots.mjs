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
    { name: 'progress', file: path.join(OUTPUT_DIR, 'knowledge-studio-progress.png') },
    { name: 'result', file: path.join(OUTPUT_DIR, 'knowledge-studio-result.png') },
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

// progress：显示进度区，合成标题/进度/状态/步骤/日志，全部无隐私文字。
const PROGRESS_STATE_JS = `
(() => {
    const byId = (id) => document.getElementById(id);
    const recent = byId('recentTasksPanel');
    if (recent) recent.hidden = true;
    const source = document.querySelector('.source-panel');
    if (source) source.hidden = true;
    byId('resultArea').hidden = true;
    const area = byId('progressArea');
    area.hidden = false;
    area.classList.add('llm-active');

    byId('progressTitle').textContent = '处理进度 · 示例课程：从视频到知识卡片';

    const state = byId('taskState');
    state.className = 'status-badge processing';
    state.textContent = '正在整理笔记';

    byId('elapsedTime').textContent = '03:42';
    byId('progressFill').style.width = '68%';
    byId('progressPercent').textContent = '68%';
    document.querySelector('[role="progressbar"]').setAttribute('aria-valuenow', '68');

    const activeStep = 6;
    document.querySelectorAll('.progress-steps .step').forEach((step, index) => {
        const number = index + 1;
        step.classList.toggle('completed', number < activeStep);
        step.classList.toggle('active', number === activeStep);
    });

    const cancel = byId('cancelTaskBtn');
    cancel.hidden = false;
    cancel.disabled = false;

    byId('networkState').textContent = '正在等待模型返回';
    byId('taskLogDetails').open = true;
    const logArea = byId('logArea');
    logArea.replaceChildren();
    [
        ['info', '已读取视频信息：示例课程：从视频到知识卡片（时长 12:08）'],
        ['success', '已获取平台字幕，跳过本地语音转写'],
        ['info', '已提取 12 张关键画面截图'],
        ['info', '正在调用模型整理笔记（第 2/3 段）…'],
    ].forEach(([type, message]) => {
        const entry = document.createElement('div');
        entry.className = 'log-entry ' + type;
        entry.textContent = message;
        logArea.appendChild(entry);
    });

    window.scrollTo(0, 0);
    return true;
})()`;

// result：显示结果区，用页面自带的 renderMarkdown（marked + DOMPurify）渲染合成 Markdown。
const RESULT_STATE_JS = `
(() => {
    const byId = (id) => document.getElementById(id);
    const recent = byId('recentTasksPanel');
    if (recent) recent.hidden = true;
    const source = document.querySelector('.source-panel');
    if (source) source.hidden = true;
    byId('progressArea').hidden = true;

    const markdown = [
        '# 示例课程：从视频到知识卡片',
        '',
        '## 摘要',
        '',
        '这节示例课程演示如何把一段教学视频拆解为结构化笔记：先抓住核心概念，',
        '再沿着时间轴定位关键片段，最后落到可执行的行动清单。以下内容为演示数据。',
        '',
        '## 三个要点',
        '',
        '1. **概念先行**：先用一句话说清本节要解决的问题，再展开细节。',
        '2. **示例驱动**：每个抽象概念都配一个具体例子，方便对照理解。',
        '3. **可复用产出**：把结论沉淀为清单与模板，下一次直接套用。',
        '',
        '## 时间轴',
        '',
        '| 时间 | 内容 |',
        '| --- | --- |',
        '| 00:00 | 开场与课程目标 |',
        '| 02:15 | 核心概念：知识卡片的结构 |',
        '| 05:40 | 示例：从一段视频到三张卡片 |',
        '| 09:20 | 常见误区与修正 |',
        '| 11:30 | 总结与延伸阅读 |',
        '',
        '## 行动清单',
        '',
        '- [ ] 用自己的话复述本节的三个要点',
        '- [ ] 挑一段 5 分钟视频，按时间轴做一次拆解练习',
        '- [ ] 把拆解结果整理成卡片并归档到笔记库',
    ].join('\\n');

    byId('resultArea').hidden = false;
    byId('resultTitle').textContent = '视频笔记 · 示例课程：从视频到知识卡片';
    byId('markdownContent').innerHTML =
        (typeof renderMarkdown === 'function')
            ? renderMarkdown(markdown)
            : '<pre></pre>';
    if (typeof renderMarkdown !== 'function') {
        byId('markdownContent').querySelector('pre').textContent = markdown;
    }
    byId('outputNotice').hidden = true;
    byId('regenerateBtn').disabled = false;
    byId('copyNoteBtn').disabled = false;
    byId('downloadMdBtn').disabled = false;

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
            "document.getElementById('appVersion')?.textContent === 'v1.0.0-beta.2'",
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

        // 2) progress：合成进度状态
        await evaluate(cdp, PROGRESS_STATE_JS);
        await sleep(300);
        const progress = await capture(cdp, SHOTS[1].file);
        console.log(`[shots] progress -> ${path.relative(REPO_ROOT, progress.file)}`
            + ` (${progress.width}x${progress.height}, ${progress.bytes} bytes)`);

        // 3) result：合成 Markdown 渲染结果（整页截图，覆盖标题→行动清单）
        await evaluate(cdp, RESULT_STATE_JS);
        await sleep(400);
        const result = await capture(cdp, SHOTS[2].file, { fullPage: true });
        console.log(`[shots] result -> ${path.relative(REPO_ROOT, result.file)}`
            + ` (${result.width}x${result.height}, ${result.bytes} bytes)`);

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

main().catch((error) => {
    console.error(`[shots] 失败: ${error.message}`);
    process.exitCode = 1;
});
