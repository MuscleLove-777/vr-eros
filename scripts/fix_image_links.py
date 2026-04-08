#!/usr/bin/env python3
"""
fix_image_links.py

content/posts/*.md 内の画像CDN直リンク (<a href="https://pics.dmm.co.jp/..."> や
<a href="https://doujin-assets.dmm.co.jp/...">) を、同じ商品ブロック内に存在する
FANZA アフィリリンクに置換する。

商品ブロックの境界:
  - frontmatter (--- ... ---) の後の本文を、行頭が "---" のみの水平線で分割
  - 各セグメント内の affiliate URL (af_id=pinky2400-990 を含むもの) を抽出
  - そのセグメント内の画像直リンク <a> の href を、そのセグメントの affiliate URL に置換
  - rel 属性は rel="nofollow sponsored" に統一
  - セグメントに affiliate URL が無ければ、ファイル全体で affiliate URL が1種類だけ
    ならそれを使う。複数あって特定不能なら当該セグメントはスキップしてログに残す。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "content" / "posts"

# 画像CDNホスト
CDN_HOST_RE = re.compile(
    r'https://(?:pics|doujin-assets|awsimgsrc)\.dmm\.co\.jp/[^"\s]+',
    re.IGNORECASE,
)

# 画像直リンクの <a ...> タグ全体 (中の <img ...> 込み)
# 例: <a href="https://pics.dmm.co.jp/.../x.jpg" target="_blank" rel="nofollow"><img ... /></a>
IMG_ANCHOR_RE = re.compile(
    r'<a\s+([^>]*?)href="(https://(?:pics|doujin-assets|awsimgsrc)\.dmm\.co\.jp/[^"]+)"([^>]*)>(\s*<img\b[^>]*/?>)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)

# affiliate URL: af_id=pinky2400-990 を含む URL
AFFILIATE_URL_RE = re.compile(
    r'https?://[^"\s\'<>]+af_id=pinky2400-990[^"\s\'<>]*',
    re.IGNORECASE,
)

# frontmatter を取り除くための正規表現 (先頭の --- ... --- ブロック)
FRONTMATTER_RE = re.compile(r'\A(---\r?\n.*?\r?\n---\r?\n)', re.DOTALL)

# 本文中の水平線 (行頭が --- のみ、空白含む可)
HR_SPLIT_RE = re.compile(r'(?m)^[ \t]*---[ \t]*$')


def split_segments(body: str) -> list[tuple[int, int, str]]:
    """本文を水平線で分割。各セグメントの (開始オフセット, 終了オフセット, 内容) を返す。"""
    positions = [m.start() for m in HR_SPLIT_RE.finditer(body)]
    bounds = [0] + positions + [len(body)]
    segments = []
    for i in range(len(bounds) - 1):
        s, e = bounds[i], bounds[i + 1]
        segments.append((s, e, body[s:e]))
    return segments


def extract_affiliates(text: str) -> list[str]:
    """テキスト内の affiliate URL を出現順に重複排除して返す。"""
    seen = []
    for m in AFFILIATE_URL_RE.finditer(text):
        url = m.group(0)
        # HTML エンティティ (&amp;) が混じる場合があるのでそのまま保持
        if url not in seen:
            seen.append(url)
    return seen


def process_file(path: Path) -> tuple[int, int, str | None]:
    """
    1ファイルを処理。
    戻り値: (置換件数, スキップしたセグメント数, スキップ理由 or None)
    """
    raw = path.read_text(encoding="utf-8")

    # 早期チェック: 画像直リンク <a> が無ければ何もしない
    if not IMG_ANCHOR_RE.search(raw):
        return (0, 0, None)

    # frontmatter を分離
    fm_match = FRONTMATTER_RE.match(raw)
    if fm_match:
        frontmatter = fm_match.group(1)
        body = raw[fm_match.end():]
    else:
        frontmatter = ""
        body = raw

    # ファイル全体の affiliate URL リスト
    all_affiliates = extract_affiliates(body)
    if not all_affiliates:
        return (0, 0, "affiliate_url が記事内に1件も存在しない")

    segments = split_segments(body)
    new_parts: list[str] = []
    total_replaced = 0
    skipped_segments = 0
    skip_reason: str | None = None

    for _, _, seg in segments:
        seg_affiliates = extract_affiliates(seg)

        # このセグメントで使う affiliate URL を決定
        if len(seg_affiliates) >= 1:
            # セグメント内に複数あっても、出現順で最初のものを採用
            # (商品ブロックでは最初の方にメインのアフィリリンクが来る)
            # ただし「最後の方」(まとめ部)が安全な場合もあるが、ここでは
            # 先頭のものを基準にする (ranking 形式に合致)
            target = seg_affiliates[0]
        elif len(all_affiliates) == 1:
            target = all_affiliates[0]
        else:
            # 特定不能: 画像直リンクが含まれていればスキップ (置換しない)
            if IMG_ANCHOR_RE.search(seg):
                skipped_segments += 1
                skip_reason = "セグメント内に affiliate_url が無く、ファイル全体に複数の affiliate_url があるため特定不能"
            new_parts.append(seg)
            continue

        replaced_in_seg = 0

        def repl(m: re.Match) -> str:
            nonlocal replaced_in_seg
            pre_attrs = m.group(1) or ""
            post_attrs = m.group(3) or ""
            img_tag = m.group(4)

            # rel 属性を pre_attrs / post_attrs から除去
            pre_clean = re.sub(r'\srel="[^"]*"', "", pre_attrs)
            post_clean = re.sub(r'\srel="[^"]*"', "", post_attrs)
            # target 属性が無ければ追加
            attrs = (pre_clean + post_clean).strip()
            if 'target=' not in attrs:
                attrs = (attrs + ' target="_blank"').strip()
            # rel を統一付与
            attrs = (attrs + ' rel="nofollow sponsored"').strip()

            replaced_in_seg += 1
            return f'<a href="{target}" {attrs}>{img_tag}</a>'

        new_seg = IMG_ANCHOR_RE.sub(repl, seg)
        total_replaced += replaced_in_seg
        new_parts.append(new_seg)

    new_body = "".join(new_parts)
    new_raw = frontmatter + new_body

    if new_raw != raw:
        # LF で保存
        new_raw = new_raw.replace("\r\n", "\n")
        path.write_bytes(new_raw.encode("utf-8"))

    return (total_replaced, skipped_segments, skip_reason)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="変更を書き込まない")
    ap.add_argument("--limit", type=int, default=0, help="処理ファイル数上限 (動作確認用)")
    ap.add_argument("--only", type=str, default=None, help="特定ファイル名で絞り込み (部分一致)")
    args = ap.parse_args()

    if args.dry_run:
        # ドライラン時は process_file 内の write_bytes をモンキーパッチ
        original_write = Path.write_bytes
        def noop(self, *a, **k):  # noqa: ANN001
            return 0
        Path.write_bytes = noop  # type: ignore

    files = sorted(POSTS_DIR.glob("*.md"))
    target_files: list[Path] = []
    for f in files:
        if args.only and args.only not in f.name:
            continue
        # 直リンクを含むファイルだけを対象 (高速化)
        try:
            text = f.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[READ-ERR] {f.name}: {e}", file=sys.stderr)
            continue
        if IMG_ANCHOR_RE.search(text):
            target_files.append(f)

    if args.limit:
        target_files = target_files[: args.limit]

    print(f"対象ファイル数: {len(target_files)}")

    total_files_changed = 0
    total_replaced = 0
    skipped_files: list[tuple[str, str]] = []
    skipped_segment_count = 0

    for f in target_files:
        try:
            replaced, skipped_segs, reason = process_file(f)
        except Exception as e:
            print(f"[ERR] {f.name}: {e}", file=sys.stderr)
            continue

        if replaced > 0:
            total_files_changed += 1
            total_replaced += replaced
        if skipped_segs > 0:
            skipped_segment_count += skipped_segs
        if replaced == 0 and reason:
            skipped_files.append((f.name, reason))

    print()
    print("=" * 60)
    print(f"処理対象記事数:        {len(target_files)}")
    print(f"実際に変更した記事数:  {total_files_changed}")
    print(f"置換した画像リンク総数:{total_replaced}")
    print(f"スキップしたセグメント:{skipped_segment_count}")
    print(f"スキップした記事数:    {len(skipped_files)}")
    if skipped_files:
        print("\n[スキップ詳細]")
        for name, reason in skipped_files[:50]:
            print(f"  - {name}: {reason}")
        if len(skipped_files) > 50:
            print(f"  ... 他 {len(skipped_files) - 50} 件")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
