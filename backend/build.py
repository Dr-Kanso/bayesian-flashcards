import PyInstaller.__main__
import os
import sys

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Change to the backend directory
os.chdir(script_dir)

# PyInstaller arguments
args = [
    '--onefile',
    '--name=app',
    '--distpath=dist',
    '--workpath=build',
    '--specpath=.',
    'app.py'
]

# Run PyInstaller
PyInstaller.__main__.run(args)
