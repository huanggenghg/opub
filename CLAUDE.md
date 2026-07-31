## Project Overview

This project, `social-auto-upload`, is a powerful automation tool designed to help content creators and operators efficiently publish video content to multiple domestic and international mainstream social media platforms in one click. The project implements video upload, scheduled release and other functions for platforms such as `Douyin`, `Bilibili`, `Xiaohongshu`, `Kuaishou`, `WeChat Channel`, `Baijiahao` and `TikTok`.

The project consists of a Python backend and a Vue.js frontend.

**Backend:**

*   Framework: Flask
*   Core Functionality:
    *   Handles file uploads and management.
    *   Interacts with a SQLite database to store information about files and user accounts.
    *   Uses `playwright` for browser automation to interact with social media platforms.
    *   Provides a RESTful API for the frontend to consume.
    *   Uses Server-Sent Events (SSE) for real-time communication with the frontend during the login process.

**Frontend:**

*   Framework: Vue.js
*   Build Tool: Vite
*   UI Library: Element Plus
*   State Management: Pinia
*   Routing: Vue Router
*   Core Functionality:
    *   Provides a web interface for managing social media accounts, video files, and publishing videos.
    *   Communicates with the backend via a RESTful API.

**Command-line Interface:**

The project provides one public command-line workflow for terminal users:

*   `hgsau publish`: Read `publish_config.ini`, validate runtime dependencies, check account login per enabled platform, publish, and print a summary.

Platform, account, media, metadata, and schedule settings should be configured in `publish_config.ini`. Standalone platform login/check/upload CLI commands are no longer part of the current mainline.

## Building and Running

### Backend

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install Playwright browser drivers:**
    ```bash
    playwright install chromium
    ```

3.  **Install ffmpeg (required for image-to-video conversion):**
    The `convert_to_video` feature uses moviepy + ffmpeg to turn image notes into slideshow videos. moviepy is installed from `requirements.txt`, but ffmpeg must be installed separately as a system dependency:
    *   macOS: `brew install ffmpeg`
    *   Ubuntu/Debian: `sudo apt-get install ffmpeg`
    *   Windows: download from https://ffmpeg.org/download.html and add to PATH

4.  **Initialize the database:**
    ```bash
    python db/createTable.py
    ```

5.  **Run the backend server:**
    ```bash
    python hgsau_backend.py
    ```
    The backend server will start on `http://localhost:5409`.

### Frontend

1.  **Navigate to the frontend directory:**
    ```bash
    cd hgsau_frontend
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

3.  **Run the development server:**
    ```bash
    npm run dev
    ```
    The frontend development server will start on `http://localhost:5173`.

### Command-line Interface

Install the editable package and run the unified publish entry:

```bash
uv pip install -e .
hgsau publish
```

Temporary overrides are allowed for one publish run:

```bash
hgsau publish --platforms douyin,weibo --video videos/demo.mp4 --title "标题"
```

## Development Conventions

*   The backend code is located in the root directory and the `myUtils` and `uploader` directories.
*   The frontend code is located in the `hgsau_frontend` directory.
*   The project uses a SQLite database for data storage. The database file is located at `db/database.db`.
*   The `conf.example.py` file should be copied to `conf.py` and configured with the appropriate settings.
*   The `requirements.txt` file lists the Python dependencies.
*   The `package.json` file in the `hgsau_frontend` directory lists the frontend dependencies.
