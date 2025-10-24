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

st.markdown("## 🔎 GitHub リポジトリ検索")

# 検索はボタンでトリガーする。検索結果は session_state に保持する。
if 'search_results' not in st.session_state:
    st.session_state['search_results'] = None
    st.session_state['search_error'] = None

if do_search:
    with st.spinner("GitHub を検索しています...（スター数>=1000）"):
        results = search_repos(keyword.strip(), language)
    if isinstance(results, dict) and "__error__" in results:
        st.error(f"検索中にエラーが発生しました: {results['__error__']}")
        st.session_state['search_results'] = []
        st.session_state['search_error'] = results['__error__']
    elif isinstance(results, dict) and results.get("message"):
        st.error(f"検索エラー: {results.get('message')}")
        st.session_state['search_results'] = []
        st.session_state['search_error'] = results.get('message')
    else:
        st.session_state['search_results'] = results
        st.session_state['search_error'] = None

if not st.session_state.get('search_results'):
    st.info("左サイドバーで条件を指定して「検索」ボタンを押してください（初回ロードではデータを取得しません）。")
else:
    repos_list = st.session_state['search_results']
    if not repos_list:
        st.info("検索結果がありません。条件を変えて再検索してください。")
    else:
        # Search API already constrained stars>=1000; 並び替えて上位N件を表示
        repos_sorted = sorted(repos_list, key=lambda r: r.get("stargazers_count", 0), reverse=True)
        top_repos = repos_sorted[:top_n]

        lang_label = language if language == "All" else language
        st.subheader(f"⭐ Top {len(top_repos)} リポジトリ（スター順・⭐>=1000） — 言語: {lang_label} — キーワード: {keyword or '（なし）'}")
        for r in top_repos:
            name = r.get("full_name") or r.get("name")
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
                "name": f"[{r.get('full_name') or r.get('name')}]({r.get('html_url')})",
                "desc": (r.get("description") or "")[:80],
                "stars": r.get("stargazers_count", 0),
                "lang": r.get("language") or "—",
            }
            for r in top_repos
        ]
        st.markdown("### 簡易一覧")
        st.table(table_data)

st.caption("データは GitHub のパブリックAPI を利用しています（レート制限あり）。")
