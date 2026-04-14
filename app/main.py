from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.routes.main import router


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

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    print("YTBQ server starting up...")


@app.on_event("shutdown")
async def shutdown_event():
    print("YTBQ server shutting down...")
