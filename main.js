const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow;
let backendProcess;
const BACKEND_PORT = 5002; // Match your backend port
const isDev = process.env.NODE_ENV === 'development';

// Platform-specific backend executable paths
function getBackendPath() {
  const platform = process.platform;
  const basePath = isDev 
    ? path.join(__dirname, 'backend') 
    : path.join(process.resourcesPath, 'backend');
  
  if (platform === 'win32') {
    return path.join(basePath, 'dist', 'app.exe');
  } else if (platform === 'darwin') {
    return path.join(basePath, 'dist', 'app');
  } else {
    return path.join(basePath, 'dist', 'app');
  }
}

// Start the Python backend
function startBackend() {
  return new Promise((resolve, reject) => {
    const backendPath = getBackendPath();
    
    console.log('Starting backend from:', backendPath);
    
    // Check if backend executable exists
    if (!fs.existsSync(backendPath)) {
      const errorMsg = `Backend executable not found at: ${backendPath}`;
      console.error(errorMsg);
      reject(new Error(errorMsg));
      return;
    }

    // For development, you might want to run the Python script directly
    if (isDev && !fs.existsSync(backendPath)) {
      // Fallback to running Python script directly in development
      const pythonScript = path.join(__dirname, 'backend', 'app.py');
      if (fs.existsSync(pythonScript)) {
        backendProcess = spawn('python', [pythonScript], {
          cwd: path.join(__dirname, 'backend'),
          stdio: 'pipe'
        });
      } else {
        reject(new Error('Neither backend executable nor Python script found'));
        return;
      }
    } else {
      // Run the compiled executable
      backendProcess = spawn(backendPath, [], {
        stdio: 'pipe',
        cwd: path.dirname(backendPath)
      });
    }

    if (!backendProcess) {
      reject(new Error('Failed to start backend process'));
      return;
    }

    backendProcess.stdout.on('data', (data) => {
      console.log('Backend stdout:', data.toString());
    });

    backendProcess.stderr.on('data', (data) => {
      console.error('Backend stderr:', data.toString());
    });

    backendProcess.on('error', (error) => {
      console.error('Backend process error:', error);
      reject(error);
    });

    backendProcess.on('exit', (code, signal) => {
      console.log(`Backend process exited with code ${code} and signal ${signal}`);
    });

    // Wait a bit for the backend to start up
    setTimeout(() => {
      // Test if backend is responding
      const http = require('http');
      const req = http.get(`http://localhost:${BACKEND_PORT}/api/health`, (res) => {
        if (res.statusCode === 200) {
          console.log('Backend is responding');
          resolve();
        } else {
          reject(new Error(`Backend responded with status ${res.statusCode}`));
        }
      });

      req.on('error', (error) => {
        console.log('Backend not yet responding, continuing anyway...');
        // Don't reject here - the backend might still be starting up
        resolve();
      });

      req.setTimeout(5000, () => {
        req.destroy();
        console.log('Backend health check timeout, continuing anyway...');
        resolve();
      });
    }, 3000);
  });
}

// Stop the backend process
function stopBackend() {
  if (backendProcess) {
    console.log('Stopping backend process...');
    backendProcess.kill('SIGTERM');
    
    // Force kill after 5 seconds if it doesn't stop gracefully
    setTimeout(() => {
      if (backendProcess && !backendProcess.killed) {
        console.log('Force killing backend process...');
        backendProcess.kill('SIGKILL');
      }
    }, 5000);
    
    backendProcess = null;
  }
}

// Create the main application window
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, 'assets', 'icon.png'), // Add your app icon
    title: 'Bayesian Flashcards',
    show: false // Don't show until ready
  });

  // Load the React app
  const frontendPath = isDev 
    ? 'http://localhost:3000' // React dev server
    : `file://${path.join(__dirname, 'frontend', 'build', 'index.html')}`;
  
  console.log('Loading frontend from:', frontendPath);
  mainWindow.loadURL(frontendPath);

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    
    // Open DevTools in development
    if (isDev) {
      mainWindow.webContents.openDevTools();
    }
  });

  // Handle window closed
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Handle navigation - prevent external links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    require('electron').shell.openExternal(url);
    return { action: 'deny' };
  });
}

// App event handlers
app.whenReady().then(async () => {
  try {
    console.log('Starting Bayesian Flashcards...');
    
    // Start backend first
    await startBackend();
    console.log('Backend started successfully');
    
    // Create window
    createWindow();
    console.log('Main window created');
    
  } catch (error) {
    console.error('Failed to start application:', error);
    
    // Show error dialog
    dialog.showErrorBox(
      'Startup Error',
      `Failed to start the application: ${error.message}\n\nPlease check that all required files are present.`
    );
    
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', (event) => {
  console.log('App is quitting...');
  stopBackend();
});

// Handle app quit
process.on('exit', () => {
  stopBackend();
});

process.on('SIGINT', () => {
  stopBackend();
  process.exit(0);
});

process.on('SIGTERM', () => {
  stopBackend();
  process.exit(0);
});
