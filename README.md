# 当直スケジューラー

PuLP による最適化エンジンを使った当直スケジュール自動生成 Web アプリです。

## ファイル構成

```
duty-scheduler/
├── app.py              # Streamlit UI
├── optimizer.py        # PuLP 最適化ロジック
├── requirements.txt    # 依存ライブラリ
└── .streamlit/
    └── config.toml     # テーマ設定
```

## ローカルで起動する

```bash
# 依存ライブラリのインストール
pip install -r requirements.txt

# 起動
streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動的に開きます。

## Streamlit Cloud でデプロイする（外部公開）

1. このフォルダを GitHub リポジトリとして push する
2. https://share.streamlit.io にアクセスしてアカウント作成（無料）
3. "New app" → GitHub リポジトリを選択 → `app.py` を指定
4. "Deploy!" をクリック
5. `https://あなたのアプリ名.streamlit.app` の URL が発行される

## パスワード保護を追加する場合

`app.py` の先頭に以下を追加してください：

```python
import streamlit as st

PASSWORD = "your_password"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pw = st.text_input("パスワードを入力", type="password")
    if st.button("ログイン"):
        if pw == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()
```
