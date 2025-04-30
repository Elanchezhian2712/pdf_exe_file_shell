// ~/Desktop/demo_work/electron/main.js

const { app, BrowserWindow, dialog, ipcMain, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs'); // Import fs for directory check/creation (optional but safer)

let mainWindow = null; // Reference to the main window
let pyProc = null; // Reference to the RUNNING backend server process

// --- Function to get the path to the backend executable ---
function getBackendPath() {
  let executableName = 'backend_server'; // Name given to PyInstaller
  if (process.platform === 'win32') {
    executableName += '.exe';
  }
  // Check if the app is packaged or running in development
  if (app.isPackaged) {
    // Path when packaged: <app root>/resources/backend_server/<executableName>
    return path.join(process.resourcesPath, 'backend_server', executableName);
  } else {
    // Path in development: <project root>/backend/dist/backend_server/<executableName>
    return path.join(__dirname, '..', 'backend', 'dist', 'backend_server', executableName);
  }
}

// --- Function to run a backend command (migrate, runserver) ---
function runBackendCommand(commandArgs = []) {
  return new Promise((resolve, reject) => {
    const backendExecutable = getBackendPath();
    const userDataPath = app.getPath('userData'); // Get writable path

    // Log paths for debugging
    console.log(`[Electron] User Data Path: ${userDataPath}`);
    console.log(`[Backend] Spawning: ${backendExecutable} ${commandArgs.join(' ')}`);

    // Prepare environment variables for the child process
    const processEnv = {
        ...process.env, // Inherit existing environment
        // Pass the User Data Path to the Python script
        'APP_DATA_PATH': userDataPath
    };

    // Spawn the backend process
    const proc = spawn(backendExecutable, commandArgs, { env: processEnv }); // Pass env
    let stderrOutput = ''; // Collect stderr for error reporting

    // Handle standard output from the backend
    proc.stdout.on('data', (data) => {
      console.log(`[Backend STDOUT - ${commandArgs[0] || 'cmd'}]: ${data.toString().trim()}`);
    });

    // Handle standard error from the backend
    proc.stderr.on('data', (data) => {
      const errorMsg = data.toString().trim();
      console.error(`[Backend STDERR - ${commandArgs[0] || 'cmd'}]: ${errorMsg}`);
      stderrOutput += errorMsg + '\n'; // Append to collected stderr
    });

    // Handle errors related to spawning the process itself
    proc.on('error', (err) => {
      console.error(`[Backend] Failed to start process for command "${commandArgs.join(' ')}":`, err);
      reject(new Error(`Failed to spawn backend (${commandArgs[0] || 'cmd'}): ${err.message}\nPath: ${backendExecutable}`));
    });

    // Handle process exit
    proc.on('close', (code) => {
      console.log(`[Backend] Process for command "${commandArgs.join(' ')}" exited with code ${code}`);
      if (code === 0) {
        resolve(code); // Success!
      } else {
        // Failure - reject the promise with an error message including stderr
        reject(new Error(`Backend command "${commandArgs.join(' ')}" failed with code ${code}.\nStderr:\n${stderrOutput}`));
      }
    });

    // Store the process reference *only* if it's the long-running server process
    if (commandArgs[0] === 'runserver') {
        pyProc = proc;
    }
  });
}


// --- Function to create the Electron Window ---
function createWindow() {
  // Create the browser window.
  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    // icon: path.join(__dirname, 'icons', 'win', 'm-favicon.ico'),
    icon: path.join(__dirname, 'icons/linux/icon.png'),
    webPreferences: {
      // preload: path.join(__dirname, 'preload.js'), // Consider using preload for better security
      // --- TEMPORARY FOR SIMPLICITY ---
      // Allow require in renderer for splash.html IPC
      // WARNING: Less secure than using a preload script.
      nodeIntegration: true,
      contextIsolation: false,
      
      // --- END TEMPORARY ---
    },
    show: false // Don't show window initially, wait for splash or content
  });

  // --- Application Menu ---
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
    // Add other menus (File, Edit, Help) as needed
  ]);
  Menu.setApplicationMenu(minimalMenu);

  // Load the splash screen initially
  const splashPath = path.join(__dirname, 'splash.html');
  console.log('[Electron] Loading splash screen:', splashPath);
  mainWindow.loadFile(splashPath);

  // Show window gracefully when it's ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Handle window closure
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// --- Electron App Lifecycle Callbacks ---

// Executed when Electron initialization is complete.
app.whenReady().then(async () => {
  console.log('[Electron] App Ready.');

  try {
    // Optional: Ensure the user data directory exists before backend tries to use it
    const userDataPath = app.getPath('userData');
    try {
        if (!fs.existsSync(userDataPath)) {
            fs.mkdirSync(userDataPath, { recursive: true });
            console.log(`[Electron] Created user data directory: ${userDataPath}`);
        }
    } catch (err) {
        console.warn(`[Electron] Could not create user data directory (may be handled by backend): ${err}`);
    }


    // 1. Run Migrations - Wait for this to complete or fail
    console.log('[Electron] Running migrations...');
    await runBackendCommand(['migrate']); // Backend now writes DB to userDataPath
    console.log('[Electron] Migrations finished successfully.');

    // 2. Start the Django Server - Run asynchronously
    console.log('[Electron] Starting backend server...');
    runBackendCommand(['runserver']).catch(err => {
        // Handle server crashing *after* it successfully started
        // This catch is for the promise returned by runBackendCommand
        console.error('[Electron] Backend server exited unexpectedly after starting:', err);
        if (!mainWindow?.isDestroyed()) {
            dialog.showErrorBox('Backend Runtime Error', `The backend server stopped unexpectedly.\n${err.message}`);
        }
    });

    // Give the server a brief moment to initialize before creating the window
    // A more robust approach would involve checking backend stdout for a ready message
    await new Promise(resolve => setTimeout(resolve, 1500)); // Wait 1.5 seconds

    // 3. Create the main application window (loads splash.html)
    createWindow();

  } catch (setupError) { // Catch errors primarily from the 'migrate' command
    console.error('[Electron] Backend setup failed:', setupError);
    dialog.showErrorBox('Initialization Error', `Failed to initialize the backend:\n${setupError.message}`);
    app.quit(); // Quit if essential setup (like migration) fails
    return; // Stop further execution in this block
  }

  // macOS specific: Re-create window when dock icon is clicked
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      // Consider if setup needs re-running or just create window
      createWindow();
    }
  });
});

// Quit when all windows are closed (except on macOS)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit(); // Triggers the 'quit' event
  }
});

// --- IPC Handler for Splash Screen Button ---
ipcMain.on('open-django', (event) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    const targetUrl = 'http://localhost:8000'; // URL served by Django backend
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


// --- Ensure backend server process is terminated when Electron quits ---
app.on('quit', () => {
  console.log('[Electron] Quitting application...');
  if (pyProc) { // pyProc references the 'runserver' process
    console.log('[Backend] Terminating running server process...');
    pyProc.kill(); // Send SIGTERM signal
    pyProc = null;
  }
});