"""
DMM/FANZAアフィリエイトAPIから商品データを取得するモジュール
"""

import time
import requests
from typing import Optional
from urllib.parse import urlencode, quote
from config import Config


def fetch_products(
    keyword: str = "",
    hits: int = Config.DEFAULT_HITS,
    service: str = Config.DEFAULT_SERVICE,
    floor: str = "",
    sort: str = Config.DEFAULT_SORT,
) -> list[dict]:
    """
    DMM Affiliate API v3から商品一覧を取得する

    Args:
        keyword: 検索キーワード
        hits: 取得件数（最大100）
        service: サービス種別（digital, mono等）
        floor: フロアID
        sort: ソート順（date, rank, price等）

    Returns:
        商品情報の辞書リスト
    """
    # 設定の検証
    if not Config.validate():
        return []

    # キーワード未指定時はデフォルトキーワードからランダムに選択
    if not keyword:
        import random
        keyword = random.choice(Config.DEFAULT_KEYWORDS)

    # APIリクエストパラメータの構築
    params = {
        "api_id": Config.API_ID,
        "affiliate_id": Config.AFFILIATE_ID,
        "site": "FANZA",
        "service": service,
        "hits": min(hits, 100),  # 最大100件
        "sort": sort,
        "keyword": keyword,
        "output": "json",
    }

    # フロア指定がある場合のみ追加
    if floor:
        params["floor"] = floor

    print(f"[取得中] キーワード「{keyword}」で{hits}件の商品を検索...")

    try:
        response = requests.get(Config.API_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print("[エラー] APIリクエストがタイムアウトしました")
        return []
    except requests.exceptions.ConnectionError:
        print("[エラー] APIサーバーに接続できません")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"[エラー] APIがHTTPエラーを返しました: {e}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"[エラー] リクエスト中に予期せぬエラーが発生: {e}")
        return []

    # レスポンスのパース
    try:
        data = response.json()
    except ValueError:
        print("[エラー] APIレスポンスのJSONパースに失敗しました")
        return []

    # エラーレスポンスのチェック
    result = data.get("result", {})
    status = result.get("status", 0)
    if status != 200:
        message = result.get("message", "不明なエラー")
        print(f"[エラー] API応答エラー: {message}")
        return []

    # 商品データの抽出
    items = result.get("items", [])
    if not items:
        print(f"[情報] キーワード「{keyword}」に該当する商品が見つかりませんでした")
        return []

    products = []
    for item in items:
        product = _parse_item(item)
        if product:
            # タイトルにキーワード関連語が含まれているかフィルタリング
            if _is_relevant(product, keyword):
                products.append(product)
            else:
                print(f"[除外] 関連度低: {product['title'][:40]}...")

    print(f"[完了] {len(products)}件の関連商品データを取得しました")
    return products


# VR系に関連するキーワード（タイトルやジャンルに含まれるべき語句）
RELEVANT_KEYWORDS = [
    "VR", "バーチャル", "没入", "主観", "ハイクオリティVR",
    "8KVR", "4KVR", "VRAV", "HQ", "視点",
]


def _is_relevant(product: dict, keyword: str) -> bool:
    """
    商品がテーマ（VR系）に関連するかチェックする

    タイトル・ジャンルに関連キーワードが1つでも含まれていればTrue
    """
    title = product.get("title", "").lower()
    genres = " ".join(product.get("genres", [])).lower()
    check_text = f"{title} {genres}"

    # 検索に使ったキーワード自体がタイトルに含まれるか
    if keyword.lower() in check_text:
        return True

    # 関連キーワードのいずれかが含まれるか
    for kw in RELEVANT_KEYWORDS:
        if kw.lower() in check_text:
            return True

    return False


def _build_affiliate_url(item: dict, affiliate_id: str) -> str:
    """
    商品のアフィリエイトURLを構築する

    APIのaffiliateURLが無効な場合（al.fanza.co.jpが400を返す場合）に備え、
    直接URL形式にアフィリエイトIDをクエリパラメータとして付与する。

    Args:
        item: APIレスポンスの商品データ
        affiliate_id: アフィリエイトID

    Returns:
        アフィリエイトURL文字列
    """
    content_id = item.get("content_id", "")
    direct_url = item.get("URL", "")

    # content_idがある場合、FANZA公式の詳細ページURLを構築
    if content_id:
        base_url = f"https://www.dmm.co.jp/digital/videoa/-/detail/=/cid={content_id}/"
        return f"{base_url}?af_id={affiliate_id}"

    # content_idがない場合、APIのURLにaf_idを付与
    if direct_url:
        separator = "&" if "?" in direct_url else "?"
        return f"{direct_url}{separator}af_id={affiliate_id}"

    # フォールバック: APIのaffiliateURLをそのまま使用
    return item.get("affiliateURL", "")


def _parse_item(item: dict) -> Optional[dict]:
    """
    APIレスポンスの1商品をパースして整形する

    Args:
        item: APIレスポンスの商品データ

    Returns:
        整形された商品情報辞書。パース失敗時はNone
    """
    try:
        # 画像URLの取得（大きい画像を優先）
        image_url = ""
        image_data = item.get("imageURL", {})
        if image_data:
            image_url = image_data.get("large", image_data.get("small", ""))

        # 価格情報の取得
        prices = item.get("prices", {})
        price = ""
        if prices:
            price_info = prices.get("price", prices.get("deliveries", {}).get("delivery", [{}]))
            if isinstance(price_info, str):
                price = price_info
            elif isinstance(price_info, list) and price_info:
                price = price_info[0].get("price", "")

        # ジャンル（タグ）の取得
        genres = []
        item_info = item.get("iteminfo", {})
        if item_info:
            genre_list = item_info.get("genre", [])
            genres = [g.get("name", "") for g in genre_list if g.get("name")]

        # 出演者の取得
        actresses = []
        if item_info:
            actress_list = item_info.get("actress", [])
            actresses = [a.get("name", "") for a in actress_list if a.get("name")]

        # サンプル画像URLのリスト（大きい画像 sample_l を優先）
        sample_images = []
        sample_image_data = item.get("sampleImageURL", {})
        if sample_image_data:
            sample_l = sample_image_data.get("sample_l", {})
            if sample_l:
                sample_images = sample_l.get("image", [])
            else:
                # sample_l がない場合は sample_s からURLを変換して大きい画像を推測
                sample_s = sample_image_data.get("sample_s", {})
                if sample_s:
                    small_images = sample_s.get("image", [])
                    import re as _re
                    for img in small_images:
                        large_img = _re.sub(r'(\w+)-(\d+\.jpg)$', r'\1jp-\2', img)
                        sample_images.append(large_img)

        # サンプル動画URL
        sample_movie_url = ""
        sample_movie_data = item.get("sampleMovieURL", {})
        if sample_movie_data:
            size_560 = sample_movie_data.get("size_560_360", "")
            if size_560:
                sample_movie_url = size_560

        return {
            "title": item.get("title", "タイトル不明"),
            "description": item.get("title", ""),
            "image_url": image_url,
            "affiliate_url": _build_affiliate_url(item, Config.AFFILIATE_ID),
            "price": price,
            "date": item.get("date", ""),
            "content_id": item.get("content_id", ""),
            "product_id": item.get("product_id", ""),
            "genres": genres,
            "actresses": actresses,
            "maker": item_info.get("maker", [{}])[0].get("name", "") if item_info.get("maker") else "",
            "series": item_info.get("series", [{}])[0].get("name", "") if item_info.get("series") else "",
            "sample_images": sample_images,
            "sample_movie_url": sample_movie_url,
        }
    except (KeyError, IndexError, TypeError) as e:
        print(f"[警告] 商品データのパースに失敗しました: {e}")
        return None


def fetch_multiple_keywords(
    keywords: Optional[list[str]] = None,
    hits_per_keyword: int = 3,
) -> list[dict]:
    """
    複数キーワードで商品を一括取得する

    Args:
        keywords: 検索キーワードリスト（Noneでデフォルト使用）
        hits_per_keyword: キーワードあたりの取得件数

    Returns:
        全キーワードの商品データをまとめたリスト
    """
    if keywords is None:
        keywords = Config.DEFAULT_KEYWORDS

    all_products = []
    seen_ids = set()  # 重複排除用

    for kw in keywords:
        products = fetch_products(keyword=kw, hits=hits_per_keyword)
        for p in products:
            # content_idで重複チェック
            pid = p.get("content_id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_products.append(p)

        # APIレートリミット対策（1秒待機）
        time.sleep(1)

    print(f"[合計] {len(all_products)}件のユニークな商品を取得しました")
    return all_products


if __name__ == "__main__":
    # テスト実行
    products = fetch_products(keyword="VR", hits=3)
    for p in products:
        print(f"  - {p['title']} ({p['price']})")
