import asyncio
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import jinja2

from astrbot.api import logger


class DeltaRenderer:
    def __init__(self, res_path: str, render_timeout: int = 30000):
        self.res_path = Path(res_path).resolve()
        self.render_timeout = int(render_timeout or 30000)
        self.output_dir = self.res_path.parent / "render_cache"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._env = jinja2.Environment(
            autoescape=True,
            keep_trailing_newline=True,
            undefined=jinja2.ChainableUndefined,
        )
        self._env.globals["fmt"] = self._fmt
        self._env.globals["len"] = len
        self._env.filters["fmt"] = self._fmt
        self._start_cleanup()

    def _start_cleanup(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(60)
                import time

                now = time.time()
                for item in self.output_dir.iterdir():
                    if item.name.startswith(("render_", "tmp_")) and now - item.stat().st_mtime > 600:
                        try:
                            item.unlink()
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @staticmethod
    def _fmt(value: Any) -> str:
        try:
            if value is None or value == "":
                return "0"
            if isinstance(value, str):
                num = float(value)
                if not value.strip().replace(".", "", 1).replace("-", "", 1).isdigit():
                    return value
            else:
                num = float(value)
            if num.is_integer():
                return f"{int(num):,}"
            return f"{num:,.2f}"
        except Exception:
            return str(value)

    def _template_path(self, name: str) -> Path:
        clean = name.replace("\\", "/")
        if not clean.endswith(".html"):
            clean += ".html"
        return self.res_path / clean

    def _read(self, name: str) -> str:
        path = self._template_path(name)
        if not path.exists():
            logger.error(f"[DeltaForce Render] 模板不存在: {path}")
            return ""
        return path.read_text("utf-8", errors="replace")

    def _layout_for(self, layout: str) -> str:
        layout = layout.strip()
        if layout == "commonLayout":
            return "Template/common/common.html"
        if layout == "defaultLayout":
            return "common/layout/default.html"
        if layout == "elemLayout":
            return "common/layout/elem.html"
        return layout

    def _apply_layout(self, content: str) -> str:
        extend = re.search(r"\{\{\s*extend\s+([A-Za-z0-9_./\\-]+)\s*\}\}", content)
        if not extend:
            return content

        layout_name = self._layout_for(extend.group(1))
        layout = self._read(layout_name)
        if not layout:
            return re.sub(r"\{\{\s*extend\s+.+?\}\}", "", content, count=1)

        blocks: Dict[str, str] = {}
        for match in re.finditer(
            r"\{\{\s*block\s+['\"]([^'\"]+)['\"]\s*\}\}(.*?)\{\{\s*/block\s*\}\}",
            content,
            flags=re.S,
        ):
            blocks[match.group(1)] = match.group(2)

        def replace_block(match):
            name = match.group(1)
            default = match.group(2)
            return blocks.get(name, default)

        return re.sub(
            r"\{\{\s*block\s+['\"]([^'\"]+)['\"]\s*\}\}(.*?)\{\{\s*/block\s*\}\}",
            replace_block,
            layout,
            flags=re.S,
        )

    def _expr(self, expr: str) -> str:
        expr = (expr or "").strip()
        expr = expr.replace("`", "'")
        expr = expr.replace("===", "==").replace("!==", "!=")
        expr = expr.replace("&&", " and ").replace("||", " or ")
        expr = re.sub(r"\btrue\b", "True", expr, flags=re.I)
        expr = re.sub(r"\bfalse\b", "False", expr, flags=re.I)
        expr = re.sub(r"\bnull\b", "None", expr, flags=re.I)
        expr = expr.replace("?.", ".")
        expr = expr.replace("$index", "loop.index0").replace("$last", "loop.last")
        expr = re.sub(r"!\s*(?!=)", "not ", expr)
        expr = re.sub(r"([\w.]+)\.length\b", r"\1|length", expr)
        expr = re.sub(r"([\w.]+)\.trim\(\)", r"\1|trim", expr)
        expr = re.sub(r"([\w.]+)\.toLocaleString\(\)", r"fmt(\1)", expr)
        expr = re.sub(r"([\w.]+)\.startsWith\(", r"\1.startswith(", expr)
        expr = re.sub(r"([\w.]+)\.includes\(", r"\1.__contains__(", expr)
        return expr

    def _adapt(self, content: str) -> str:
        content = self._apply_layout(content)
        content = re.sub(r"<%.*?%>", "", content, flags=re.S)

        content = re.sub(
            r"\{\{\s*set\s+(.+?)\s*=\s*(.+?)\s*\}\}",
            lambda m: "{% set " + m.group(1).strip() + " = " + self._expr(m.group(2)) + " %}",
            content,
        )
        content = re.sub(
            r"\{\{\s*if\s+(.+?)\s*\}\}",
            lambda m: "{% if " + self._expr(m.group(1)) + " %}",
            content,
        )
        content = re.sub(
            r"\{\{\s*else if\s+(.+?)\s*\}\}",
            lambda m: "{% elif " + self._expr(m.group(1)) + " %}",
            content,
        )
        content = re.sub(r"\{\{\s*else\s*\}\}", "{% else %}", content)
        content = re.sub(r"\{\{\s*/if\s*\}\}", "{% endif %}", content)

        def each_repl(match):
            parts = match.group(1).strip().split()
            if len(parts) >= 3:
                return f"{{% for {parts[2]}, {parts[1]} in {self._expr(parts[0])}|enumerate %}}"
            if len(parts) >= 2:
                return f"{{% for {parts[1]} in {self._expr(parts[0])} %}}"
            return f"{{% for item in {self._expr(parts[0])} %}}"

        self._env.filters["enumerate"] = enumerate
        content = re.sub(r"\{\{\s*each\s+(.+?)\s*\}\}", each_repl, content)
        content = re.sub(r"\{\{\s*/each\s*\}\}", "{% endfor %}", content)

        content = re.sub(
            r"\{\{@\s*(.+?)\s*\}\}",
            lambda m: "{{ " + self._expr(m.group(1)) + "|safe }}",
            content,
        )
        content = re.sub(
            r"\{\{\s*([^{}]+?)\s*\}\}",
            lambda m: "{{ " + self._expr(m.group(1)) + " }}",
            content,
        )
        return content

    async def render_html(
        self,
        template_name: str,
        data: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        source = self._read(template_name)
        if not source:
            return None
        data = dict(data or {})
        data.setdefault("_res_path", self.res_path.as_uri() + "/")
        data.setdefault("pluResPath", self.res_path.as_uri() + "/")
        data.setdefault("commonLayout", "Template/common/common.html")
        data.setdefault("defaultLayout", "common/layout/default.html")
        data.setdefault("elemLayout", "common/layout/elem.html")
        data.setdefault("sys", {"scale": "", "copyright": "AstrBot DeltaForce Plugin"})

        try:
            template = self._env.from_string(self._adapt(source))
            html = template.render(**data)
        except Exception as exc:
            logger.error(f"[DeltaForce Render] 模板渲染失败 {template_name}: {exc}")
            return None

        return await self._screenshot(html, template_name, options or {})

    async def _ensure_browser(self):
        from playwright.async_api import async_playwright

        async with self._lock:
            try:
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                if self._browser is None or not self._browser.is_connected():
                    self._browser = await self._playwright.chromium.launch()
            except Exception:
                try:
                    if self._browser:
                        await self._browser.close()
                except Exception:
                    pass
                try:
                    if self._playwright:
                        await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch()

    async def _screenshot(self, html: str, template_name: str, options: Dict[str, Any]) -> Optional[str]:
        await self._ensure_browser()
        output_path = self.output_dir / f"render_{uuid.uuid4().hex[:8]}.png"
        temp_path = self.output_dir / f"tmp_{uuid.uuid4().hex[:8]}.html"
        temp_path.write_text(html, "utf-8")

        context = None
        page = None
        try:
            width = int(options.get("viewport_width") or options.get("width") or 1400)
            height = int(options.get("viewport_height") or options.get("height") or 1200)
            scale = float(options.get("device_scale_factor") or options.get("scale") or 1.0)
            context = await self._browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
            )
            page = await context.new_page()
            await page.goto(temp_path.as_uri(), wait_until="networkidle", timeout=self.render_timeout)
            await page.evaluate(
                """
                Promise.all(Array.from(document.images).map(img => {
                    if (img.complete) return Promise.resolve();
                    return new Promise(resolve => {
                        img.onload = resolve;
                        img.onerror = resolve;
                    });
                }))
                """
            )
            await page.wait_for_timeout(int(options.get("settle_ms", 300)))
            selector = options.get("selector") or self._selector_for(template_name)
            el = await page.query_selector(selector) if selector else None
            if el:
                box = await el.bounding_box()
                if box:
                    await page.set_viewport_size(
                        {"width": max(240, int(box["width"]) + 12), "height": max(240, int(box["height"]) + 12)}
                    )
                    await page.wait_for_timeout(100)
                    await el.screenshot(path=str(output_path), type="png")
                else:
                    await page.screenshot(path=str(output_path), full_page=True, type="png")
            else:
                await page.screenshot(path=str(output_path), full_page=True, type="png")
            return str(output_path) if output_path.exists() else None
        except Exception as exc:
            logger.error(f"[DeltaForce Render] Playwright 截图失败 {template_name}: {exc}")
            return None
        finally:
            try:
                if page:
                    await page.close()
            except Exception:
                pass
            try:
                if context:
                    await context.close()
            except Exception:
                pass
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

    @staticmethod
    def _selector_for(template_name: str) -> str:
        name = template_name.replace("\\", "/").lower()
        if "/help/" in name or name.startswith("help/"):
            return "#container, .container, body"
        selectors = [
            ".container",
            ".red-collection-container",
            ".red-record-list-container",
            ".red-record-container",
            ".collection-container",
            ".music-list-container",
            ".place-info-container",
            "body > div",
        ]
        return ", ".join(selectors)

    async def close(self):
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
