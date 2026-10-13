"""Check published episode links, then notify a Discord incoming webhook.

Uses standard HTTP or an ordinary Chromium browser. Does not bypass verification pages.
"""
import argparse
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "state.json"


class SourceError(Exception):
    pass


class DeliveryError(Exception):
    pass


class EpisodeParser(HTMLParser):
    def __init__(self, show_url):
        super().__init__(convert_charrefs=True)
        self.show_url = show_url
        self.in_latest = False
        self.has_latest = False
        self.episodes = {}
        self.link = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li" and "latest_eps" in attrs.get("class", "").split():
            self.in_latest = True
            self.has_latest = True
        if tag == "a" and self.in_latest:
            self.link = urljoin(self.show_url, attrs.get("href", ""))
            self.parts = []

    def handle_data(self, data):
        if self.link is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            label = "".join(self.parts).strip()
            base, target = urlsplit(self.show_url), urlsplit(self.link)
            tail = target.path.removeprefix(base.path.rstrip("/") + "/")
            # Only accept numbered episode links in this exact show's directory.
            match = re.fullmatch(r"tap-(\d+)-\d+\.html", tail)
            if (target.scheme == "https" and target.netloc == base.netloc
                    and match and label.isdigit()
                    and int(label) == int(match.group(1))):
                number = int(label)
                self.episodes[number] = {
                    "number": number, "label": label,
                    "url": target._replace(query="", fragment="").geturl(),
                }
            self.link = None
            self.parts = []
        if tag == "li":
            self.in_latest = False


def parse_episodes(html, show_url):
    parser = EpisodeParser(show_url)
    parser.feed(html)
    if not parser.has_latest or not parser.episodes:
        raise SourceError("Không đọc được mục Tập mới: có thể bị chặn/xác minh, hoặc web đã đổi cấu trúc. Không gửi thông báo.")
    return sorted(parser.episodes.values(), key=lambda ep: ep["number"])


def fetch_episodes(show):
    if os.environ.get("BROWSER_FETCH") == "true":
        return fetch_browser_episodes(show)
    req = Request(show["url"], headers={
        "User-Agent": "AnimeEpisodeNotifier/1.0",
        "Accept": "text/html", "Accept-Language": "vi-VN,vi;q=0.9",
    })
    try:
        with urlopen(req, timeout=30) as response:
            if urlsplit(response.url).path.startswith("/xac-minh"):
                raise SourceError("Website yêu cầu xác minh khu vực. Chưa thể dùng máy chủ này.")
            html = response.read(2_000_000).decode("utf-8", errors="replace")
    except HTTPError as error:
        body = error.read(100_000).decode("utf-8", errors="replace").lower()
        reason = "chặn truy cập HTTP"
        if "cloudflare" in body or "just a moment" in body:
            reason = "trang kiểm tra truy cập Cloudflare"
        if "xác minh" in body or "xac-minh" in body or "not available in your area" in body:
            reason = "trang xác minh/giới hạn khu vực"
        raise SourceError(f"Website trả HTTP {error.code}: {reason}; chưa đọc được nguồn.") from None
    except (URLError, TimeoutError, OSError):
        raise SourceError("Không kết nối được website; sẽ thử lại ở lần chạy sau.") from None
    return parse_episodes(html, show["url"])


def fetch_browser_episodes(show):
    from playwright.sync_api import sync_playwright, Error as BrowserError
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(locale="vi-VN")
            page = context.new_page()
            page.goto(show["url"], wait_until="domcontentloaded", timeout=30_000)
            try:
                page.locator("li.latest_eps a").first.wait_for(state="visible", timeout=15_000)
            except BrowserError:
                title = page.title().lower()
                if "xác minh" in title or "/xac-minh" in page.url:
                    raise SourceError("Trình duyệt GitHub gặp xác minh/giới hạn khu vực; không đọc được nguồn.") from None
                if "just a moment" in title or "attention required" in title:
                    raise SourceError("Trình duyệt GitHub gặp kiểm tra truy cập Cloudflare; không tự vượt xác minh.") from None
                raise SourceError("Trình duyệt GitHub không đọc được mục Tập mới; nguồn bị chặn hoặc đổi cấu trúc.") from None
            html = page.locator("li.latest_eps").first.evaluate("element => element.outerHTML")
            browser.close()
        return parse_episodes(html, show["url"])
    except BrowserError:
        raise SourceError("Trình duyệt không tải được trang; cần kiểm tra khả năng truy cập từ máy chủ.") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_webhook(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "discord.com"
            or not re.fullmatch(r"/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9_.-]+", parsed.path)):
        raise DeliveryError("Thiếu/sai DISCORD_WEBHOOK_URL. Nhập URL webhook vào GitHub Actions Secret.")
    return parsed._replace(query=urlencode({"wait": "true"}), fragment="").geturl()


def send_discord(webhook, payload):
    url = validate_webhook(webhook)
    payload = {"username": "Anime Update", "allowed_mentions": {"parse": []}, **payload}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    opener = build_opener(NoRedirect())
    for attempt in range(3):
        request = Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "AnimeEpisodeNotifier/1.0"})
        try:
            with opener.open(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not result.get("id"):
                raise DeliveryError("Discord chưa xác nhận lưu tin nhắn.")
            return result["id"]
        except HTTPError as error:
            if error.code == 429 and attempt < 2:
                try:
                    delay = float(json.loads(error.read()).get("retry_after", 2))
                except (ValueError, TypeError):
                    delay = 2
                time.sleep(min(max(delay, 1), 30))
                continue
            raise DeliveryError(f"Discord trả HTTP {error.code}. Kiểm tra webhook/quyền gửi.") from None
        except (URLError, TimeoutError, OSError, ValueError):
            # Don't immediately retry an ambiguous delivery: Discord may have received it.
            raise DeliveryError("Chưa xác nhận Discord nhận tin. Dừng để kiểm tra; lần chạy sau sẽ thử lại.") from None
    raise DeliveryError("Discord đang giới hạn gửi tin.")


def load_state(path=STATE):
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != 1 or not isinstance(state.get("shows"), dict):
        raise ValueError("Sai định dạng state; không tự xóa lịch sử gửi.")
    for entry in state["shows"].values():
        if (not isinstance(entry.get("baseline_max"), int)
                or not isinstance(entry.get("sent"), dict)):
            raise ValueError("Lịch sử gửi bị lỗi; cần kiểm tra trước khi chạy tiếp.")
    return state


def save_state(state, path=STATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def baseline(state, show, episodes):
    if show["id"] not in state["shows"]:
        state["shows"][show["id"]] = {
            "baseline_max": max(ep["number"] for ep in episodes), "sent": {},
        }


def notify_show(state, show, episodes, deliver, persist):
    entry = state["shows"].get(show["id"])
    if entry is None:
        raise SourceError("Phim chưa có mốc ban đầu; chạy initialize trước.")
    sent_count = 0
    for ep in episodes:
        key = str(ep["number"])
        if ep["number"] <= entry["baseline_max"] or key in entry["sent"]:
            continue
        payload = {"embeds": [{
            "title": f'{show["name"]} • Tập {ep["label"]} đã cập nhật',
            "url": ep["url"], "color": 5793266,
            "description": f'[Xem tập {ep["label"]}]({ep["url"]})\nNguồn: AnimeVietsub',
        }]}
        message_id = deliver(payload)
        entry["sent"][key] = message_id
        persist(state)
        sent_count += 1
    return sent_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "initialize", "notify"], default="check")
    args = parser.parse_args()
    shows = json.loads((ROOT / "anime.json").read_text(encoding="utf-8"))
    state = load_state()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if args.mode != "check":
        validate_webhook(webhook)
    fetched, errors = [], []
    for show in shows:
        try:
            episodes = fetch_episodes(show)
            print(f'{show["name"]}: đọc được tập ' + ", ".join(ep["label"] for ep in episodes))
            fetched.append((show, episodes))
        except SourceError as error:
            errors.append(f'{show["name"]}: {error}')
    if args.mode == "initialize" and not errors:
        # A deliberate one-time setup message confirms source access AND webhook delivery.
        lines = [f'• {show["name"]}: hiện tới tập {episodes[-1]["label"]}' for show, episodes in fetched]
        send_discord(webhook, {"content": "✅ Đã kết nối Anime Update\n" + "\n".join(lines) + "\nĐã ghi nhận mốc ban đầu, chỉ báo các tập mới từ sau mốc này."})
        for show, episodes in fetched:
            baseline(state, show, episodes)
        save_state(state)
    elif args.mode == "notify":
        for show, episodes in fetched:
            try:
                count = notify_show(state, show, episodes, lambda payload: send_discord(webhook, payload), save_state)
                print(f'{show["name"]}: gửi {count} thông báo mới.')
            except (SourceError, DeliveryError) as error:
                errors.append(f'{show["name"]}: {error}')
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, SourceError, DeliveryError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
