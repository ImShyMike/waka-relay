#!/usr/bin/env python3

"""
WakaTime Relay - Server that relays WakaTime requests to multiple instances.
Copyright (c) 2025 ImShyMike
(not affiliated with WakaTime)
"""

import asyncio
import base64
import logging
import sys
from hmac import compare_digest
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse

import httpx
import toml
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

CURRENT_VERSION = "0.1.0"

app = FastAPI(
    title="WakaTime Relay",
    description="Server that relays WakaTime requests to multiple instances.",
    version=CURRENT_VERSION,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("relay.log")],
)
logger = logging.getLogger(__name__)

USER_HOME = str(Path.home())
CONFIG_PATH = Path(USER_HOME) / ".waka-relay.toml"

REQUEST_SEMAPHORE = asyncio.Semaphore(25)

CONFIG = {}


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def catch_everything(request: Request, full_path: str):
    """Catches all incoming requests and forwards them to wakatime instances."""

    instances = CONFIG.get("instances", {})

    if full_path == "":
        return RedirectResponse(list(instances.keys())[0], status_code=307)

    if not CONFIG:
        logging.error("Configuration not loaded.")
        return JSONResponse(
            content={"error": "Configuration not loaded."}, status_code=500
        )

    if CONFIG.get("require_api_key", False):
        if not CONFIG.get("api_key"):
            logging.error("API key is missing from the config.")
            return JSONResponse(
                content={"error": "API key is not properly configured."},
                status_code=401,
            )

        auth_header = request.headers.get("authorization")

        if not auth_header:
            logging.info("API key is required but not provided.")
            return JSONResponse(
                content={"error": "API key is required."}, status_code=401
            )

        if not auth_header.startswith("Basic "):
            logging.info("Invalid API key format.")
            return JSONResponse(
                content={"error": "Invalid API key format."}, status_code=401
            )

        api_key = base64.b64decode(auth_header.split(" ")[1]).decode()

        if not compare_digest(api_key, CONFIG.get("api_key", "")):
            logging.info("Invalid API key.")
            return JSONResponse(content={"error": "Invalid API key."}, status_code=401)

    if not instances:
        logging.error("No WakaTime instances configured.")
        return JSONResponse(
            content={"error": "No WakaTime instances configured."}, status_code=500
        )

    async with httpx.AsyncClient(timeout=CONFIG.get("timeout", 25)) as client:
        responses = [
            handle_single_request(
                request=request,
                url=await make_url(url, full_path),
                client=client,
                api_key=key,
            )
            for url, key in instances.items()
        ]
        responses = await asyncio.gather(*responses)

    primary_response = responses[0]

    if full_path == "users/current/statusbar/today":
        grand_total = (
            primary_response.get("response", {}).get("data", {}).get("grand_total", {})
        )
        if grand_total.get("text"):
            primary_response["response"]["data"]["grand_total"]["text"] += CONFIG.get(
                "time_suffix", ""
            )

    return JSONResponse(
        content=primary_response["response"],
        status_code=primary_response["status_code"],
    )


async def make_url(url: str, full_path: str) -> str:
    """Constructs the full URL for the request."""
    parsed_url = urlparse(url)

    if parsed_url.path.endswith("/"):
        return f"{url}{full_path}"

    return f"{url}/{full_path}"


async def handle_single_request(
    request: Request,
    url: str,
    client: httpx.AsyncClient,
    api_key: str,
) -> Dict[str, Any]:
    """Handles a single request to a WakaTime instance."""

    async with REQUEST_SEMAPHORE:
        body = await request.body()

        headers = dict(request.headers)
        headers["authorization"] = (
            f"Basic {base64.b64encode(api_key.encode()).decode()}"
        )
        headers["user-agent"] += f"waka-relay/{CURRENT_VERSION}"

        headers.pop("host", None)

        response = await client.request(
            method=request.method, url=url, content=body, headers=headers
        )

        return {
            "status_code": response.status_code,
            "response": response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text,
        }


def load_config(is_retry: bool = False) -> Dict:
    """Loads the config file from the user's home directory.

    Args:
        is_retry (bool, optional): Set if the read is a retry. Defaults to False.
    """
    try:
        config = toml.load(CONFIG_PATH)

        if "relay" not in config:
            logging.error("Relay section not found in config file.")
            raise ValueError("Relay section not found in config file.")

        return config["relay"]

    except FileNotFoundError:
        if is_retry:
            logging.warning("Config file not found. Unable to create it.")
            logging.warning("Please make it yourself add your API keys.")
            logging.warning("Exiting...")
            sys.exit(1)

        create_default_config()
        logging.info("Loading the generated config file.")
        return load_config(True)

    except toml.TomlDecodeError as e:
        logging.error("Error reading config file: %s", e)
        logging.warning("Exiting...")
        sys.exit(1)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.critical("An unexpected error occurred: %s", e)
        sys.exit(1)


def create_default_config() -> None:
    """Creates a default config file if it doesn't exist."""
    try:
        config = {
            "relay": {
                "host": "0.0.0.0",
                "port": "25892",
                "workers": 4,
                "timeout": 25,
                "time_suffix": " (Relayed)",
                "require_api_key": False,
                "api_key": "",
                "instances": {"https://api.wakatime.com/api/v1": "API KEY HERE"},
            }
        }

        with open(CONFIG_PATH, "w", encoding="utf8") as f:
            toml.dump(config, f)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.critical("An error occurred while creating the default config: %s", e)
        sys.exit(1)


CONFIG = load_config()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=CONFIG.get("host", "0.0.0.0"),
        port=CONFIG.get("port", 25892),
        log_level="info",
        workers=CONFIG.get("workers", None),
    )
