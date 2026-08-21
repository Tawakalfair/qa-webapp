import os
import re
import asyncio
from typing import Any, Optional
from playwright.async_api import Page, expect


async def execute_single_command(
        page: Page, 
        step: Any, 
        base_url: str, 
        run_id: str = "DEFAULT",
        user_id: Optional[int] = None
        ):
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

    elif cmd == "CLICK_SAME_TAB":
        if not selector:
            raise ValueError("Perintah CLICK_SAME_TAB membutuhkan target_selector.")
        try:
            # Menggunakan JavaScript DOM untuk menghapus atribut target (agar tidak buka tab baru) lalu mengkliknya
            await page.eval_on_selector(selector, "el => { el.removeAttribute('target'); el.click(); }")
        except Exception as e:
            raise AssertionError(f"Gagal melakukan klik paksa di tab yang sama: {str(e)}")
        
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
            raise ValueError("Command SELECT_OPTION requires a target_selector.")
        
        clean_val = val.strip() if val else ""

        # 1. Validate element tag: if not <select>, fail immediately without waiting for timeout
        tag_name = await page.eval_on_selector(selector, "el => el.tagName.toLowerCase()")
        if tag_name != "select":
            raise AssertionError(
                f"Target '{selector}' is an <{tag_name}> element, not a <select> dropdown. "
                f"Please use 'TYPE_TEXT' or 'CLICK' instead."
            )

        # 2. If it is a <select> element, attempt selection by label first, then fallback to value
        try:
            await page.select_option(selector, label=clean_val, timeout=3000)
        except Exception:
            try:
                await page.select_option(selector, value=clean_val, timeout=3000)
            except Exception:
                raise AssertionError(f"Option '{clean_val}' not found in dropdown '{selector}'.")

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
        pixels = int(val) if (val and str(val).isdigit()) else 300
        target_sel = selector.strip() if selector and selector.strip() else "#mainDiv"
        
        try:
            # Skrip Universal: Telusuri seluruh frame/iframe, ubah scrollLeft, dan paksa render
            scroll_script = """
            ([sel, px]) => {
                // 1. Fungsi pencari elemen menembus seluruh iframe
                function getTargetElement(s) {
                    let el = document.querySelector(s) || document.getElementById('mainDiv');
                    if (el) return { element: el, win: window };
                    
                    let iframes = document.querySelectorAll('iframe, frame');
                    for (let iframe of iframes) {
                        try {
                            let iDoc = iframe.contentDocument || iframe.contentWindow.document;
                            let iEl = iDoc.querySelector(s) || iDoc.getElementById('mainDiv');
                            if (iEl) return { element: iEl, win: iframe.contentWindow };
                        } catch(e) {}
                    }
                    return null;
                }

                let target = getTargetElement(sel);
                if (target) {
                    let el = target.element;
                    let win = target.win;

                    // 2. Ubah nilai scrollLeft secara langsung
                    el.scrollLeft += px;
                    
                    // 3. Panggil fungsi sinkronisasi header tabel bawaan web
                    if (typeof win.scrollTable === 'function') {
                        win.scrollTable();
                    } else if (typeof win.window.scrollTable === 'function') {
                        win.window.scrollTable();
                    } else {
                        el.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }

                    // 4. Paksa visual update agar perubahan langsung ter-render di video
                    el.style.display = 'none';
                    el.offsetHeight; // trigger reflow
                    el.style.display = '';
                    
                    return el.scrollLeft;
                }
                return 0;
            }
            """
            await page.evaluate(scroll_script, [target_sel, pixels])
        except Exception as e:
            raise AssertionError(f"Gagal menggeser elemen '{target_sel}': {str(e)}")

    elif cmd == "TAKE_SCREENSHOT_FULL":
        # 🟢 ISOLATED USER SCREENSHOT DIRECTORY
        user_folder = f"user_{user_id}" if user_id else "common"
        screenshot_dir = os.path.join("static", "screenshots", user_folder)
        os.makedirs(screenshot_dir, exist_ok=True)
        
        filename = f"case_{step.test_case_id}_step_{step.step_order}.png"
        filepath = os.path.join(screenshot_dir, filename)

        # 1. Fetch current URL
        current_url = page.url

        # 2. Inject custom URL bar banner
        await page.evaluate("""
            if (document.body) {
                const banner = document.createElement('div');
                banner.innerHTML = 'Teks Bukti Pengujian...';
                // ... (styling banner Anda) ...
                
                document.body.prepend(banner);
            } else {
                console.warn('Tidak dapat menyuntikkan banner: document.body tidak ditemukan.');
            }
        """)

        # 3. Capture screenshot
        is_full = (cmd == "TAKE_SCREENSHOT_FULL")
        await page.screenshot(path=filepath, full_page=is_full)

    elif cmd == "WAIT":
        seconds = float(val) if (val and val.replace('.', '', 1).isdigit()) else 1.0
        await asyncio.sleep(seconds)

    elif cmd == "WAIT_FOR_SELECTOR":
        if not selector:
            raise ValueError("Perintah WAIT_FOR_SELECTOR membutuhkan target_selector.")
        await page.wait_for_selector(selector, state="visible", timeout=20000)

    elif cmd == "VERIFY_TEXT":
        if not selector:
            raise ValueError("Perintah VERIFY_TEXT membutuhkan target_selector.")
        element = await page.wait_for_selector(selector, state="visible", timeout=20000)
        text_content = await element.text_content()
        if not val or val not in text_content:
            raise AssertionError(f"Verifikasi Teks Gagal! Diharapkan mengandung '{val}', tetapi mendapatkan '{text_content}'.")

    elif cmd == "VERIFY_ELEMENT_VISIBLE":
        if not selector:
            raise ValueError("Perintah VERIFY_ELEMENT_VISIBLE membutuhkan target_selector.")
        is_visible = await page.is_visible(selector)
        if not is_visible:
            raise AssertionError(f"Verifikasi Elemen Gagal! Elemen '{selector}' tidak tampak pada layar.")

    # 🟢 COMMAND BARU: Verifikasi Download & Tampilkan Bukti Visual
    elif step.command == "VERIFY_DOWNLOAD":
        target = step.target_selector.strip() if step.target_selector else None
        
        # 1. Tunggu aksi klik memicu proses download file
        if target:
            async with page.expect_download(timeout=20000) as download_info:
                await page.locator(target).click()
            download = await download_info.value
        else:
            # Jika klik sudah dilakukan di step sebelumnya
            async with page.expect_download(timeout=20000) as download_info:
                download = await download_info.value

        # 2. Ambil informasi nama file asli yang terdownload
        downloaded_file_name = download.suggested_filename
        
        # Simpan file sementara untuk memastikan file utuh (opsional)
        temp_path = await download.path()
        file_size_kb = round(os.path.getsize(temp_path) / 1024, 2) if temp_path and os.path.exists(temp_path) else 0

        # 3. Injeksi Banner Bukti Hijau ke Layar Browser
        await page.evaluate(f"""
            const oldBadge = document.getElementById('qa-download-evidence-badge');
            if (oldBadge) oldBadge.remove();

            const badge = document.createElement('div');
            badge.id = 'qa-download-evidence-badge';
            badge.innerHTML = `
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:20px;">📥</span>
                    <div>
                        <div style="font-size:12px; font-weight:bold; text-transform:uppercase; letter-spacing:0.5px;">File Downloaded Successfully</div>
                        <div style="font-size:11px; opacity:0.9; margin-top:2px;"><b>File:</b> {downloaded_file_name} (${file_size_kb} KB)</div>
                    </div>
                </div>
            `;
            badge.style.position = 'fixed';
            badge.style.top = '24px';
            badge.style.right = '24px';
            badge.style.backgroundColor = '#059669';
            badge.style.color = '#ffffff';
            badge.style.padding = '12px 20px';
            badge.style.borderRadius = '12px';
            badge.style.boxShadow = '0 10px 25px -5px rgba(0, 0, 0, 0.3)';
            badge.style.zIndex = '99999999';
            badge.style.fontFamily = 'Segoe UI, Tahoma, sans-serif';
            badge.style.border = '2px solid #34d399';
            document.body.appendChild(badge);
        """)
        
        # Jeda 500ms agar animasi render banner stabil
        await page.wait_for_timeout(500)

    elif cmd in ["ASSERT", "VERIFY"]:
        if not selector:
            raise ValueError(f"Command {cmd} requires a target_selector.")
        
        val_str = str(val).strip() if val is not None else ""
        val_lower = val_str.lower()
        ASSERT_TIMEOUT = 5000  # 5 seconds timeout limit
        locator = page.locator(selector)

        # 1. Checkbox & Radio Status Verification
        if val_lower in ["checked", "is checked", "tercentang", "centang", "selected"]:
            await expect(locator).to_be_checked(timeout=ASSERT_TIMEOUT)

        elif val_lower in ["unchecked", "not checked", "is unchecked", "tidak tercentang", "uncheck"]:
            await expect(locator).not_to_be_checked(timeout=ASSERT_TIMEOUT)

        # 2. Element State Verification (disabled, enabled, visible, hidden, empty, focused)
        elif val_lower in ["disabled", "non-aktif"]:
            await expect(locator).to_be_disabled(timeout=ASSERT_TIMEOUT)

        elif val_lower in ["enabled", "aktif"]:
            await expect(locator).to_be_enabled(timeout=ASSERT_TIMEOUT)

        elif val_lower in ["visible", "tampil", "is visible"]:
            await expect(locator).to_be_visible(timeout=ASSERT_TIMEOUT)

        elif val_lower in ["hidden", "sembunyi", "not visible", "is hidden"]:
            await expect(locator).to_be_hidden(timeout=ASSERT_TIMEOUT)

        elif val_lower in ["empty", "kosong"]:
            await expect(locator).to_be_empty(timeout=ASSERT_TIMEOUT)

        elif val_lower in ["focused", "fokus"]:
            await expect(locator).to_be_focused(timeout=ASSERT_TIMEOUT)

        # 3. Visual Color / CSS Style Verification (e.g. "background is red", "color green")
        elif any(keyword in val_lower for keyword in ["background", "bg", "color", "warna"]):
            if any(w in val_lower for w in ["red", "merah", "danger", "error", "rose"]):
                try:
                    await expect(locator).to_have_class(
                        re.compile(r"red|danger|error|rose|amber", re.I), 
                        timeout=ASSERT_TIMEOUT
                    )
                except Exception:
                    bg_color = await locator.evaluate("el => window.getComputedStyle(el).backgroundColor")
                    if not any(c in bg_color for c in ["255", "239", "220", "248", "252"]):
                        raise AssertionError(f"Expected red background color, but received: {bg_color}")
            elif any(w in val_lower for w in ["green", "hijau", "success", "emerald"]):
                try:
                    await expect(locator).to_have_class(
                        re.compile(r"green|emerald|success", re.I), 
                        timeout=ASSERT_TIMEOUT
                    )
                except Exception:
                    bg_color = await locator.evaluate("el => window.getComputedStyle(el).backgroundColor")
                    if not any(c in bg_color for c in ["34", "16", "22", "green", "emerald"]):
                        raise AssertionError(f"Expected green background color, but received: {bg_color}")

        # 4. Mathematical & Numeric Comparison (e.g. "< 0", "> 100", "<= 15", "= 10", "!= 0")
        elif (math_match := re.match(r"^([<>]=?|!=|=)\s*(-?\d+(\.\d+)?)$", val_str)):
            operator = math_match.group(1)
            target_num = float(math_match.group(2))

            # Retrieve text content or input value depending on HTML tag
            element = await page.wait_for_selector(selector, state="visible", timeout=ASSERT_TIMEOUT)
            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            
            if tag_name in ["input", "textarea", "select"]:
                raw_text = await element.input_value()
            else:
                raw_text = (await element.text_content()) or ""

            cleaned_num_str = re.sub(r"[^\d.-]", "", raw_text.replace(",", "."))
            if not cleaned_num_str:
                raise AssertionError(f"Element '{selector}' with text '{raw_text}' contains no numerical value to compare with '{val_str}'.")

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
                raise AssertionError(f"Numeric assertion failed: Actual value ({actual_num}) does not satisfy condition '{val_str}'.")

        # 5. Default Text / Value Verification (Smart detection for input fields vs regular elements)
        else:
            tag_name = await locator.evaluate("el => el.tagName.toLowerCase()")
            if tag_name in ["input", "textarea"]:
                await expect(locator).to_have_value(re.compile(re.escape(val_str), re.I), timeout=ASSERT_TIMEOUT)
            else:
                await expect(locator).to_contain_text(val_str, timeout=ASSERT_TIMEOUT)
    
    else:
        raise ValueError(f"Perintah tidak dikenal: {cmd}")
        