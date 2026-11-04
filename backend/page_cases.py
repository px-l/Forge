"""Bounded routes and test cases for hash-routed apps."""
from pydantic import BaseModel, Field


class Route(BaseModel):
    path: str = Field(pattern=r"^/(?:[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*)?$", max_length=100)
    label: str = Field(default="", max_length=80)


class PageCase(BaseModel):
    path: str = Field(pattern=r"^/(?:[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*)?$", max_length=100)
    state: str = Field(default="initial", min_length=1, max_length=80)
    tests: list[dict] = Field(default_factory=list, max_length=20)


def routes(values):
    if not isinstance(values, list) or len(values) > 8:
        raise ValueError("页面清单最多支持八个路由")
    result = [Route.model_validate(value).model_dump() for value in values]
    paths = [value["path"] for value in result]
    if len(paths) != len(set(paths)) or (paths and "/" not in paths):
        raise ValueError("页面路由必须唯一并包含首页 /")
    return result


def cases(values, declared, tests):
    if not isinstance(values, list) or len(values) > 12:
        raise ValueError("最多支持十二个页面状态用例")
    result = [PageCase.model_validate(value).model_dump() for value in values]
    paths = {item["path"] for item in declared} or {"/"}
    keys = {(item["path"], item["state"]) for item in result}
    if len(keys) != len(result) or any(path not in paths for path, _ in keys):
        raise ValueError("页面用例路由未声明或状态重复")
    missing = [
        {"path": route["path"], "state": "initial", "tests": tests if route["path"] == "/" else []}
        for route in declared if (route["path"], "initial") not in keys
    ]
    if len(missing) + len(result) > 12:
        raise ValueError("页面初始状态及交互状态合计最多十二个用例")
    return missing + result
