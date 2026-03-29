"""
メインスクリプト: 商品取得 → 記事生成 → (任意) Git push の一連のフローを実行する
"""

import argparse
import subprocess
import sys
from pathlib import Path

from config import Config
from fetch_products import fetch_products, fetch_multiple_keywords
from generate_articles import generate_articles


def parse_args() -> argparse.Namespace:
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(
        description="FANZA商品データを取得してHugoブログ記事を自動生成する",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default="",
        help="検索キーワード（未指定の場合はデフォルトキーワードを順に使用）",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="取得する商品数（デフォルト: 5）",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="生成後にgit add/commit/pushを自動実行する",
    )
    parser.add_argument(
        "--multi",
        action="store_true",
        help="全デフォルトキーワードで一括取得する",
    )
    return parser.parse_args()


def git_push(files: list[str]) -> bool:
    """
    生成した記事ファイルをGitでコミット・プッシュする

    Args:
        files: コミット対象のファイルパスリスト

    Returns:
        成功時True
    """
    if not files:
        print("[Git] コミットする記事がありません")
        return False

    project_root = Path(__file__).resolve().parent.parent

    try:
        # ファイルをステージング
        print("[Git] ファイルをステージング中...")
        subprocess.run(
            ["git", "add"] + files,
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )

        # コミット
        count = len(files)
        message = f"記事自動生成: {count}件の新規記事を追加"
        print(f"[Git] コミット中... ({message})")
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )

        # プッシュ
        print("[Git] プッシュ中...")
        result = subprocess.run(
            ["git", "push"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        print("[Git] プッシュ完了！")
        return True

    except subprocess.CalledProcessError as e:
        print(f"[Git エラー] {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        print("[Git エラー] gitコマンドが見つかりません")
        return False


def print_summary(products: list[dict], files: list[str]) -> None:
    """実行結果のサマリーを表示する"""
    print("\n" + "=" * 60)
    print("  実行結果サマリー")
    print("=" * 60)
    print(f"  取得した商品数  : {len(products)}件")
    print(f"  生成した記事数  : {len(files)}件")
    print(f"  出力先          : {Config.CONTENT_DIR}")
    print("-" * 60)

    if files:
        print("  生成されたファイル:")
        for f in files:
            print(f"    - {Path(f).name}")
    else:
        print("  ※ 新規生成された記事はありませんでした")

    print("=" * 60 + "\n")


def main() -> None:
    """メイン処理"""
    args = parse_args()

    # 設定の検証
    print("\n[開始] FANZA記事自動生成システム\n")
    if not Config.validate():
        sys.exit(1)

    # 商品データの取得
    if args.multi:
        # 全デフォルトキーワードで一括取得
        products = fetch_multiple_keywords(
            hits_per_keyword=max(1, args.count // len(Config.DEFAULT_KEYWORDS)),
        )
    else:
        # 単一キーワードで取得（フィルタリングで減る分を考慮して多めに取得）
        products = fetch_products(
            keyword=args.keyword,
            hits=min(args.count * 4, 100),
        )
        # 必要件数に絞る
        products = products[:args.count]

    if not products:
        print("[終了] 取得できた商品がないため、記事生成をスキップします")
        sys.exit(0)

    # 記事の生成
    generated_files = generate_articles(products)

    # サマリー表示
    print_summary(products, generated_files)

    # Git push（--pushオプション指定時のみ）
    if args.push and generated_files:
        print("[Git] 自動プッシュを実行します...")
        success = git_push(generated_files)
        if success:
            print("[Git] 正常に完了しました")
        else:
            print("[Git] プッシュに失敗しました。手動で確認してください")


if __name__ == "__main__":
    main()
