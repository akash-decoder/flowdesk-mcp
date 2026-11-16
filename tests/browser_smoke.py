import os, subprocess, sys, tempfile, time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, FLOWDESK_DB=tmp + "/ui.sqlite")
    server = subprocess.Popen([sys.executable, "-m", "flowdesk", "web", "--port","18765"],env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = "http://127.0.0.1:18765"
        for _ in range(60):
            try:
                urlopen(url, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("Editor failed to start")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width":1440,"height":1000},device_scale_factor=1)
            errors=[]
            page.on("pageerror",lambda e: errors.append(str(e)))
            page.goto(url)
            expect(page.locator(".step")).to_have_count(3)
            page.get_by_role("button",name="Save workflow").click()
            expect(page.locator("#status")).to_contain_text("Revision 1")
            page.get_by_role("button",name="Preview",exact=True).click()
            expect(page.locator("#result")).to_contain_text("Quote request from Alex")
            page.get_by_role("button",name="Run now",exact=True).click()
            expect(page.locator("#status")).to_contain_text("Run · completed")
            page.get_by_role("button",name="Records",exact=True).click()
            expect(page.locator("#items summary")).to_have_text("Record 1")
            page.get_by_role("button",name="Run history").click()
            expect(page.locator("#items summary")).to_contain_text("completed")
            page.get_by_role("button",name="Editor",exact=True).click()
            page.get_by_role("button",name="Add step").click()
            page.get_by_label("Step type").select_option("deliver")
            expect(page.get_by_label("Destination alias")).to_have_value("crm")
            page.get_by_role("button",name="Move up").click()
            page.get_by_role("button",name="Remove",exact=True).click()
            page.get_by_role("button",name="Save workflow").click()
            expect(page.locator("#status")).to_contain_text("Revision 2")
            page.locator(".step").nth(1).click()

            page.set_viewport_size({"width":390,"height":844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.get_by_role("button",name="New workflow").click()
            page.get_by_label("Workflow name").fill("Mobile intake")
            page.get_by_role("button",name="Save workflow").click()
            expect(page.locator("#library")).to_contain_text("Mobile intake")
            assert not errors, errors
            browser.close()
            print("Desktop and mobile UI passed.")
    finally:
        server.terminate()
        server.wait(timeout=10)
