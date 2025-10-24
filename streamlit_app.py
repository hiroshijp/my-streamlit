import streamlit as st
import json
from urllib import request, error
import pandas as pd
from collections import Counter
from datetime import datetime, timedelta

# ページタイトルを設定
st.set_page_config(page_title="俺得GitHub検索ツール")

API_BASE = "https://api.github.com"

# サイドバー見出しをアプリタイトルに変更
st.sidebar.header("俺得GitHub検索ツール")
# ユーザー名は指定しない（要件）。キーワードで絞る。
keyword = st.sidebar.text_input("キーワード（オプション）", value="")
top_n = st.sidebar.slider("上位 N 件（スター順）", min_value=5, max_value=30, value=10)
# 言語選択
language = st.sidebar.selectbox("言語", options=["All", "Go", "Java", "Flutter", "Elixir"], index=0)
# 検索はボタンでトリガー（初期ロードでデータを取らない）
do_search = st.sidebar.button("検索")

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


@st.cache_data(ttl=3600)
def fetch_json_with_headers(url, headers=None):
    req = request.Request(url, headers=headers or {"User-Agent": "streamlit-app"})
    try:
        with request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except error.HTTPError as e:
        return {"__error__": f"HTTPError: {e.code} {e.reason}"}
    except Exception as e:
        return {"__error__": str(e)}


@st.cache_data(ttl=3600)
def get_stargazer_dates(full_name: str, max_pages: int = 10):
    """指定リポジトリの stargazers を取得し、starred_at の日付リストを返す。
    max_pages * 100 件を上限とする（デフォルト1000件）。
    使用する Accept ヘッダー: application/vnd.github.v3.star+json
    戻り値: dict -> {"dates": [...], "truncated": bool} またはエラー dict
    """
    owner_repo = full_name
    headers = {"User-Agent": "streamlit-app", "Accept": "application/vnd.github.v3.star+json"}
    starred_dates = []
    for page in range(1, max_pages + 1):
        url = f"{API_BASE}/repos/{owner_repo}/stargazers?per_page=100&page={page}"
        data = fetch_json_with_headers(url, headers=headers)
        if isinstance(data, dict) and "__error__" in data:
            return data
        if not isinstance(data, list):
            break
        if not data:
            break
        for item in data:
            # each item has 'starred_at' and 'user' when using the star+json media type
            sa = item.get("starred_at")
            if sa:
                # normalize to date
                try:
                    d = datetime.fromisoformat(sa.replace("Z", "+00:00")).date()
                    starred_dates.append(d.isoformat())
                except Exception:
                    continue
    truncated = False
    # If we hit max_pages and last page was full, consider truncated
    if len(starred_dates) >= max_pages * 100:
        truncated = True
    return {"dates": starred_dates, "truncated": truncated}

st.markdown("## 俺得GitHub検索ツール")

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

        # サイドバーに選択用のリストを表示（トップ結果から選べる）
        repo_options = [r.get("full_name") or r.get("name") for r in top_repos]
        if repo_options:
            selected_repo = st.sidebar.selectbox("対象リポジトリ（グラフ化）", options=repo_options, key="selected_repo")
            show_chart = st.sidebar.button("スター推移を表示", key="show_chart")
        else:
            selected_repo = None
            show_chart = False

        st.subheader(f"⭐ Top {len(top_repos)} リポジトリ（スター順・⭐>=1000）")
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

        # スター推移グラフの表示
        if selected_repo and show_chart:
            with st.spinner("スター推移データを取得しています（最大1000件）..."):
                sg = get_stargazer_dates(selected_repo, max_pages=10)
                if isinstance(sg, dict) and "__error__" in sg:
                    st.error(f"データ取得エラー: {sg['__error__']}")
                elif isinstance(sg, dict) and "dates" in sg:
                    dates = sg.get("dates", [])
                    if not dates:
                        st.info("スター履歴が取得できませんでした（非公開またはデータ不足）。")
                    else:
                        # 過去5年を横軸にする（約5*365日）
                        today = datetime.utcnow().date()
                        cutoff = today - timedelta(days=5 * 365)

                        # 日付ごとのカウント
                        cnt = Counter(dates)

                        # 総数のうち、cutoff より前のスターを初期値として計上
                        total_before = 0
                        for dstr, v in cnt.items():
                            try:
                                d = datetime.fromisoformat(dstr).date()
                            except Exception:
                                continue
                            if d < cutoff:
                                total_before += v

                        # 日次で累積を作る（cutoff から today までの連続日付）
                        days = [(cutoff + timedelta(days=i)) for i in range((today - cutoff).days + 1)]
                        cum_values = []
                        total = total_before
                        for day in days:
                            day_str = day.isoformat()
                            total += cnt.get(day_str, 0)
                            cum_values.append({"date": day, "stars": total})

                        df = pd.DataFrame(cum_values).set_index(pd.DatetimeIndex([r["date"] for r in cum_values]))
                        df.index.name = None

                        # 取得が途中で切れている（truncated）場合、表示が最大取得件数で平坦化することがある。
                        # そのため、可能であればトップリポジトリ情報から実際のスター数を取得して最終値に反映する。
                        if sg.get("truncated"):
                            # top_repos がスコープ内にあるはずなので、selected_repo 名で該当オブジェクトを探す
                            repo_obj = None
                            try:
                                repo_obj = next((x for x in top_repos if (x.get("full_name") or x.get("name")) == selected_repo), None)
                            except Exception:
                                repo_obj = None

                            if repo_obj:
                                actual_total = repo_obj.get("stargazers_count") or None
                                if actual_total and actual_total > int(df["stars"].iloc[-1]):
                                    # 最終日の値を実際のスター数に合わせる
                                    df.at[df.index[-1], "stars"] = actual_total
                            st.warning("注: 取得上限に達したため一部データのみを使用しています（最大1000件）。")

                        st.line_chart(df["stars"])

st.caption("データは GitHub のパブリックAPI を利用しています（レート制限あり）。")
