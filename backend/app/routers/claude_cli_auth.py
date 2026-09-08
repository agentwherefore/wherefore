import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()


class ClaudeLoginSession:
    """Tracks a single in-flight `claude auth login` subprocess.

    Single-operator tool — only one login flow is ever meaningful at a time,
    so this is process-local state, not a DB table.
    """

    def __init__(self) -> None:
        self.process: Optional[asyncio.subprocess.Process] = None
        self.lines: List[str] = []
        self.done = False
        self.success: Optional[bool] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self.process is not None and self.process.returncode is None:
                return  # already running — don't spawn a second one

            self.lines = []
            self.done = False
            self.success = None
            try:
                self.process = await asyncio.create_subprocess_exec(
                    "claude", "auth", "login",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
            except FileNotFoundError:
                self.lines = ["The `claude` CLI isn't installed or isn't on PATH."]
                self.done = True
                self.success = False
                return

            asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        process = self.process
        assert process is not None and process.stdout is not None
        async for raw_line in process.stdout:
            self.lines.append(raw_line.decode("utf-8", errors="replace").rstrip())
        await process.wait()
        self.done = True
        self.success = process.returncode == 0


_session = ClaudeLoginSession()


@router.get("/claude-cli/status")
async def claude_cli_status():
    try:
        process = await asyncio.create_subprocess_exec(
            "claude", "auth", "status", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return json.loads(stdout.decode("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"loggedIn": False}


@router.post("/claude-cli/login")
async def start_claude_login():
    await _session.start()
    return {"status": "started"}


@router.get("/claude-cli/login/stream")
async def stream_claude_login():
    async def event_gen():
        sent = 0
        while True:
            if len(_session.lines) > sent:
                for line in _session.lines[sent:]:
                    yield f"data: {json.dumps({'type': 'line', 'text': line})}\n\n"
                sent = len(_session.lines)
            if _session.done:
                yield f"data: {json.dumps({'type': 'done', 'success': _session.success})}\n\n"
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
