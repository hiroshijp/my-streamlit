import streamlit as st
import json
from urllib import request, error

API_BASE = "https://api.github.com"

st.sidebar.header("GitHub リポジトリ検索")
# ユーザー名は指定しない（要件）。キーワードで絞る。
keyword = st.sidebar.text_input("キーワード（オプション）", value="")
top_n = st.sidebar.slider("上位 N 件（スター順）", min_value=5, max_value=50, value=10)
# 言語選択
language = st.sidebar.selectbox("言語", options=["All", "Go", "Java", "Flutter", "Elixir"], index=0)
# 検索はボタンでトリガー（初期ロードでデータを取らない）
do_search = st.sidebar.button("検索")
# 言語選択（ユーザー指定）。"All" を追加してフィルタ無しを選べるようにする。
language = st.sidebar.selectbox("言語", options=["All", "Go", "Java", "Flutter", "Elixir"], index=0)

@st.cache_data(ttl=300)
def fetch_json(url):
    req = request.Request(url, headers={"User-Agent": "streamlit-app"})
    try:
        with request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except error.HTTPError as e:
        return {"__error__": f"HTTPError: {e.code} {e.reason}"}
    except Exception as e:
        return {"__error__": str(e)}


def search_repos(keyword: str, language: str):
    """
    GitHub Search API を使ってリポジトリ検索を行う。
    - stars:>=1000 を固定条件にする
    - language が "All" の場合は言語条件を付けない
    - Flutter は GitHub 上では language='Dart' になっているため内部でマップする
    戻り値: list (items) または dict (エラー情報)
    """
    q_parts = []
    # キーワードがあれば追加（複数ワードはそのままスペースでつなげてよい）
    if keyword:
        # 検索クエリでは空白は + にエンコードされるが fetch_json の URL に渡す際に置換する
        q_parts.append(keyword)

    # 言語マッピング
    lang_map = {"Flutter": "Dart"}
    if language and language != "All":
        q_parts.append(f"language:{lang_map.get(language, language)}")

    # スター数条件（要件で固定）
    q_parts.append("stars:>=1000")

    q = "+".join([p.replace(" ", "+") for p in q_parts])
    url = f"{API_BASE}/search/repositories?q={q}&per_page=100"
    data = fetch_json(url)
    # data は dict で items を持つはず
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return data

st.markdown("## 🔎 GitHub ユーザー検索")
if not username:
    st.info("左サイドバーに GitHub のユーザー名を入力してください。")
else:
    with st.spinner("外部API（GitHub）に問い合わせ中..."):
        user = get_user(username)

    if "__error__" in user:
        st.error(f"ユーザー情報の取得に失敗しました: {user['__error__']}")
    elif user.get("message") == "Not Found":
        st.error("ユーザーが見つかりませんでした。")
    else:
        col1, col2 = st.columns([1, 3])
        with col1:
            if user.get("avatar_url"):
                st.image(user["avatar_url"], width=120)
            st.caption(f"GitHub ID: {user.get('login', '')}")
        with col2:
            st.subheader(user.get("name") or user.get("login"))
            if user.get("bio"):
                st.write(user["bio"])
            stats = {
                "フォロー中": user.get("following", 0),
                "フォロワー": user.get("followers", 0),
                "公開リポジトリ": user.get("public_repos", 0),
            }
            st.metric(label="フォロワー", value=stats["フォロワー"])
            st.write(f"会社: {user.get('company') or '－'}  ・  ロケーション: {user.get('location') or '－'}")
            if user.get("blog"):
                st.write(f"[Website]({user.get('blog')})")

        if show_repos:
            with st.spinner("リポジトリを取得しています..."):
                repos = get_repos(username)

            if isinstance(repos, dict) and "__error__" in repos:
                st.error(f"リポジトリ取得エラー: {repos['__error__']}")
            elif isinstance(repos, dict) and repos.get("message") == "Not Found":
                st.error("リポジトリが見つかりませんでした。")
            else:
                # repos はリストのはず
                repos_list = repos if isinstance(repos, list) else []
                if not repos_list:
                    st.info("公開リポジトリがありません。")
                else:
                    # 選択された言語でフィルタ（All のときはフィルタしない）
                    if language != "All":
                        # GitHub の language フィールドは Flutter の場合 'Dart' になることが多いので補正マップを用意
                        lang_map = {"Flutter": "Dart"}
                        match_lang = lang_map.get(language, language)
                        repos_list = [r for r in repos_list if (r.get("language") or "").lower() == match_lang.lower()]

                    # 要件: star数1000以上に限定
                    repos_list = [r for r in repos_list if r.get("stargazers_count", 0) >= 1000]

                    # スター順にソートして上位N件を表示
                    repos_sorted = sorted(repos_list, key=lambda r: r.get("stargazers_count", 0), reverse=True)
                    top_repos = repos_sorted[:top_n]

                    # 選択言語をサブヘッダーに表示
                    lang_label = language if language == "All" else f"{language}"
                    st.subheader(f"⭐ Top {len(top_repos)} リポジトリ（スター順・⭐>=1000） — 言語: {lang_label}")
                    for r in top_repos:
                        name = r.get("name")
                        desc = r.get("description") or ""
                        stars = r.get("stargazers_count", 0)
                        forks = r.get("forks_count", 0)
                        lang = r.get("language") or "—"
                        url = r.get("html_url")
                        updated = r.get("updated_at", "")[:10]
                        with st.expander(f"{name} — ⭐ {stars} — {lang}", expanded=False):
                            st.write(desc)
                            st.write(f"[リポジトリへ]({url})  ・  フォーク: {forks}  ・  更新: {updated}")

                    # 小さな表で簡易一覧
                    table_data = [
                        {
                            "name": f"[{r.get('name')}]({r.get('html_url')})",
                            "desc": (r.get("description") or "")[:80],
                            "stars": r.get("stargazers_count", 0),
                            "lang": r.get("language") or "—",
                        }
                        for r in top_repos
                    ]
                    st.markdown("### 簡易一覧")
                    st.table(table_data)

st.caption("データは GitHub のパブリックAPI を利用しています（レート制限あり）。")
