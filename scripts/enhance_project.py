"""Post-build image guarantee for related project Pages. No network or generation.

Adds a local-to-the-host fallback to every article and image-backed article cards.
Runs after the project's normal static/Hugo build, before artifact upload.
Existing text, links, scripts, article images and publishing schedules are retained.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

BASE = "https://musclelove-777.github.io"
SKIP = {".git", "node_modules", "templates", "layouts", "themes", "scripts", "blog_engine", "references", ".venv"}
IMAGES = {
    "ai": ("ai-studio.webp", "AIクリエイティブをイメージしたパソコンと光るキューブ", 1536, 1024),
    "sport": ("competition.webp", "架空の競技会場のイメージイラスト", 1536, 1024),
    "fitness": ("fitness-01.webp", "架空の成人女性によるフィットネスのAIイメージ", 720, 1080),
    "art": ("brand-hero.webp", "架空の成人女性のオリジナルイラスト", 1536, 1024),
}


def chosen_image(name):
    if any(x in name for x in ("ai-tool", "guide", "flux")):
        return IMAGES["ai"]
    if any(x in name for x in ("prowrestling", "fighting")):
        return IMAGES["sport"]
    if any(x in name for x in ("fitness", "physique", "armwrestling", "meal")):
        return IMAGES["fitness"]
    return IMAGES["art"]


def new_image(soup, cover, eager=False):
    name, alt, width, height = cover
    return soup.new_tag("img", src="/assets/images/" + name, alt=alt, width=str(width), height=str(height),
                        loading="eager" if eager else "lazy", decoding="async", attrs={"data-ml-fallback":"/assets/images/" + name})


def article_page(relative, soup):
    return bool({"articles", "posts", "post"}.intersection(relative.parts) or
                soup.find("meta", property="og:type", content="article") or
                soup.select_one('article.post-single') or
                any(re.search(r'"@type"\s*:\s*"(?:Article|BlogPosting|NewsArticle)"', tag.get_text()) for tag in soup.find_all("script", type="application/ld+json")))


def run(root, project):
    if not (root / "index.html").is_file():
        raise ValueError("Build output has no index.html; refusing to publish an empty site")
    cover = chosen_image(project)
    counts = Counter()
    failures = []
    for path in sorted(root.rglob("*.html")):
        relative = path.relative_to(root)
        if SKIP.intersection(relative.parts):
            continue
        original = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(original, "html.parser")
        if not soup.body or not soup.head or not soup.h1:
            continue
        if any(str(m.get("http-equiv", "")).lower() == "refresh" for m in soup.find_all("meta")):
            counts["redirects"] += 1
            continue
        article = article_page(relative, soup)
        counts["pages"] += 1
        counts["articles"] += int(article)
        classes = soup.body.get("class", [])
        if "ml-page" not in classes:
            soup.body["class"] = classes + ["ml-page"]
        if not soup.find("link", href="/assets/css/visual.css"):
            soup.head.append(soup.new_tag("link", rel="stylesheet", href="/assets/css/visual.css"))
        if not soup.find("script", src="/assets/js/visual.js"):
            soup.head.append(soup.new_tag("script", src="/assets/js/visual.js", defer=""))
        # Ensure a genuine rendered image even in source templates that only had og:image.
        if (article or relative.as_posix() == "index.html") and not soup.select_one(".ml-project-cover"):
            figure = soup.new_tag("figure", attrs={"class":"ml-cover ml-project-cover"})
            figure.append(new_image(soup, cover, eager=True))
            caption = soup.new_tag("figcaption")
            caption.string = "AIによるイメージ画像です。実在の人物・大会・商品の写真ではありません。"
            figure.append(caption)
            # Keep the existing title first and do not insert before site navigation.
            soup.h1.insert_after(figure)
        for selector in ("a.article-card", "a.card", "article.post-entry", "article.article-card", ".post-card", ".article-item"):
            for card in soup.select(selector):
                if card.find("img") or not card.get_text(strip=True):
                    continue
                img = new_image(soup, cover)
                img["class"] = "ml-card-image"
                img["alt"] = ""
                card.insert(0, img)
                counts["cards_added"] += 1
        for img in soup.find_all("img"):
            img["data-ml-fallback"] = "/assets/images/" + cover[0]
        if article:
            for attr, key in (("property", "og:image"), ("name", "twitter:image")):
                meta = soup.find("meta", attrs={attr:key})
                if meta is None:
                    meta = soup.new_tag("meta", attrs={attr:key})
                    soup.head.append(meta)
                meta["content"] = BASE + "/assets/images/" + cover[0]
            if not soup.select_one(".ml-project-cover img"):
                failures.append(relative.as_posix())
            else:
                counts["articles_with_image"] += 1
        new = re.sub(r"(<!DOCTYPE[^>]*>)\s*", r"\1\n", str(soup), count=1, flags=re.I)
        if new != original:
            path.write_text(new, encoding="utf-8")
    result = {"status":"PASS" if not failures and counts["pages"] else "REVISE", "project":project, **counts, "missing":failures}
    (root / "ml-image-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    result = run(args.root.resolve(), args.project)
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "PASS":
        raise SystemExit(1)
