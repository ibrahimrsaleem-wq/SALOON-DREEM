'use strict';

const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const net = require('node:net');
const fs = require('node:fs');
const path = require('node:path');

const APP_TITLE = 'SALOON DREEM';
let mainWindow = null;
let serverProcess = null;
let serverLogFd = null;
let quitting = false;

function writeStartupPage() {
  return `<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${APP_TITLE}</title><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#101916;color:#f6f1e5;font-family:Segoe UI,Tahoma,sans-serif"><main style="text-align:center;padding:28px"><div style="font-size:58px;color:#d9b77a;font-weight:800">D✦</div><h1>${APP_TITLE}</h1><p>جارٍ تشغيل النظام وتأمين قاعدة بيانات الصالون…</p><small>قد تستغرق عملية بدء التشغيل بضع ثوانٍ في أول مرة.</small></main></body></html>`;
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const address = probe.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      probe.close(error => error ? reject(error) : resolve(port));
    });
  });
}

function startBackend(port) {
  const dataDir = path.join(app.getPath('userData'), 'data');
  fs.mkdirSync(dataDir, { recursive: true });
  const logPath = path.join(app.getPath('userData'), 'backend.log');
  serverLogFd = fs.openSync(logPath, 'a');
  const env = {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(port),
    APP_TIMEZONE: process.env.APP_TIMEZONE || 'Asia/Gaza',
    DATA_DIR: dataDir,
    DATABASE_PATH: path.join(dataDir, 'saloon_dreem.db')
  };

  if (app.isPackaged) {
    const executable = path.join(process.resourcesPath, 'server', 'saloon-dreem-server.exe');
    if (!fs.existsSync(executable)) throw new Error(`لم يتم العثور على خادم التطبيق: ${executable}`);
    serverProcess = spawn(executable, [], { env, windowsHide: true, stdio: ['ignore', serverLogFd, serverLogFd] });
  } else {
    const projectRoot = path.resolve(__dirname, '..');
    const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    serverProcess = spawn(python, ['-m', 'backend.app.server_entry'], { cwd: projectRoot, env, windowsHide: true, stdio: ['ignore', serverLogFd, serverLogFd] });
  }
  serverProcess.once('error', error => console.error('Backend process error:', error));
  return serverProcess;
}

async function waitForBackend(baseUrl, child, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`توقف الخادم أثناء بدء التشغيل (exit ${child.exitCode}). راجع سجل backend.log في مجلد بيانات التطبيق.`);
    }
    try {
      const response = await fetch(`${baseUrl}/api/health`, { signal: AbortSignal.timeout(1200) });
      if (response.ok) return;
    } catch (_) {
      // The local service is still starting.
    }
    await new Promise(resolve => setTimeout(resolve, 350));
  }
  throw new Error('لم يستجب خادم الصالون خلال المهلة. راجع سجل backend.log في مجلد بيانات التطبيق.');
}

async function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 360,
    minHeight: 620,
    show: false,
    title: APP_TITLE,
    backgroundColor: '#101916',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true
    }
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://') || url.startsWith('http://')) void shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (url !== mainWindow.webContents.getURL() && !url.startsWith('http://127.0.0.1:')) event.preventDefault();
  });
  mainWindow.once('ready-to-show', () => mainWindow && mainWindow.show());
  await mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(writeStartupPage())}`);

  const port = await findFreePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const child = startBackend(port);
  await waitForBackend(baseUrl, child);
  if (mainWindow && !mainWindow.isDestroyed()) await mainWindow.loadURL(baseUrl);
}

function stopBackend() {
  if (serverProcess && serverProcess.exitCode === null) {
    try { serverProcess.kill(); } catch (_) { /* process may already have exited */ }
  }
  serverProcess = null;
  if (serverLogFd !== null) {
    try { fs.closeSync(serverLogFd); } catch (_) { /* already closed */ }
    serverLogFd = null;
  }
}

app.whenReady().then(async () => {
  try {
    await createMainWindow();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await dialog.showMessageBox({ type: 'error', title: `${APP_TITLE} — تعذر التشغيل`, message, detail: 'لم يتم حذف قاعدة البيانات. حاول إغلاق التطبيق وتشغيله مرة أخرى.' });
    quitting = true;
    stopBackend();
    app.quit();
  }
});

app.on('before-quit', () => {
  quitting = true;
  stopBackend();
});
app.on('window-all-closed', () => {
  if (!quitting) app.quit();
});
