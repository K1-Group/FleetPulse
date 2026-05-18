from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os


_static_dir = os.path.join(os.path.dirname(__file__), "static")
_NO_CACHE_HEADERS = {"Cache-Control": "no-store, must-revalidate"}


def _static_file_response(path: str) -> FileResponse:
    filename = os.path.basename(path)
    if filename in {"index.html", "sw.js"}:
        return FileResponse(path, headers=_NO_CACHE_HEADERS)
    return FileResponse(path)


if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(_static_dir, full_path)
        if os.path.isfile(file_path):
            return _static_file_response(file_path)
        return _static_file_response(os.path.join(_static_dir, "index.html"))
