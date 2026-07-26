import asyncio
import urllib.parse
from playwright.async_api import Page
from app.models import TestStep, TestCase

# Registry Dictionary untuk menyimpan pasangan "NAMA_COMMAND": fungsi_handler
COMMAND_REGISTRY = {}

def register(code: str):
    """Decorator untuk mendaftarkan fungsi perintah ke registry secara otomatis"""
    def decorator(func):
        COMMAND_REGISTRY[code.upper()] = func
        return func
    return decorator

# ===================================================
# DAFTAR HANDLER PERINTAH PLAYWRIGHT (MODULAR)
# ===================================================

@register("GOTO_URL")
async def handle_goto(page: Page, step: TestStep, test_case: TestCase):
    val = step.input_value
    if not val:
        url = test_case.base_url
    elif val.startswith(("http://", "https://")):
        url = val
    else:
        url = urllib.parse.urljoin(test_case.base_url, val)
    await page.goto(url)

@register("CLICK")
async def handle_click(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    await page.click(step.target_selector)

@register("DOUBLE_CLICK")
async def handle_double_click(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    await page.dblclick(step.target_selector)

@register("RIGHT_CLICK")
async def handle_right_click(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    await page.click(step.target_selector, button="right")

@register("TYPE_TEXT")
async def handle_type(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    await page.fill(step.target_selector, step.input_value or "")

@register("PRESS_KEY")
async def handle_press_key(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    await page.press(step.target_selector, step.input_value or "Enter")

@register("HOVER")
async def handle_hover(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    await page.hover(step.target_selector)

@register("SELECT_OPTION")
async def handle_select(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    await page.select_option(step.target_selector, label=step.input_value)

@register("SCROLL_RIGHT")
async def handle_scroll_right(page: Page, step: TestStep, test_case: TestCase):
    val = step.input_value
    target = step.target_selector
    px = int(val) if val and val.replace("-", "").isdigit() else 300
    if target:
        await page.wait_for_selector(target, timeout=5000)
        await page.locator(target).evaluate("(el, x) => el.scrollBy(x, 0)", px)
    else:
        await page.evaluate("(x) => window.scrollBy(x, 0)", px)

@register("SCROLL_DOWN")
async def handle_scroll_down(page: Page, step: TestStep, test_case: TestCase):
    val = step.input_value
    target = step.target_selector
    px = int(val) if val and val.replace("-", "").isdigit() else 300
    if target:
        await page.wait_for_selector(target, timeout=5000)
        await page.locator(target).evaluate("(el, y) => el.scrollBy(0, y)", px)
    else:
        await page.evaluate("(y) => window.scrollBy(0, y)", px)

@register("WAIT")
async def handle_wait(page: Page, step: TestStep, test_case: TestCase):
    delay = float(step.input_value) if step.input_value else 2.0
    await asyncio.sleep(delay)

@register("VERIFY_TEXT")
async def handle_verify_text(page: Page, step: TestStep, test_case: TestCase):
    await page.wait_for_selector(step.target_selector, timeout=5000)
    content = await page.inner_text(step.target_selector)
    val = step.input_value or ""
    if val not in content:
        raise AssertionError(f"Teks '{val}' tidak ditemukan pada selector '{step.target_selector}'. Teks aktual: '{content}'")