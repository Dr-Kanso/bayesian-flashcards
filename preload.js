const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // Session management for navigation guards
  checkActiveSession: () => {
    // This would check if there's an active study session
    // For now, return false - you can implement session checking logic
    return Promise.resolve(false);
  },
  
  confirmNavigation: () => {
    // Show confirmation dialog for navigation during active session
    return Promise.resolve(true);
  },
  
  endSession: () => {
    // End the current session
    return Promise.resolve();
  },
  
  showPromptDialog: (message, defaultValue) => {
    // Instead of using prompt(), post a message to the renderer process
    // The renderer will handle showing the custom modal
    return new Promise((resolve) => {
      // Store the resolve function globally so the renderer can call it
      window.electronPromptResolve = resolve;
      
      // Send message to renderer to show custom prompt
      window.postMessage({
        type: 'SHOW_CUSTOM_PROMPT',
        message,
        defaultValue
      }, '*');
    });
  }
});
