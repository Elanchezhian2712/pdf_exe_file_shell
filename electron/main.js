const { app, BrowserWindow, dialog, ipcMain, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs'); 

let mainWindow = null; 
let pyProc = null; 


function getBackendPath() {
  let executableName = 'backend_server'; 
  if (process.platform === 'win32') {
    executableName += '.exe';
  }
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend_server', executableName);
  } else {
    return path.join(__dirname, '..', 'backend', 'dist', 'backend_server', executableName);
  }
}

function runBackendCommand(commandArgs = []) {
  return new Promise((resolve, reject) => {
    const backendExecutable = getBackendPath();
    const userDataPath = app.getPath('userData'); 

    console.log(`[Electron] User Data Path: ${userDataPath}`);
    console.log(`[Backend] Spawning: ${backendExecutable} ${commandArgs.join(' ')}`);

    const processEnv = {
        ...process.env, 
        'APP_DATA_PATH': userDataPath
    };

    const proc = spawn(backendExecutable, commandArgs, { env: processEnv }); 
    let stderrOutput = ''; 

    proc.stdout.on('data', (data) => {
      console.log(`[Backend STDOUT - ${commandArgs[0] || 'cmd'}]: ${data.toString().trim()}`);
    });

    proc.stderr.on('data', (data) => {
      const errorMsg = data.toString().trim();
      console.error(`[Backend STDERR - ${commandArgs[0] || 'cmd'}]: ${errorMsg}`);
      stderrOutput += errorMsg + '\n';
    });

    proc.on('error', (err) => {
      console.error(`[Backend] Failed to start process for command "${commandArgs.join(' ')}":`, err);
      reject(new Error(`Failed to spawn backend (${commandArgs[0] || 'cmd'}): ${err.message}\nPath: ${backendExecutable}`));
    });
    proc.on('close', (code) => {
      console.log(`[Backend] Process for command "${commandArgs.join(' ')}" exited with code ${code}`);
      if (code === 0) {
        resolve(code);
      } else {
        reject(new Error(`Backend command "${commandArgs.join(' ')}" failed with code ${code}.\nStderr:\n${stderrOutput}`));
      }
    });
    if (commandArgs[0] === 'runserver') {
        pyProc = proc;
    }
  });
}


function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    // icon: path.join(__dirname, 'icons', 'win', 'm-favicon.ico'),
    icon: path.join(__dirname, 'icons/linux/icon.png'),
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
    show: false 
  });

  const minimalMenu = Menu.buildFromTemplate([
    {
        label: '',
        submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
        ]
    },
  ]);
  Menu.setApplicationMenu(minimalMenu);

  const splashPath = path.join(__dirname, 'splash.html');
  console.log('[Electron] Loading splash screen:', splashPath);
  mainWindow.loadFile(splashPath);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}


app.whenReady().then(async () => {
  console.log('[Electron] App Ready.');

  try {
    const userDataPath = app.getPath('userData');
    try {
        if (!fs.existsSync(userDataPath)) {
            fs.mkdirSync(userDataPath, { recursive: true });
            console.log(`[Electron] Created user data directory: ${userDataPath}`);
        }
    } catch (err) {
        console.warn(`[Electron] Could not create user data directory (may be handled by backend): ${err}`);
    }
    console.log('[Electron] Running migrations...');
    await runBackendCommand(['migrate']); 
    console.log('[Electron] Migrations finished successfully.');

    console.log('[Electron] Starting backend server...');
    runBackendCommand(['runserver']).catch(err => {
        console.error('[Electron] Backend server exited unexpectedly after starting:', err);
        if (!mainWindow?.isDestroyed()) {
            dialog.showErrorBox('Backend Runtime Error', `The backend server stopped unexpectedly.\n${err.message}`);
        }
    });
    await new Promise(resolve => setTimeout(resolve, 1500)); 
    createWindow();

  } catch (setupError) { 
    console.error('[Electron] Backend setup failed:', setupError);
    dialog.showErrorBox('Initialization Error', `Failed to initialize the backend:\n${setupError.message}`);
    app.quit();
    return; 
  }
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit(); 
  }
});


ipcMain.on('open-django', (event) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    const targetUrl = 'http://localhost:8000';
    console.log(`[IPC] Received open-django. Loading URL: ${targetUrl}`);
    mainWindow.loadURL(targetUrl)
      .catch(err => {
        console.error(`[Electron] Failed to load Django URL (${targetUrl}):`, err);
        dialog.showErrorBox('Load URL Error', `Could not connect to the backend at ${targetUrl}.\nEnsure the backend started correctly.\nError: ${err.message}`);
      });
  } else {
      console.warn('[IPC] Received open-django, but mainWindow is not available.');
  }
});

app.on('quit', () => {
  console.log('[Electron] Quitting application...');
  if (pyProc) { 
    console.log('[Backend] Terminating running server process...');
    pyProc.kill(); 
    pyProc = null;
  }
});