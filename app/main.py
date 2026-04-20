from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.routes.main import router
from app.config import set_base_url
from app.services.ngrok_tunnel import start_tunnel, stop_tunnel


class MobileRestrictMiddleware(BaseHTTPMiddleware):
    MOBILE_USER_AGENTS = [
        "android",
        "iphone",
        "ipad",
        "ipod",
        "mobile",
        "phone",
        "blackberry",
        "windows phone",
        "webos",
        "opera mini",
        "opera mobi",
    ]

    def is_mobile(self, user_agent: str) -> bool:
        if not user_agent:
            return False
        ua_lower = user_agent.lower()
        return any(mobile in ua_lower for mobile in self.MOBILE_USER_AGENTS)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        user_agent = request.headers.get("user-agent", "")

        if self.is_mobile(user_agent):
            if (
                path == "/join"
                or path.startswith("/api/")
                or path.startswith("/static/")
                or path == "/ws"
            ):
                return await call_next(request)
            else:
                return RedirectResponse(url="/join")

        return await call_next(request)


app = FastAPI(title="YTBQ - YouTube Queue")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(MobileRestrictMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico")


app.include_router(router)


@app.on_event("startup")
async def startup_event():
    try:
        public_url = await start_tunnel(port=8000)
        if public_url:
            set_base_url(public_url.rstrip("/"))
            print(f"ngrok tunnel started: {public_url}")
    except Exception as e:
        print(f"ngrok tunnel startup failed: {e}")
    print("YTBQ server starting up...")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        await stop_tunnel()
    except Exception as e:
        print(f"ngrok tunnel shutdown failed: {e}")
    print("YTBQ server shutting down...")
