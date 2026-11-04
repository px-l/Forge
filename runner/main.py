import base64, json, os, asyncio
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Literal
from playwright.async_api import async_playwright, expect

app = FastAPI(title="Isolated browser runner")


class Step(BaseModel):
    action: Literal["fill", "click", "expect_text", "reload", "expect_text_exact", "expect_disabled", "expect_enabled", "try_click", "press", "seed_storage", "expect_storage"]
    selector: str = Field(default="", max_length=300)
    value: str = Field(default="", max_length=12000)


class Viewport(BaseModel):
    width: int = Field(default=1440, ge=64, le=2560)
    height: int = Field(default=900, ge=64, le=2560)


class Input(BaseModel):
    html: str = Field(max_length=400000)
    viewport: Viewport = Field(default_factory=Viewport)
    design_spec: dict | None = None
    route: str | None = Field(default=None, pattern=r"^/(?:[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*)?$", max_length=100)
    state: str = Field(default="initial", max_length=80)
    tests: list[Step] = Field(default_factory=list, max_length=20)


@app.post("/validate")
async def validate(body: Input):
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage"],
            executable_path=os.getenv("CHROMIUM_EXECUTABLE_PATH") or None,
        )
        try:
            context = await browser.new_context(
                viewport=body.viewport.model_dump(), service_workers="block"
            )
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            await page.add_init_script(
                "window.__FORGE_CAPTURE__=new URLSearchParams(location.search).get('forge_capture')==='1';window.alert=()=>{};window.confirm=()=>false;window.prompt=()=>null;"
            )
            page.on("pageerror", lambda e: errors.append(str(e)[:400]))
            # Same-origin inert route supports localStorage; all other networking is denied.
            await context.unroute("**/*")

            async def route(r):
                if r.request.url.split("#",1)[0].split("?",1)[0] == "http://preview.invalid/":
                    await r.fulfill(
                        body=body.html,
                        content_type="text/html; charset=utf-8",
                        headers={
                            "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; frame-src 'none'"
                        },
                    )
                else:
                    await r.abort()

            await context.route("**/*", route)
            fragment = "#" + body.route if body.route else ""
            query = "?forge_capture=1" if body.state == "initial" and body.route in (None, "/") else ""
            await page.goto("http://preview.invalid/" + query + fragment, wait_until="load", timeout=15000)
            await page.wait_for_timeout(350)
            checks = await page.evaluate(
                """()=>({has_content:document.body.innerText.trim().length>5,horizontal_overflow:document.documentElement.scrollWidth>innerWidth+2,controls:document.querySelectorAll('button,input,select,textarea').length})"""
            )
            route_ok = not body.route or (await page.locator('[data-forge-route]:visible').count() == 1 and await page.locator(f'[data-forge-route="{body.route}"]:visible').count() == 1)
            layout = {"passed":True,"issues":[]}
            if body.design_spec:
                layout=await page.evaluate("""spec=>{
                  const issues=[],all=[...document.querySelectorAll('[data-forge-section]')].filter(n=>n.getClientRects().length);let last=-1;
                  for(const section of spec.sections||[]){
                    const nodes=all.filter(n=>n.dataset.forgeSection===section.id);
                    if(nodes.length!==1){issues.push({area:section.id,issue:'模块缺失或重复',expected:1,actual:nodes.length});continue;}
                    const node=nodes[0],index=all.indexOf(node);
                    if(index<last)issues.push({area:section.id,issue:'模块顺序与规格不一致'});last=index;
                    const expected=section.id==='hero'?(spec.hero_layout==='two-columns'?2:1):section.columns;
                    if(expected>1&&innerWidth>spec.stack_below){
                      const children=[...node.children].filter(x=>getComputedStyle(x).display!=='none'&&x.getBoundingClientRect().width>0);
                      const positions=new Set(children.map(x=>Math.round(x.getBoundingClientRect().left)));
                      if(positions.size!==expected)issues.push({area:section.id,issue:'桌面列数不一致',expected,actual:positions.size});
                    }
                  }
                  for (const section of spec.sections || []) {
                    const root = all.find(node => node.dataset.forgeSection === section.id);
                    if (!root) continue;
                    for (const element of section.elements || []) {
                      if (!element.visible_on_load) continue;
                      const found = [root, ...root.querySelectorAll('[data-forge-element],[id]')].some(node =>
                        (node.dataset.forgeElement === element.id || node.id === element.id) && node.getClientRects().length &&
                        getComputedStyle(node).visibility === 'visible');
                      if (!found) issues.push({area:element.id,issue:'关键元素首屏不可见'});
                    }
                  }
                  if(!document.querySelector('[data-forge-title]'))issues.push({area:'title',issue:'缺少主标题标记'});
                  return {passed:issues.length===0,issues};
                }""",body.design_spec)
            shot = await page.screenshot(type="png", timeout=10000)
            # Screenshot uses fixed capture state; interactions run in normal application mode.
            if query:
                await page.goto("http://preview.invalid/" + fragment, wait_until="load", timeout=15000)
            interactions = []
            for step in body.tests:
                try:
                    if step.action == "fill":
                        await page.locator(step.selector).fill(step.value, timeout=2500)
                    elif step.action == "click":
                        await page.locator(step.selector).click(timeout=2500)
                    elif step.action == "expect_text":
                        if step.selector:
                            await expect(page.locator(step.selector)).to_contain_text(step.value,timeout=2500)
                        else:
                            await page.get_by_text(step.value, exact=False).first.wait_for(state="visible", timeout=2500)
                    elif step.action == "expect_text_exact":
                        await expect(page.locator(step.selector)).to_have_text(step.value, timeout=2500)
                    elif step.action == "expect_disabled":
                        await expect(page.locator(step.selector)).to_be_disabled(timeout=2500)
                    elif step.action == "expect_enabled":
                        await expect(page.locator(step.selector)).to_be_enabled(timeout=2500)
                    elif step.action == "try_click":
                        locator = page.locator(step.selector)
                        if await locator.is_enabled():
                            await locator.click(timeout=2500)
                    elif step.action == "press":
                        await page.locator(step.selector).press(step.value, timeout=2500)
                    elif step.action == "seed_storage":
                        await page.evaluate("([key,value])=>localStorage.setItem(key,value)", [step.selector,step.value])
                    elif step.action == "expect_storage":
                        raw = await page.evaluate("key=>localStorage.getItem(key)", step.selector)
                        try:
                            expected = json.loads(step.value)
                        except json.JSONDecodeError:
                            expected = step.value
                        try:
                            actual = json.loads(raw) if raw is not None else None
                        except json.JSONDecodeError:
                            actual = raw
                        if isinstance(expected, dict):
                            matches = isinstance(actual, dict) and all(k in actual and actual[k] == v for k, v in expected.items())
                        else:
                            matches = actual == expected or raw == step.value
                        if not matches:
                            raise ValueError("存档与预期状态不一致")
                    elif step.action == "reload":
                        await page.reload(wait_until="load", timeout=5000)
                    interactions.append({"action": step.action, "passed": True})
                except Exception as e:
                    interactions.append(
                        {"action": step.action, "passed": False, "error": str(e)[:500]}
                    )
                    break
            if body.state != "initial":
                shot = await page.screenshot(type="png", timeout=10000)
            checks["route_visible"] = bool(route_ok)
            return {
                "passed": route_ok and checks["has_content"]
                and not checks["horizontal_overflow"]
                and not errors
                and layout["passed"]
                and all(x["passed"] for x in interactions),
                "interactions": interactions,
                "layout":layout,
                "checks": checks,
                "viewport": body.viewport.model_dump(),
                "errors": errors,
                "screenshot": "data:image/png;base64,"
                + base64.b64encode(shot).decode(),
            }
        finally:
            await browser.close()
