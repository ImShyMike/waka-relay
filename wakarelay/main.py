#!/usr/bin/env python3

"""
WakaTime Relay - Server that relays WakaTime requests to multiple instances.
Copyright (c) 2025 ImShyMike
(not affiliated with WakaTime)
"""

import asyncio
import base64
import json
import logging
import sys
import time
from hmac import compare_digest
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
import toml
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

CURRENT_VERSION = "0.1.1"

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

RELAY_SIGNATURE = f"waka-relay/{CURRENT_VERSION}"

USER_HOME = Path.home()
CURRENT_DIR = Path(__file__).parent

CONFIG = {}
CONFIG_PATHS = [
    Path(USER_HOME) / ".waka-relay.toml",
    Path(CURRENT_DIR).parent / ".waka-relay.toml",
]

REQUEST_SEMAPHORE = asyncio.Semaphore(25)

STATUS_MAP = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    302: "Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    429: "Too Many Requests",
    500: "Server Error",
}

CONFIG = {}

client = httpx.AsyncClient(
    timeout=CONFIG.get("timeout", 25),
    limits=httpx.Limits(
        max_keepalive_connections=20, max_connections=100, keepalive_expiry=60
    ),
)


def verify_key(authorization: str = Header()):
    """Verifies the API key from the request header. (if required)

    Args:
        authorization (str, optional): _description_. Defaults to Header().

    Raises:
        HTTPException: Configuration not loaded.
        HTTPException: API key is missing from the config.
        HTTPException: API key is required.
        HTTPException: Invalid API key format.
        HTTPException: Invalid API key.
    """
    if not CONFIG:
        logging.error("Configuration not loaded.")
        raise HTTPException(status_code=500, detail="Configuration not loaded.")

    if CONFIG.get("require_api_key", False):
        if not CONFIG.get("api_key"):
            logging.error("API key is missing from the config.")
            raise HTTPException(
                status_code=401, detail="API key is missing from the config."
            )

        if not authorization:
            logging.info("API key is required but not provided.")
            raise HTTPException(status_code=401, detail="API key is required.")

        if authorization.startswith("Basic "):
            api_key = base64.b64decode(authorization.split(" ")[1]).decode()
        elif authorization.startswith("Bearer "):
            api_key = authorization.split(" ")[1]
        else:
            logging.info("Invalid API key format.")
            raise HTTPException(status_code=401, detail="Invalid API key format.")

        if not compare_digest(api_key, CONFIG.get("api_key", "")):
            logging.info("Invalid API key.")
            raise HTTPException(status_code=401, detail="Invalid API key.")


@app.get("/")
async def root():
    """Root endpoint."""

    instances = CONFIG.get("instances", {})

    if error := no_instances_check(instances):  # fail if no instances are configured
        return error

    return RedirectResponse(list(instances.keys())[0], status_code=307)


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    dependencies=[Depends(verify_key)],
)
async def catch_everything(request: Request, full_path: str):
    """Catches all incoming requests and forwards them to wakatime instances."""

    start_time = time.perf_counter()

    if CONFIG.get("debug", False):
        with open("packets.log", "a", encoding="utf8") as f:
            f.write(
                f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} - {request.method} {request.url}\n"
            )
            if is_heartbeat(request):
                incoming_body = await request.body()
                try:
                    body_json = json.loads(incoming_body.decode("utf-8"))
                    json.dump(body_json, f, ensure_ascii=False, indent=4)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    f.write(f"Raw body: {str(incoming_body)}\n")

    instances = CONFIG.get("instances", {})

    if error := no_instances_check(instances):  # fail if no instances are configured
        return error

    instances_list = list(instances.items())
    primary_instance, secondary_instances = instances_list[0], instances_list[1:]

    primary_response = await handle_single_request(
        request=request,
        url=make_url(primary_instance[0], full_path),
        api_key=primary_instance[1],
    )  # only wait for the primary response

    if secondary_instances:
        for instance in secondary_instances:
            # use background tasks for secondary instances
            asyncio.create_task(
                handle_single_request(
                    request=request,
                    url=make_url(instance[0], full_path),
                    api_key=instance[1],
                    expected_status_code=primary_response["status_code"],
                )
            )

    if full_path in (
        "users/current/statusbar/today",
        "users/current/status_bar/today",
    ):  # add time suffix to time text
        grand_total = (
            primary_response.get("response", {}).get("data", {}).get("grand_total", {})
        )
        if grand_total.get("text"):
            primary_response["response"]["data"]["grand_total"]["text"] = CONFIG.get(
                "time_text", "%TEXT% (Relayed)"
            ).replace("%TEXT%", grand_total["text"])

    # fix for heartbeats.bulk endpoint to match the format expected by wakatime-cli
    if is_heartbeat(request) and isinstance(primary_response["response"], list):
        if isinstance(primary_response["response"], list):
            primary_response["response"] = {"responses": primary_response["response"]}

    logging.info(  # mimic gunicorn's log format (but with request time)
        '%s - %i ms - "%s %s HTTP/%s" %s %s',
        request.client.host,  # type: ignore # ip address
        (time.perf_counter() - start_time) * 1000,  # request time in ms
        request.method,  # request method
        request.url.path,  # request path
        request.scope.get("http_version", "1.1"),  # http version
        primary_response["status_code"],  # response status code
        STATUS_MAP.get(
            primary_response["status_code"], ""
        ),  # response status code as text
    )

    if CONFIG.get("debug", False):
        with open("packets.log", "a", encoding="utf8") as f:
            outgoing_body = primary_response["response"]
            f.write("\nOutgoing response:\n")
            json.dump(outgoing_body, f, ensure_ascii=False, indent=4)

    if CONFIG.get("debug", False):
        with open("packets.log", "a", encoding="utf8") as f:
            f.write(
                f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} - {request.method} {request.url}\n"
            )
            if is_heartbeat(request):
                try:
                    json.dump(
                        primary_response["response"], f, ensure_ascii=False, indent=4
                    )
                except (json.JSONDecodeError, UnicodeDecodeError):
                    f.write(f"Raw body: {str(primary_response['response'])}\n")

    # this line...
    # it made me have to read a bunch of source code from
    # wakatime-cli and the vscode extension to try to figure out
    # what was broken because even with the verbose option
    # it was failing silently and saying i was offline...
    # turns out it was logging the fail as "debug" and not "error"
    primary_response["headers"].pop("content-encoding", None)

    return JSONResponse(
        content=primary_response["response"],
        status_code=primary_response["status_code"],
        headers=primary_response["headers"],
        media_type=primary_response["content_type"],
    )


def no_instances_check(instances: Dict[str, str]) -> Optional[HTTPException]:
    """Check if there are instances configured. Otherwise, return an error.

    Args:
        instances (Dict[str, str]): Instances dictionary.

    Returns:
        HTTPException: No instances are configured.
    """
    if not instances:
        logging.error("No WakaTime instances configured.")
        return HTTPException(
            status_code=500, detail="No WakaTime instances configured."
        )

    return None


def is_heartbeat(request: Request) -> bool:
    """Check if a request is a heartbeat.

    Args:
        request (Request): Request object.

    Returns:
        bool: Is it a heartbeat?
    """
    url = str(request.url)
    return (
        request.headers.get("content-type", "").startswith("application/json")
        and request.method == "POST"
        and (
            url.endswith("/users/current/heartbeats")
            or url.endswith("/users/current/heartbeats.bulk")
        )
    )


def make_url(url: str, full_path: str) -> str:
    """Constructs the full URL for the request."""
    parsed_url = urlparse(url)

    if parsed_url.path.endswith("/"):
        return f"{url}{full_path}"

    return f"{url}/{full_path}"


async def handle_single_request(
    request: Request,
    url: str,
    api_key: str,
    expected_status_code: Optional[int] = None,
) -> Dict[str, Any]:
    """Handles a single request to a WakaTime instance."""

    async with REQUEST_SEMAPHORE:
        body = await request.body()

        headers = dict(request.headers)
        # i spent nearly 1 hour trying to figure out why auth was broken
        # just to then decide "hm, i should print incoming headers" and then
        # see that, no, the api key isnt sent as "Bearer (raw key)" but
        # as "Basic (base64 encoded key)" :whyyy:
        headers["authorization"] = (
            f"Basic {base64.b64encode(api_key.encode()).decode()}"
        )
        if RELAY_SIGNATURE not in headers.get("user-agent", ""):
            headers["user-agent"] = (
                headers.get("user-agent", "") + f" {RELAY_SIGNATURE}"
            )

        if is_heartbeat(request):
            try:
                json_body = await request.json()
                # patch the user agent in each heartbeat
                for i, item in enumerate(json_body):
                    if isinstance(item, dict) and RELAY_SIGNATURE not in item.get(
                        "user_agent", ""
                    ):
                        json_body[i]["user_agent"] += f" {RELAY_SIGNATURE}"
                body = json.dumps(json_body).encode("utf-8")

            except json.JSONDecodeError:
                logging.error("Failed to decode JSON body.")

            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.critical("An unexpected error occurred: %s", e)

        headers.pop("host", None)
        headers.pop("content-length", None)

        response = None
        for retry in range(CONFIG.get("retries", 3)):
            if retry > 0:
                logging.warning("Retrying request to %s (attempt %d)", url, retry + 1)

            try:
                response = await client.request(
                    method=request.method, url=url, content=body, headers=headers
                )
                if CONFIG.get("debug", False):
                    with open("packets.log", "a", encoding="utf8") as f:
                        f.write(
                            f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} - {request.method} {url}\n"
                        )
                        if is_heartbeat(request):
                            try:
                                body_json = json.loads(body.decode("utf-8"))
                                json.dump(body_json, f, ensure_ascii=False, indent=4)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                f.write(f"Raw body: {str(body)}\n")
                break  # dont retry if the request was successful

            except httpx.RequestError as e:
                logging.error("Request to %s failed: %s", url, e)

                if retry == (CONFIG.get("retries", 2) - 1):
                    logging.error("Max retries reached. Request failed...")

        if response is None:
            logging.error("No response received from %s", url)
            return {
                "status_code": 500,
                "response": {"error": "No response received"},
                "headers": {},
                "content_type": "",
            }

        response_headers = dict(response.headers)
        response_headers.pop("content-length", None)

        if expected_status_code and is_success(expected_status_code) != is_success(
            response.status_code
        ):
            logging.error(
                "Received unexpected status code %s from %s (expected %s)",
                response.status_code,
                url,
                expected_status_code,
            )

        request_response = (
            response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text
        )

        return {
            "status_code": response.status_code,
            "response": request_response,
            "headers": response_headers,
            "content_type": response.headers.get("content-type", ""),
        }


def get_existing_config_path() -> Path:
    """Get the an existing config path.

    Returns:
        Path: The first existing config path.
    """
    for path in CONFIG_PATHS:
        if path.exists():
            return path

    return CONFIG_PATHS[0]  # fallback to the first path


def is_success(status_code: int) -> bool:
    """Check if the status code indicates success.

    Args:
        status_code (int): Status code to check.

    Returns:
        bool: Is it a success?
    """
    return 200 <= status_code < 300


def load_config(is_retry: bool = False) -> Dict:
    """Loads the config file from the user's home directory.

    Args:
        is_retry (bool, optional): Set if the read is a retry. Defaults to False.
    """
    try:
        config = toml.load(get_existing_config_path())

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
                "time_text": "%TEXT% (Relayed)",
                "require_api_key": False,
                "api_key": "",
                "debug": False,
                "instances": {"https://api.wakatime.com/api/v1": "API KEY HERE"},
            }
        }

        with open(get_existing_config_path(), "w", encoding="utf8") as f:
            toml.dump(config, f)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.critical("An error occurred while creating the default config: %s", e)
        sys.exit(1)


CONFIG = load_config()


def main():
    """Main function to run the server."""
    if CONFIG.get("debug", False):
        httpx_logger = logging.getLogger("httpx")
        httpx_logger.setLevel(logging.WARNING)  # disable httpx logs on every request

        logging.info("Config file loaded successfully.")
        logging.info("Config file path: %s", get_existing_config_path())
        logging.info("Config file content: %s", CONFIG)

    uvicorn.run(
        "main:app",
        host=CONFIG.get("host", "0.0.0.0"),
        port=CONFIG.get("port", 25892),
        log_level="info",
        workers=CONFIG.get("workers", None),
    )


if __name__ == "__main__":
    main()
