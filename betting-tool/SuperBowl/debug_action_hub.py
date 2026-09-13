from playwright.sync_api import sync_playwright
import re

HUB = "https://www.actionnetwork.com/nfl/picks/game"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        page = browser.new_page()
        page.goto(HUB, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3000)

        print("\n=== BASIC ===")
        print("URL:", page.url)
        print("Title:", page.title())

        print("\n=== 'BY GAME' CANDIDATES ===")
        # Print all anchors with href "/picks/game"
        anchors = page.locator("a[href='/picks/game']")
        print("a[href='/picks/game'] count:", anchors.count())
        for i in range(min(anchors.count(), 5)):
            el = anchors.nth(i)
            print(f"- [{i}] text={el.inner_text().strip()!r} href={el.get_attribute('href')!r}")

        # Also any link role with name "By Game"
        by_game_links = page.get_by_role("link", name=re.compile(r"By Game", re.I))
        print("role=link name~By Game count:", by_game_links.count())
        for i in range(min(by_game_links.count(), 5)):
            el = by_game_links.nth(i)
            print(f"- [{i}] text={el.inner_text().strip()!r}")

        print("\n=== LEFT RAIL (LEAGUE / EVENTS) TEXT SNIPPET ===")
        # Grab visible text from the left rail if present
        # This is loose on purpose; we just want to see what league it thinks it's on.
        left = page.locator("aside").first
        if left.count() > 0:
            txt = left.inner_text()
            print(txt[:800].replace("\n\n", "\n"))
        else:
            print("No <aside> found")

        print("\n=== GAME ROW LINKS (first 15 links that look like nfl-game) ===")
        game_links = page.locator("a[href*='/nfl-game/']")
        print("nfl-game link count:", game_links.count())
        for i in range(min(game_links.count(), 15)):
            el = game_links.nth(i)
            href = el.get_attribute("href")
            text = (el.inner_text() or "").strip().replace("\n", " ")
            print(f"- [{i}] href={href!r} text={text[:120]!r}")

        print("\n=== BUTTONS LABELED 'Picks' (count + sample) ===")
        picks_buttons = page.get_by_role("button", name=re.compile(r"picks", re.I))
        print("picks buttons:", picks_buttons.count())
        for i in range(min(picks_buttons.count(), 10)):
            text = (picks_buttons.nth(i).inner_text() or "").strip()
            print(f"- [{i}] {text!r}")

        print("\nLeave this window open. Press Enter here to close.")
        input()
        browser.close()

if __name__ == "__main__":
    main()
