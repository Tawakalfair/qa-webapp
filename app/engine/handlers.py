import os
import re
import asyncio
from typing import Any
from playwright.async_api import Page, expect


async def execute_single_command(page: Page, step: Any, base_url: str, run_id: str = "DEFAULT"):
    """
    Penerjemah dan eksekutor untuk setiap jenis perintah Playwright.
    """
    cmd = step.command.upper()
    selector = step.target_selector.strip() if step.target_selector else None
    val = step.input_value.strip() if step.input_value else None

    def resolve_url(raw_url: str) -> str:
        if raw_url.startswith("http://") or raw_url.startswith("https://"):
            return raw_url
        base = base_url.rstrip("/")
        path = raw_url.lstrip("/")
        return f"{base}/{path}"

    if cmd == "GOTO_URL":
        target_url = resolve_url(val) if val else base_url
        # Menggunakan domcontentloaded agar tidak menggantung menanti polling background
        await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)

    elif cmd == "CLICK":
        if not selector:
            raise ValueError("Perintah CLICK membutuhkan target_selector.")
        
        try:
            # 1. Coba klik standar
            await page.click(selector, timeout=3000)
        except Exception:
            # 2. Jika tertutup lapisan transparan, paksa klik lewat JavaScript DOM
            await page.eval_on_selector(selector, "el => el.click()")

    elif cmd == "DOUBLE_CLICK":
        if not selector:
            raise ValueError("Perintah DOUBLE_CLICK membutuhkan target_selector.")
        await page.dblclick(selector, timeout=10000)

    elif cmd == "RIGHT_CLICK":
        if not selector:
            raise ValueError("Perintah RIGHT_CLICK membutuhkan target_selector.")
        await page.click(selector, button="right", timeout=10000)

    elif cmd == "TYPE_TEXT":
        if not selector:
            raise ValueError("Perintah TYPE_TEXT membutuhkan target_selector.")
        
        try:
            # 1. PAKSA FOKUS ke elemen lewat JavaScript (Menembus invisible overlay Google)
            await page.eval_on_selector(selector, "el => { el.focus(); el.click(); }")
            
            # 2. Ketik langsung lewat Keyboard Browser ke elemen yang sedang fokus
            await page.keyboard.type(val or "", delay=30)
        except Exception:
            # 3. Fallback Ekstrem: Suntikkan teks langsung ke atribut 'value' HTML
            await page.eval_on_selector(
                selector,
                """(el, text) => {
                    el.value = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                val or ""
            )

    elif cmd == "CLEAR_TEXT":
        if not selector:
            raise ValueError("Perintah CLEAR_TEXT membutuhkan target_selector.")
        await page.fill(selector, "", timeout=10000)

    elif cmd == "PRESS_KEY":
        if not selector:
            raise ValueError("Perintah PRESS_KEY membutuhkan target_selector.")
        await page.press(selector, val or "Enter", timeout=10000)

    elif cmd == "SELECT_OPTION":
        if not selector:
            raise ValueError("Perintah SELECT_OPTION membutuhkan target_selector.")
        await page.select_option(selector, label=val, timeout=10000)

    elif cmd == "CHECK":
        if not selector:
            raise ValueError("Perintah CHECK membutuhkan target_selector.")
        await page.check(selector, timeout=10000)

    elif cmd == "UNCHECK":
        if not selector:
            raise ValueError("Perintah UNCHECK membutuhkan target_selector.")
        await page.uncheck(selector, timeout=10000)

    elif cmd == "HOVER":
        if not selector:
            raise ValueError("Perintah HOVER membutuhkan target_selector.")
        await page.hover(selector, timeout=10000)

    elif cmd == "SCROLL_DOWN":
        pixels = int(val) if (val and val.isdigit()) else 300
        if selector:
            await page.eval_on_selector(selector, f"(el) => el.scrollBy(0, {pixels})")
        else:
            await page.evaluate(f"window.scrollBy(0, {pixels})")

    elif cmd == "SCROLL_UP":
        pixels = int(val) if (val and val.isdigit()) else 300
        if selector:
            await page.eval_on_selector(selector, f"(el) => el.scrollBy(0, -{pixels})")
        else:
            await page.evaluate(f"window.scrollBy(0, -{pixels})")

    elif cmd == "SCROLL_RIGHT":
        pixels = int(val) if (val and val.isdigit()) else 300
        if selector:
            await page.eval_on_selector(selector, f"(el) => el.scrollBy({pixels}, 0)")
        else:
            await page.evaluate(f"window.scrollBy({pixels}, 0)")

    elif cmd == "TAKE_SCREENSHOT_FULL":
        screenshot_dir = os.path.join("static", "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        # Penamaan file terstruktur: RUN_ID + STEP_ORDER
        filename = f"case_{step.test_case_id}_step_{step.step_order}.png"
        filepath = os.path.join(screenshot_dir, filename)
        await page.screenshot(path=filepath, full_page=True)

    elif cmd == "WAIT":
        seconds = float(val) if (val and val.replace('.', '', 1).isdigit()) else 1.0
        await asyncio.sleep(seconds)

    elif cmd == "WAIT_FOR_SELECTOR":
        if not selector:
            raise ValueError("Perintah WAIT_FOR_SELECTOR membutuhkan target_selector.")
        await page.wait_for_selector(selector, state="visible", timeout=10000)

    elif cmd == "VERIFY_TEXT":
        if not selector:
            raise ValueError("Perintah VERIFY_TEXT membutuhkan target_selector.")
        element = await page.wait_for_selector(selector, state="visible", timeout=10000)
        text_content = await element.text_content()
        if not val or val not in text_content:
            raise AssertionError(f"Verifikasi Teks Gagal! Diharapkan mengandung '{val}', tetapi mendapatkan '{text_content}'.")

    elif cmd == "VERIFY_ELEMENT_VISIBLE":
        if not selector:
            raise ValueError("Perintah VERIFY_ELEMENT_VISIBLE membutuhkan target_selector.")
        is_visible = await page.is_visible(selector)
        if not is_visible:
            raise AssertionError(f"Verifikasi Elemen Gagal! Elemen '{selector}' tidak tampak pada layar.")

    elif cmd in ["ASSERT", "VERIFY"]:
        if not selector:
            raise ValueError(f"Perintah {cmd} membutuhkan target_selector.")
        
        locator = page.locator(selector)
        val_lower = val.lower()
        ASSERT_TIMEOUT = 5000  # <--- Set Timeout Assert ke 5 Detik (5000 ms)

        # 1. Verifikasi Visual Warna / Style (e.g., "background is red", "bg-red", "color green")
        if any(keyword in val_lower for keyword in ["background", "bg", "color", "warna"]):
            if any(w in val_lower for w in ["red", "merah", "danger"]):
                try:
                    await expect(locator).to_have_class(re.compile(r"red|danger|error|rose|amber"), timeout=ASSERT_TIMEOUT)
                except Exception:
                    bg_color = await locator.evaluate("el => window.getComputedStyle(el).backgroundColor")
                    if not any(c in bg_color for c in ["255", "239", "220", "248", "252"]):
                        raise AssertionError(f"Ekspektasi warna background merah, tetapi mendapatkan: {bg_color}")
            elif any(w in val_lower for w in ["green", "hijau", "success"]):
                await expect(locator).to_have_class(re.compile(r"green|emerald|success"), timeout=ASSERT_TIMEOUT)

        # 2. Verifikasi Matematika/Angka (e.g., "< 0", "> 100", "<= 15", "!= 0")
        elif re.match(r"^([<>]=?|!=|=)\s*(-?\d+(\.\d+)?)$", val):
            match = re.match(r"^([<>]=?|!=|=)\s*(-?\d+(\.\d+)?)$", val)
            operator = match.group(1)
            target_num = float(match.group(2))

            # Tunggu elemen muncul maks 5 detik
            element = await page.wait_for_selector(selector, state="visible", timeout=ASSERT_TIMEOUT)
            text_content = await element.text_content() or ""
            cleaned_num_str = re.sub(r"[^\d.-]", "", text_content.replace(",", "."))
            
            if not cleaned_num_str:
                raise AssertionError(f"Elemen '{selector}' tidak mengandung angka untuk dibandingkan dengan '{val}'.")

            actual_num = float(cleaned_num_str)

            ops = {
                "<": actual_num < target_num,
                "<=": actual_num <= target_num,
                ">": actual_num > target_num,
                ">=": actual_num >= target_num,
                "!=": actual_num != target_num,
                "=": actual_num == target_num,
            }
            if not ops.get(operator, False):
                raise AssertionError(f"Gagal verifikasi angka: Nilai aktual ({actual_num}) tidak memenuhi kondisi '{val}'.")

        # 3. Verifikasi Status Elemen (e.g., "disabled", "visible")
        elif val_lower in ["disabled", "non-aktif"]:
            await expect(locator).to_be_disabled(timeout=ASSERT_TIMEOUT)
        elif val_lower in ["visible", "tampil"]:
            await expect(locator).to_be_visible(timeout=ASSERT_TIMEOUT)

        # 4. Default: Verifikasi Teks/Nilai Biasa
        else:
            await expect(locator).to_contain_text(val, timeout=ASSERT_TIMEOUT)
    
    else:
        raise ValueError(f"Perintah tidak dikenal: {cmd}")
        