"""
設定管理モジュール
環境変数または.envファイルから設定を読み込む
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルートの.envファイルを読み込む
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
load_dotenv(_env_path)


class Config:
    """アプリケーション設定クラス"""

    # DMM API認証情報
    API_ID: str = os.getenv("API_ID", "")
    AFFILIATE_ID: str = os.getenv("AFFILIATE_ID", "")
    SITE_NAME: str = os.getenv("SITE_NAME", "vr-eros")

    # APIエンドポイント
    API_BASE_URL: str = "https://api.dmm.com/affiliate/v3/ItemList"

    # デフォルトの検索キーワード（VRジャンル）
    DEFAULT_KEYWORDS: list[str] = [
        "VR",
        "アダルトVR",
        "高画質VR",
        "8KVR",
        "VR 主観",
    ]

    # Hugo出力設定
    CONTENT_DIR: str = str(_project_root / "content" / "posts")

    # 記事生成のデフォルト設定
    DEFAULT_HITS: int = 5
    DEFAULT_SERVICE: str = "digital"
    DEFAULT_SORT: str = "date"

    @classmethod
    def validate(cls) -> bool:
        """必須設定が存在するか検証する"""
        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.AFFILIATE_ID:
            missing.append("AFFILIATE_ID")
        if missing:
            print(f"[エラー] 以下の環境変数が未設定です: {', '.join(missing)}")
            print("  .envファイルを作成するか、環境変数を設定してください。")
            print("  .env.exampleを参照してください。")
            return False
        return True
