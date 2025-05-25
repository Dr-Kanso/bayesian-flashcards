#!/usr/bin/env python3
"""
Launch script for Bayesian Flashcards application.
Starts both the React frontend and Flask backend.
"""

import subprocess
import sys
import os
import time
import signal
import threading
from pathlib import Path

# Configuration
BACKEND_PORT = 5002
FRONTEND_PORT = 3000
BACKEND_DIR = "backend"
FRONTEND_DIR = "frontend"

class AppLauncher:
    def __init__(self):
        self.backend_process = None
        self.frontend_process = None
        self.root_dir = Path(__file__).parent
        
    def check_dependencies(self):
        """Check if required dependencies are available."""
        print("🔍 Checking dependencies...")
        
        # Check Python
        try:
            python_version = subprocess.check_output([sys.executable, "--version"], 
                                                   stderr=subprocess.STDOUT, text=True)
            print(f"✅ Python: {python_version.strip()}")
        except Exception as e:
            print(f"❌ Python check failed: {e}")
            return False
            
        # Check Node.js
        try:
            node_version = subprocess.check_output(["node", "--version"], 
                                                 stderr=subprocess.STDOUT, text=True)
            print(f"✅ Node.js: {node_version.strip()}")
        except Exception as e:
            print(f"❌ Node.js not found. Please install Node.js from https://nodejs.org/")
            return False
            
        # Check npm (with Windows-specific handling)
        npm_commands = ["npm"]
        if os.name == 'nt':  # Windows
            npm_commands.extend(["npm.cmd", "npm.exe"])
            
        npm_found = False
        for npm_cmd in npm_commands:
            try:
                npm_version = subprocess.check_output([npm_cmd, "--version"], 
                                                    stderr=subprocess.STDOUT, text=True)
                print(f"✅ npm: {npm_version.strip()}")
                npm_found = True
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
                
        if not npm_found:
            print("❌ npm not found. This usually means:")
            print("   1. Node.js was not installed with npm included")
            print("   2. npm is not in your system PATH")
            print("   3. You might need to restart your terminal/command prompt")
            print("   Try reinstalling Node.js from https://nodejs.org/ (includes npm)")
            return False
            
        return True
        
    def setup_backend(self):
        """Install Python dependencies and setup backend."""
        print("\n🐍 Setting up backend...")
        backend_path = self.root_dir / BACKEND_DIR
        
        if not backend_path.exists():
            print(f"❌ Backend directory not found: {backend_path}")
            return False
            
        # Check if requirements.txt exists
        requirements_file = backend_path / "requirements.txt"
        if requirements_file.exists():
            print("📦 Installing Python dependencies...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                             cwd=backend_path, check=True, capture_output=True)
                print("✅ Backend dependencies installed")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install backend dependencies: {e}")
                return False
        else:
            print("⚠️  No requirements.txt found, skipping dependency installation")
            
        return True
        
    def setup_frontend(self):
        """Install Node.js dependencies and setup frontend."""
        print("\n⚛️  Setting up frontend...")
        frontend_path = self.root_dir / FRONTEND_DIR
        
        if not frontend_path.exists():
            print(f"❌ Frontend directory not found: {frontend_path}")
            return False
            
        # Check if package.json exists
        package_json = frontend_path / "package.json"
        if package_json.exists():
            # Check if node_modules exists
            node_modules = frontend_path / "node_modules"
            if not node_modules.exists():
                print("📦 Installing Node.js dependencies...")
                try:
                    # Use the same npm command detection logic
                    npm_cmd = "npm"
                    if os.name == 'nt':  # Windows
                        for cmd in ["npm", "npm.cmd", "npm.exe"]:
                            try:
                                subprocess.check_output([cmd, "--version"], 
                                                      stderr=subprocess.STDOUT)
                                npm_cmd = cmd
                                break
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                continue
                    
                    subprocess.run([npm_cmd, "install"], cwd=frontend_path, check=True, capture_output=True)
                    print("✅ Frontend dependencies installed")
                except subprocess.CalledProcessError as e:
                    print(f"❌ Failed to install frontend dependencies: {e}")
                    return False
            else:
                print("✅ Frontend dependencies already installed")
        else:
            print("❌ No package.json found in frontend directory")
            return False
            
        return True
        
    def start_backend(self):
        """Start the Flask backend server."""
        print(f"\n🚀 Starting backend server on port {BACKEND_PORT}...")
        backend_path = self.root_dir / BACKEND_DIR
        
        try:
            # Set environment variables
            env = os.environ.copy()
            env['FLASK_ENV'] = 'development'
            env['FLASK_DEBUG'] = '1'
            
            self.backend_process = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=backend_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start thread to monitor backend output
            threading.Thread(target=self._monitor_backend_output, daemon=True).start()
            
            # Wait a moment to see if the process starts successfully
            time.sleep(2)
            if self.backend_process.poll() is not None:
                print("❌ Backend failed to start")
                return False
                
            print(f"✅ Backend started (PID: {self.backend_process.pid})")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start backend: {e}")
            return False
            
    def start_frontend(self):
        """Start the React frontend server."""
        print(f"\n⚛️  Starting frontend server on port {FRONTEND_PORT}...")
        frontend_path = self.root_dir / FRONTEND_DIR
        
        try:
            # Set environment variables
            env = os.environ.copy()
            env['BROWSER'] = 'none'  # Prevent auto-opening browser
            env['PORT'] = str(FRONTEND_PORT)
            
            # Use the same npm command detection logic
            npm_cmd = "npm"
            if os.name == 'nt':  # Windows
                for cmd in ["npm", "npm.cmd", "npm.exe"]:
                    try:
                        subprocess.check_output([cmd, "--version"], 
                                              stderr=subprocess.STDOUT)
                        npm_cmd = cmd
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
            
            self.frontend_process = subprocess.Popen(
                [npm_cmd, "start"],
                cwd=frontend_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start thread to monitor frontend output
            threading.Thread(target=self._monitor_frontend_output, daemon=True).start()
            
            # Wait for frontend to be ready
            print("⏳ Waiting for frontend to be ready...")
            start_time = time.time()
            timeout = 60  # 60 seconds timeout
            
            while time.time() - start_time < timeout:
                if self.frontend_process.poll() is not None:
                    print("❌ Frontend failed to start")
                    return False
                time.sleep(1)
                
            print(f"✅ Frontend started (PID: {self.frontend_process.pid})")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start frontend: {e}")
            return False
            
    def _monitor_backend_output(self):
        """Monitor backend process output."""
        if not self.backend_process:
            return
            
        try:
            for line in iter(self.backend_process.stdout.readline, ''):
                if line:
                    print(f"[BACKEND] {line.rstrip()}")
        except Exception:
            pass
            
    def _monitor_frontend_output(self):
        """Monitor frontend process output."""
        if not self.frontend_process:
            return
            
        try:
            for line in iter(self.frontend_process.stdout.readline, ''):
                if line:
                    # Filter out some noisy output
                    line = line.rstrip()
                    if any(skip in line.lower() for skip in ['compiled successfully', 'webpack compiled']):
                        print(f"[FRONTEND] {line}")
                    elif 'local:' in line.lower() or 'network:' in line.lower():
                        print(f"[FRONTEND] {line}")
        except Exception:
            pass
            
    def cleanup(self):
        """Clean up processes."""
        print("\n🧹 Cleaning up...")
        
        if self.frontend_process:
            try:
                self.frontend_process.terminate()
                self.frontend_process.wait(timeout=5)
                print("✅ Frontend process terminated")
            except subprocess.TimeoutExpired:
                self.frontend_process.kill()
                print("⚠️  Frontend process killed (timeout)")
            except Exception as e:
                print(f"⚠️  Error terminating frontend: {e}")
                
        if self.backend_process:
            try:
                self.backend_process.terminate()
                self.backend_process.wait(timeout=5)
                print("✅ Backend process terminated")
            except subprocess.TimeoutExpired:
                self.backend_process.kill()
                print("⚠️  Backend process killed (timeout)")
            except Exception as e:
                print(f"⚠️  Error terminating backend: {e}")
                
    def run(self):
        """Main run method."""
        print("🎯 Bayesian Flashcards Application Launcher")
        print("=" * 50)
        
        # Setup signal handler for cleanup
        def signal_handler(signum, frame):
            print("\n\n⚠️  Interrupt received, shutting down...")
            self.cleanup()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Check dependencies
            if not self.check_dependencies():
                print("\n❌ Dependency check failed. Please install missing dependencies.")
                return 1
                
            # Setup backend
            if not self.setup_backend():
                print("\n❌ Backend setup failed.")
                return 1
                
            # Setup frontend
            if not self.setup_frontend():
                print("\n❌ Frontend setup failed.")
                return 1
                
            # Start backend
            if not self.start_backend():
                print("\n❌ Failed to start backend.")
                return 1
                
            # Start frontend
            if not self.start_frontend():
                print("\n❌ Failed to start frontend.")
                self.cleanup()
                return 1
                
            # Print success message
            print("\n" + "=" * 50)
            print("🎉 Application started successfully!")
            print(f"🌐 Frontend: http://localhost:{FRONTEND_PORT}")
            print(f"🔧 Backend API: http://localhost:{BACKEND_PORT}/api")
            print("\n💡 Press Ctrl+C to stop the application")
            print("=" * 50)
            
            # Keep the main thread alive
            try:
                while True:
                    time.sleep(1)
                    # Check if processes are still running
                    if self.backend_process and self.backend_process.poll() is not None:
                        print("\n❌ Backend process died unexpectedly")
                        break
                    if self.frontend_process and self.frontend_process.poll() is not None:
                        print("\n❌ Frontend process died unexpectedly")
                        break
            except KeyboardInterrupt:
                pass
                
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            return 1
        finally:
            self.cleanup()
            
        return 0

if __name__ == "__main__":
    launcher = AppLauncher()
    sys.exit(launcher.run())
