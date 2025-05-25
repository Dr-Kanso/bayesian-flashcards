# Bayesian Adaptive SRS Flashcard System (ADHD-aware)

This project implements a research-grade, fully extensible **spaced repetition system (SRS)** that leverages Bayesian memory modeling and adaptive cognitive features for individualized, optimal review scheduling. It's designed to support diverse learners, with special consideration for users with ADHD and variable attention.

---

## Quick Start

### 🚀 One-Click Launch

The easiest way to run the application is using the launch script:

**Windows:**
```cmd
launch.bat
```

**macOS/Linux:**
```bash
chmod +x launch.sh
./launch.sh
```

**Or directly with Python:**
```bash
python launch.py
```

This will automatically:
- Check for required dependencies (Python, Node.js, npm)
- Install backend dependencies (Flask, etc.)
- Install frontend dependencies (React, etc.)
- Start the backend server on port 5002
- Start the frontend server on port 3000
- Open the application at http://localhost:3000

### 📋 Prerequisites

- **Python 3.8+** with pip
- **Node.js 16+** with npm

---

## Key Features

### 📊 Bayesian Memory Modeling
- Every card's review interval is computed using a per-card Beta posterior, modeling memory decay and recall probability over time.
- Personalized decay rates are further adapted from global user recall statistics.

### 🎯 Desirable Difficulty Targeting
- Schedules reviews to maintain an empirically optimal ~80% correct recall rate ("desirable difficulty").
- Automatically adjusts intervals to prevent both under- and overlearning.

### 🧠 Cognitive & Behavioral Adaptivity
- **Pomodoro-based session management** with dynamic fatigue detection and session break suggestions.
- **Real-time focus drop monitoring** and review rebalancing ("rescue mode") to mitigate distractions or attention lapses.
- **Meta-cognitive spot-checks** and calibration for self-assessment accuracy.

### 🖼️ Rich Content Support
- Create and study flashcards with rich text and images on both front and back.
- Organize cards into decks.

### 🛠️ Modern, Modular Stack
- **Frontend:** React, with support for rich text editors, image upload, and live Bayesian visualizations (Plotly/Chart.js).
- **Backend:** Python (Flask/FastAPI) for all memory modeling, session scheduling, and data endpoints.
- **Desktop-ready:** Ships as a cross-platform desktop app (Mac, Windows, Linux) via Tauri or Electron.

### 📈 Data-Driven Visualization
- Live visual feedback for Bayesian recall distributions, interval histories, session progress, and cognitive indicators—all toggleable during study.

---

## Manual Setup

If you prefer to run the frontend and backend separately:

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
python app.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm start
```

---

## Troubleshooting

### Common Issues

1. **Port conflicts**: If ports 3000 or 5002 are in use, stop other applications or modify the ports in `launch.py`
2. **Permission errors**: On macOS/Linux, make sure `launch.sh` is executable: `chmod +x launch.sh`
3. **Node.js not found**: Install Node.js from https://nodejs.org/
4. **Python dependencies fail**: Try upgrading pip: `python -m pip install --upgrade pip`

### Getting Help

- Check the console output for detailed error messages
- Ensure all prerequisites are installed
- Try running the backend and frontend separately to isolate issues

---

