import json
import logging
import re
import shlex
import subprocess
from typing import Any, List, Optional, Union

import requests
import toml
from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel


class Config:
    def __init__(self, path: str):
        self.conf = toml.load(open(path))

    def get(self, section: str, prop: str, required: bool = True, default_value=None):
        val = self.conf.get(section, {}).get(prop, None)
        if val is None:
            if required:
                raise Exception(f"Not found {section}.{prop} in config.")
            else:
                return default_value
        return val


config = Config("conf.toml")
app = FastAPI()
logger = logging.getLogger("uvicorn.server")
logger.info("Config: %s", config)


class Challenge(BaseModel):
    token: str
    type: str
    challenge: str


class Event(BaseModel):
    client_msg_id: str
    type: str
    text: str
    user: str
    ts: str
    team: str
    blocks: List[Any]
    channel: str
    event_ts: str


class EventBox(BaseModel):
    token: str
    team_id: str
    api_app_id: str
    event: Event
    type: str
    event_id: str
    event_time: int
    authorizations: Any
    is_ext_shared_channel: bool
    event_context: str


@app.post("/")
async def main(item: Union[Challenge, EventBox, Any], background: BackgroundTasks):

    if isinstance(item, Challenge):
        logger.info("Challenge Mode: %s", item)
        return item.challenge

    elif isinstance(item, EventBox):
        logger.info("Event: %s", item)
        background.add_task(write, item)
        return {}

    else:
        logger.info("Unknown Data: %s", item)
        return {}


class History:

    items = []
    items_set = set()
    hist_size = 100

    @classmethod
    def contains(cls, item):
        return item in cls.items_set

    @classmethod
    def add(cls, item):
        cls.items.append(item)
        cls.items_set.add(item)
        if len(cls.items) > cls.hist_size:
            remove_item = cls.items[0]
            cls.items_set.remove(remove_item)
            cls.items = cls.items[1:]


def write(item: EventBox):
    """Process User's Mentions"""

    if History.contains(item.event_id):
        logger.info("Event %s is already written", item.event_id)
        return

    result = execute(parse(item.event.text))
    post(result)

    History.add(item.event_id)
    logger.info("Event %s has been written successfully", item.event_id)


def parse(text: str):
    """Trim and Split into shell command"""

    text = re.sub(r"^<@[^>]*>", "", text)
    text = re.sub("　", " ", text)
    text = text.strip()
    commands = shlex.split(text)
    return commands


class Result:
    def __init__(self, is_success: bool, is_failed: bool, data: Any):
        self.is_success = is_success
        self.is_failed = is_failed
        self.data = data

    @classmethod
    def success(self, data):
        return Result(is_success=True, is_failed=False, data=data)

    @classmethod
    def failed(self, data):
        return Result(is_success=False, is_failed=True, data=data)

    def __repr__(self):
        if self.is_success:
            return f"Success({self.data})"
        else:
            return f"Failed({self.data})"


def execute(command: List[str]) -> Result:
    """Execute shell command and Returns stdout"""
    logger.info("Execute: %s", command)

    assert len(command) > 0

    allows = config.get('command','allows')
    if command[0] not in allows:
        return Result.failed(f"Error: {command[0]} is not allowed")

    try:
        proc = subprocess.run(command, capture_output=True)
        return Result.success(proc.stdout.decode())
    except Exception:
        return Result.failed("Error: Something wrong?")


def post(result: Result):
    """Post to Slack via incoming-webhook"""
    logger.info("Result: %s", result)

    url = config.get("slack", "webhook")
    channel = config.get("slack", "channel")
    if not channel.startswith("#"):
        channel = "#" + channel

    color = "#202020" if result.is_success else "#f02020"

    data = {
        "username": config.get("slack", "username"),
        "channel": channel,
        "color": color,
        "fields": [{"title": "", "value": result.data, "short": False}],
    }

    icon = config.get("slack", "icon", required=False)
    if icon is None:
        pass
    elif icon.startswith(":"):
        data["icon_emoji"] = icon
    elif icon.startswith("http"):
        data["icon_url"] = icon

    requests.post(url, json=data)
