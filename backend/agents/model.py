import os, json, asyncio
import httpx
from ..store import event


class ModelError(Exception):
    pass


DEFAULT_CODE_MODEL = "deepseek-flash"


def code_model():
    return os.getenv("CODE_MODEL") or DEFAULT_CODE_MODEL


async def ask(task_id, system, prompt, *, images=None, vision=False, coding=False):
    if coding:
        key_name = "DEEPSEEK_API_KEY"
        base = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        endpoint = base + "/chat/completions"
        model = code_model()
        if images and model != "deepseek-flash":
            raise ModelError("带设计图的代码生成请设置 CODE_MODEL=deepseek-flash，该模型支持图片输入。")
    else:
        key_name = "DASHSCOPE_API_KEY"
        base = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/")
        endpoint = base + "/compatible-mode/v1/chat/completions"
        model = os.getenv("VISION_MODEL" if vision else "TEXT_MODEL", "qwen3.7-plus")
    key = os.getenv(key_name)
    if not key:
        raise ModelError(f"未配置 {key_name}。请配置服务端密钥，或新建「演示模式」任务体验流程。")
    content = [{"type": "text", "text": prompt}]
    for image in images or []:
        content.append({"type": "image_url", "image_url": {"url": image}})
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 14000,
    }
    if coding:
        payload["thinking"] = {"type": "disabled"}
    else:
        payload["enable_thinking"] = False
    async with httpx.AsyncClient(timeout=180) as client:
        for attempt in range(3):
            try:
                r = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
                if r.status_code in (429, 502, 503, 504):
                    if attempt < 2:
                        event(
                            task_id,
                            type="retry",
                            attempt=attempt + 1,
                            summary="模型临时繁忙，等待后重试",
                        )
                        await asyncio.sleep(2**attempt)
                        continue
                if r.is_error:
                    raise ModelError(
                        f"模型接口返回 {r.status_code}，请检查模型权限、地域和额度。"
                    )
                raw = r.json()["choices"][0]["message"]["content"]
                return json.loads(
                    raw.removeprefix("```json").removesuffix("```").strip()
                )
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt == 2:
                    raise ModelError("模型接口连接失败或超时，已达到重试上限。")
                await asyncio.sleep(2**attempt)
            except (KeyError, json.JSONDecodeError) as e:
                raise ModelError("模型返回格式不合法；可携带当前任务重试。") from e


async def image(task_id, prompt):
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise ModelError("尚未配置百炼密钥")
    import base64

    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(
            os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip(
                "/"
            )
            + "/api/v1/services/aigc/multimodal-generation/generation",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv("IMAGE_MODEL", "qwen-image-3.0"),
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": "网页应用首页高保真效果图，正面截图，无设备边框。只使用指定设计规格中的布局、字号、颜色、文案和模块，不新增功能。简洁可实现的SVG/CSS风格，不用复杂插画、Emoji、照片、3D或纹理。首屏完整展示、游戏未开始且分数为0。清晰中文文字、可实现布局。"
                                    + prompt[:4000]
                                }
                            ],
                        }
                    ]
                },
                "parameters": {"size": "1664*928", "n": 1, "watermark": False},
            },
        )
        if r.is_error:
            raise ModelError(f"效果图生成失败（{r.status_code}），请检查图像模型权限。")
        try:
            url = next(
                x["image"]
                for x in r.json()["output"]["choices"][0]["message"]["content"]
                if "image" in x
            )
        except (KeyError, StopIteration):
            raise ModelError("图像模型未返回图片")
        img = await c.get(url)
        img.raise_for_status()
        if len(img.content) > 5_000_000:
            raise ModelError("图片超出大小限制")
        return "data:image/png;base64," + base64.b64encode(img.content).decode()
