import asyncio
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from pyngrok import ngrok
except ImportError:
    ngrok = None

_tunnel = None
_AUTHTOKEN_ENV_VARS = ("NGROK_AUTHTOKEN", "NGROK_AUTH_TOKEN", "NGROK_TOKEN")


def _is_enabled() -> bool:
    return os.getenv("NGROK_AUTOSTART", "1").lower() in {"1", "true", "yes", "on"}


def _configure_auth_token() -> None:
    if ngrok is None:
        return
    for env_var in _AUTHTOKEN_ENV_VARS:
        token = os.getenv(env_var, "").strip()
        if token:
            ngrok.set_auth_token(token)
            return


async def start_tunnel(port: int = 8000) -> Optional[str]:
    if not _is_enabled():
        return None
    if ngrok is None:
        print("pyngrok is not installed; skipping ngrok tunnel startup")
        return None

    _configure_auth_token()

    def _start():
        return ngrok.connect(addr=port, bind_tls=True)

    global _tunnel
    _tunnel = await asyncio.to_thread(_start)
    return _tunnel.public_url


async def stop_tunnel() -> None:
    global _tunnel
    if ngrok is None:
        return
    if _tunnel is None:
        return
    await asyncio.to_thread(ngrok.disconnect, _tunnel.public_url)
    _tunnel = None
