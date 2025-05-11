
<div align="center">

  <img src="https://raw.githubusercontent.com/ImShyMike/waka-relay/refs/heads/main/assets/waka-relay.png" alt="waka‑relay logo" width="256" />

  <span style="font-size: 1.3rem;">A self-hosted app that relays WakaTime heartbeats to multiple instances</span>

  <p>
    <img src="https://img.shields.io/github/license/ImShyMike/waka-relay.svg?style=for-the-badge&" alt="License" />
    <img src="https://img.shields.io/github/repo-size/imshymike/waka-relay.svg?style=for-the-badge" alt="Code Size" />
    <img src="https://img.shields.io/github/issues/ImShyMike/waka-relay.svg?style=for-the-badge" alt="Issues" />
    <img src="https://img.shields.io/github/stars/ImShyMike/waka-relay.svg?style=for-the-badge" alt="Stars" />
  </p>

  <h3>
    <a href="#installation">Installation</a>
    <span> | </span>
    <a href="#how-it-works">How it works</a>
    <span> | </span>
    <a href="https://github.com/ImShyMike/waka-relay/issues">Issues</a>
    <span> | </span>
    <a href="https://pypi.org/project/waka-relay">PyPI Package</a>
  </h3>
  
</div>

## Features

* ✅ Multi-instance support
* ✅ Self-hosted
* ✅ Key authentication
* ✅ Highly configurable
* ✅ Fully relays WakaTime requests

## Table of contents

* [Installation](#installation)
  * [Quick run](#quick-run)
  * [Python](#python)
  * [Using docker](#using-docker)
* [Example config](#example-config)
* [Configuration options](#configuration-options)
* [Known compatible backends](#known-compatible-backends)
* [Issues](#issues)

## Installation

### Quick run

Python (>=3.8) is required for this installation type, please install it before continuing.

```bash
# Install the package
$ pip install waka-relay

# Then run the app
$ wakarelay
```

### Python

Python (>=3.8) is required for this installation type, please install it before continuing.

```bash
# Clone the repository
$ git clone https://github.com/ImShyMike/waka-relay.git

# Move into the project's folder
$ cd waka-relay

# Install the dependencies
$ pip install -r requirements.txt

# Then run the app using python 
$ python relay/main.py

# Or use uvicorn directly (WARNING: this will ignore the host, port, and worker configuration)
$ uvicorn relay.main:app
```

### Using docker

```bash
# Clone the repository
$ git clone https://github.com/ImShyMike/waka-relay.git

# Move into the project's folder
$ cd waka-relay

# First start by building the docker image
$ docker build -t waka-relay .

# Then run the container
$ docker run -d \
  -p 25892:25892 \
  -v ~/.waka-relay.toml:/root/.waka-relay.toml \
  --name waka-relay \
  waka-relay
```

## How it works

![waka-relay graph](https://raw.githubusercontent.com/ImShyMike/waka-relay/refs/heads/main/assets/graph.png)

A "WakaTime instance" does not need to be the real WakaTime server but it can also be anything that implements the same protocol. ([compatible instance backends](#known-compatible-backends))

## Example config

The configuration file must be located either in `~/.waka-relay.toml` or `./.waka-relay.toml` (first config file found is used)

```toml
[relay]
workers = 2
timeout = 10
require_api_key = true
api_key = "39949664-5a5f-4c7d-95b2-44a864f67b6a"
debug = false

[relay.instances]
"https://api.wakatime.com/api/v1" = "WAKATIME API KEY"
```

For a full config example with an explanation check out the [example config file](.waka-relay.toml).

## Configuration options

| TOML key | Default value | Description |
|----------|---------------|-------------|
|`host`|`"0.0.0.0"`|Host for the webserver to listen on|
|`port`|`25892`|Port for the webserver to run on|
|`workers`|`4`|Worker count for the webserver|
|`timeout`|`25`|Timeout value for the relayed requests (in seconds)|
|`retries`|`3`|Number of retries for failed requests|
|`time_text`|`"%TEXT% (Relayed)"`|Text to display in the IDE (%TEXT% is replaced by what the api retuns)|
|`require_api_key`|`""`|Whether or not to require an API key|
|`api_key`|`""`|The API key to use if `require_api_key` is true|
|`debug`|`false`|Whether or not to enable debug logging|

## Known compatible backends

This relay is compatible with the following backend servers:

* [WakaTime](https://github.com/wakatime)
* [Wakapi](https://github.com/muety/wakapi)
* [Hackatime](https://github.com/hackclub/hackatime)
* [Hackatime (old)](https://github.com/hackclub/archived-hacktime)

<sub>(all of the above servers were tested using the vscode extension)</sub>

## Issues

Please feel free to [open an issue](https://github.com/ImShyMike/waka-relay/issues/new) on the github if you come across a bug or crash as this project has not been fully tested and may have some bugs.
