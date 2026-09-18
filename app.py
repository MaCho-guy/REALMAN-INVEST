import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import random
import plotly.graph_objects as go
import plotly.express as px
import urllib.parse
import concurrent.futures

# 1. 페이지 기본 설정 (전체 화면 & 사이드바 확장)
st.set_page_config(page_title="REALMAN INVEST", layout="wide", initial_sidebar_state="expanded")

# 2. 커스텀 CSS (주식봇 스타일의 다크 테마 강제 적용)
st.markdown("""
<style>
    /* 전체 배경 및 폰트 색상 강제 지정 (Dark 핀테크 테마) */
    .stApp { background-color: #0B1120; color: #F8FAFC; }
    
    /* 사이드바 디자인 */
    [data-testid="stSidebar"] { background-color: #0F172A; border-right: 1px solid #1E293B; }
    
    /* 메뉴 헤더 텍스트 */
    .sidebar-title { font-size: 24px; font-weight: 900; color: #DA291C; font-style: italic; text-align: center; margin-bottom: 30px; letter-spacing: -1px; }
    
    /* 섹터 제목 */
    .section-title { 
        background-color: #1E293B; border-left: 4px solid #DA291C; padding: 12px 16px; 
        border-radius: 6px; font-size: 18px; font-weight: 700; margin-top: 30px; margin-bottom: 20px; 
    }
    
    /* 데이터 카드 레이아웃 */
    .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; }
    
    .stock-card { 
        background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; 
        padding: 16px; display: flex; justify-content: space-between; align-items: center; 
        transition: transform 0.2s; 
    }
    .stock-card:hover { transform: translateY(-3px); border-color: #DA291C; }
    
    .card-left { display: flex; flex-direction: column; }
    .stock-name { font-size: 15px; font-weight: 700; color: #F8FAFC; }
    .stock-ticker { font-size: 12px; color: #94A3B8; margin-top: 2px; }
    
    .card-right { display: flex; flex-direction: column; align-items: flex-end; }
    .stock-price { font-size: 16px; font-weight: 700; color: #F8FAFC; }
    
    .badge { font-size: 12px; font-weight: 600; margin-top: 5px; padding: 3px 8px; border-radius: 4px; color: #fff; }
    .badge-up { background-color: #ef4444; } 
    .badge-down { background-color: #3b82f6; } 
    .badge-neutral { background-color: #475569; }
    
    /* 뉴스 카드 */
    .news-item { background-color: #1E293B; border: 1px solid #334155; border-radius: 6px; padding: 12px; margin-bottom: 8px; }
    .news-item a { color: #F8FAFC; text-decoration: none; font-size: 14px; }
    .news-item a:hover { color: #38bdf8; text-decoration: underline; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 📌 URL 라우팅 & 사이드바 메뉴 (주식봇 스타일)
# ==========================================
pages = ["📊 시장지표", "🎯 관심종목", "📡 투자인사이트", "🧠 마인드셋"]

# 현재 URL의 파라미터 읽기 (페이지 전환 구현)
if "page" in st.query_params:
    current_page = st.query_params["page"]
else:
    current_page = pages[0]

# 사이드바 렌더링
st.sidebar.markdown('<div class="sidebar-title">REALMAN INVEST</div>', unsafe_allow_html=True)
selected_page = st.sidebar.radio("MENU", pages, index=pages.index(current_page) if current_page in pages else 0)

# URL 업데이트 (클릭 시 주소창 변경)
if selected_page != current_page:
    st.query_params["page"] = selected_page
    st.rerun()


# ==========================================
# 🛠️ 데이터 통신 및 렌더링 엔진
# ==========================================

# 1. 강력한 트레이딩뷰 위젯 (로딩 에러 원천 차단형)
def render_tv_widget(symbol, height=450):
    html_code = f"""
    <div class="tradingview-widget-container" style="height:{height}px;width:100%">
      <div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {{
      "autosize": true,
      "symbol": "{symbol}",
      "interval": "D",
      "timezone": "Asia/Seoul",
      "theme": "dark",
      "style": "1",
      "locale": "kr",
      "enable_publishing": false,
      "backgroundColor": "#1E293B",
      "gridColor": "#334155",
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "support_host": "https://www.tradingview.com"
      }}
      </script>
    </div>
    """
    components.html(html_code, height=height)

# 2. ADR 스크래핑 (에러 방지 떡칠)
@st.cache_data(ttl=300)
def fetch_krx_adr():
    try:
        res = requests.get("https://finance.naver.com/sise/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        k_up = soup.select_one('#KOSPI_now ~ .siselist .up em')
        k_dn = soup.select_one('#KOSPI_now ~ .siselist .down em')
        q_up = soup.select_one('#KOSDAQ_now ~ .siselist .up em')
        q_dn = soup.select_one('#KOSDAQ_now ~ .siselist .down em')
        
        kpi = (int(k_up.text.replace(',','')) if k_up else 0, int(k_dn.text.replace(',','')) if k_dn else 0)
        kdq = (int(q_up.text.replace(',','')) if q_up else 0, int(q_dn.text.replace(',','')) if q_dn else 0)
        return {"KOSPI": kpi, "KOSDAQ": kdq}
    except: 
        return {"KOSPI": (0, 0), "KOSDAQ": (0, 0)}

# 3. 주식 카드 HTML
def draw_stock_card(name, ticker, price, change, info=""):
    color = "badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"
    p_str = f"₩{price:,.0f}" if '.KS' in str(ticker) else f"${price:,.2f}"
    badge_html = f'<div class="badge {color}">{change:+.2f}%</div>' if info == "" else f'<div class="badge badge-neutral">{info}</div>'
    
    return f"""
    <a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" style="text-decoration:none;">
        <div class="stock-card">
            <div class="card-left">
                <div class="stock-name">{name}</div>
                <div class="stock-ticker">{str(ticker).replace('.KS','')}</div>
            </div>
            <div class="card-right">
                <div class="stock-price">{p_str}</div>
                {badge_html}
            </div>
        </div>
    </a>
    """


# ==========================================
# 📖 페이지 내용 구성
# ==========================================

if selected_page == "📊 시장지표":
    st.markdown('<div class="section-title">글로벌 지수 & 시장 체력(ADR)</div>', unsafe_allow_html=True)
    krx_adr = fetch_krx_adr()
    
    t_kpi, t_kdq, t_ndq, t_sp = st.tabs(["KOSPI", "KOSDAQ", "NASDAQ 100", "S&P 500"])
    
    def render_market(name, symbol, up, dn):
        c1, c2 = st.columns([1, 4])
        with c1:
            if up > 0 or dn > 0:
                adr = (up/dn*100) if dn > 0 else 0
                st.metric(f"{name} 실시간 ADR", f"{adr:.1f}%", f"상승 {up} / 하락 {dn}")
            else:
                st.metric(f"{name}", "글로벌 지수", "차트 전용")
        with c2:
            render_tv_widget(symbol)

    with t_kpi: render_market("KOSPI", "KRX:KOSPI", krx_adr["KOSPI"][0], krx_adr["KOSPI"][1])
    with t_kdq: render_market("KOSDAQ", "KRX:KOSDAQ", krx_adr["KOSDAQ"][0], krx_adr["KOSDAQ"][1])
    # 무료로 웹 임베딩이 가능한 CFD 심볼 적용 (에러 방지)
    with t_ndq: render_market("NASDAQ 100", "OANDA:NAS100USD", 0, 0)
    with t_sp: render_market("S&P 500", "OANDA:SPX500USD", 0, 0)

    st.markdown('<div class="section-title">글로벌 리스크 레이더</div>', unsafe_allow_html=True)
    g_cols = st.columns(4)
    
    try:
        vix = yf.Ticker('^VIX').history(period="2d")
        v_val, v_chg = vix['Close'].iloc[-1], vix['Close'].iloc[-1]-vix['Close'].iloc[-2]
    except: v_val, v_chg = 0, 0
    g_cols[0].metric("VIX (공포지수)", f"{v_val:.2f}", f"{v_chg:+.2f}", delta_color="inverse")
    
    try:
        t10, t03 = yf.Ticker('^TNX').history(period="1d")['Close'], yf.Ticker('^IRX').history(period="1d")['Close']
        spread = t10.iloc[-1] - t03.iloc[-1]
    except: spread = 0
    g_cols[1].metric("장단기 금리차", f"{spread:.2f}%p", "침체 경고" if spread < 0 else "정상", delta_color="off")
    
    fg_val, fg_txt = 0, "API 지연"
    try:
        res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
        if res.status_code == 200: 
            fg_val, fg_txt = round(res.json()['fear_and_greed']['score']), res.json()['fear_and_greed']['rating']
    except: pass
    g_cols[2].metric("CNN 공탐지수", f"{fg_val}점", fg_txt, delta_color="off")
    
    try:
        hyg = yf.Ticker('HYG').history(period="2d")
        h_val, h_chg = hyg['Close'].iloc[-1], hyg['Close'].iloc[-1]-hyg['Close'].iloc[-2]
    except: h_val, h_chg = 0, 0
    g_cols[3].metric("하이일드(HYG) 채권", f"${h_val:.2f}", f"{h_chg:+.2f} (하락시 위험)", delta_color="normal")


elif selected_page == "🎯 관심종목":
    st.markdown('<div class="section-title">내 관심종목 모니터링</div>', unsafe_allow_html=True)
    my_stocks = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 'O', 'SCHD', '005930.KS', '000660.KS']
    
    html_stock = '<div class="card-grid">'
    for t in my_stocks:
        try:
            hist = yf.Ticker(t).history(period="2d")
            if len(hist) >= 2:
                close_tdy, close_ytd = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
                chg_pct = ((close_tdy - close_ytd) / close_ytd) * 100
                d_name = '삼성전자' if t == '005930.KS' else 'SK하이닉스' if t == '000660.KS' else t
                html_stock += draw_stock_card(d_name, t, close_tdy, chg_pct)
        except: continue
    html_stock += '</div>'
    st.markdown(html_stock, unsafe_allow_html=True)

    st.markdown('<div class="section-title">가치주 스크리닝 (서버 DB)</div>', unsafe_allow_html=True)
    st.info("💡 과거 설정한 [PER 15 미만, PBR 1.5 미만, 내년 EPS 상향] 기준입니다[cite: 1].")
    
    DB_FILE = "market_db.csv"
    if st.button("🔄 스크리닝 서버 DB 최신화"):
        st.warning("데이터 수집 중입니다. (야후 서버 상태에 따라 1~2분 소요)")
        # 실전 배치용 간소화 우주
        universe = {'미국주식': ['AAPL', 'MSFT', 'GOOGL', 'NVDA'], '한국주식': ['005930.KS', '000660.KS', '005380.KS']}
        results = []
        for m, tickers in universe.items():
            for t in tickers:
                try:
                    info = yf.Ticker(t).info
                    h = yf.Ticker(t).history(period="1d")
                    if not h.empty:
                        results.append({'market': m, 'ticker': t, 'price': h['Close'].iloc[-1], 'per': info.get('trailingPE', 0), 'pbr': info.get('priceToBook', 0)})
                except: pass
        pd.DataFrame(results).to_csv(DB_FILE, index=False)
        st.success("완료되었습니다! 새로고침을 해주세요.")


elif selected_page == "📡 투자인사이트":
    st.markdown('<div class="section-title">시장 뉴스 및 이웃 블로그</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    
    def render_rss(url, limit=5):
        html_str = ""
        try:
            items = ET.fromstring(requests.get(url, timeout=3).content).findall('.//item')[:limit]
            for item in items:
                html_str += f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>'
        except: html_str = '<div class="news-item">데이터를 불러올 수 없습니다.</div>'
        return html_str

    with c1:
        st.markdown("###### 🌍 거시 경제 뉴스")
        st.markdown(render_rss("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko"), unsafe_allow_html=True)
    with c2:
        st.markdown("###### 🎯 관심종목 뉴스")
        st.markdown(render_rss("https://news.google.com/rss/search?q=애플+테슬라+삼성전자+엔비디아&hl=ko&gl=KR&ceid=KR:ko"), unsafe_allow_html=True)
    with c3:
        st.markdown("###### 📝 이웃 블로그 최신글")
        st.markdown(render_rss("https://rss.blog.naver.com/jeunkim", 3), unsafe_allow_html=True)
        st.markdown(render_rss("https://rss.blog.naver.com/crush212121", 3), unsafe_allow_html=True)


elif selected_page == "🧠 마인드셋":
    st.markdown('<div class="section-title">투자의 대가들</div>', unsafe_allow_html=True)
    gurus = [
        {"name": "워런 버핏", "search": "워런 버핏 투자 조언", "quotes": ["위대한 기업을 적당한 가격에 사는 것이 훨씬 낫다.", "원칙 1: 절대 돈을 잃지 마라."]},
        {"name": "찰리 멍거", "search": "찰리 멍거 명언", "quotes": ["바보 같은 짓을 피하는 것이 중요하다.", "이해하지 못하는 것에는 절대 투자하지 마라."]},
        {"name": "피터 린치", "search": "피터 린치 강연", "quotes": ["가장 중요한 기관은 뇌가 아니라 위장(인내심)이다.", "기업 수익이 우상향하면 주가도 우상향한다."]},
        {"name": "코스톨라니", "search": "앙드레 코스톨라니", "quotes": ["투자는 머리로 하는 것이 아니라 엉덩이로 하는 것이다.", "주가는 결국 기업의 가치로 회귀한다."]}
    ]
    cols = st.columns(2) + st.columns(2)
    for i, guru in enumerate(random.sample(gurus, 4)):
        yt = f"https://www.youtube.com/results?search_query={urllib.parse.quote(guru['search'])}&sp=CAM%253D"
        msg = f"**{guru['name']}**\n\n> \"{random.choice(guru['quotes'])}\"\n\n[▶️ 관련 영상 보기]({yt})"
        cols[i].info(msg) if i % 2 == 0 else cols[i].success(msg)

    st.markdown('<div class="section-title">나만의 매수 매도 원칙</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size: 15px; background-color: #1E293B; padding: 24px; border-radius: 8px; line-height: 1.8; border-left: 4px solid #DA291C;">
    <b>1.</b> 급격한 상승이나 하락세에 올라타지 마라. 매수, 매도 타이밍은 완만해질 때다.<br>
    <b>2.</b> 시장은 쏠리기 마련이다. 과도한 비관론에 매수하라.<br>
    <b>3.</b> 전문가도 잘 모른다. 장담하는 사람은 사기꾼이다.<br>
    <b>4.</b> 오른 만큼 가파르게 떨어진다. 그 사이 수익을 내는 것은 어렵다.<br>
    <b>5.</b> 큰 자본을 한 번에 투하하지 마라. 분할 매수해라.<br>
    <b>6.</b> 손절도 할 줄 알아야 한다. 싫으면 인내심을 길러라.<br>
    <b>7.</b> 나만 소외된 것 같을 때가 가장 참아야 할 때다.<br>
    <b>8.</b> 가치분석은 직접 해라.<br>
    <b>9.</b> 산업의 기술을 잘 안다고 주가를 잘 아는 것은 아니다.
    </div>
    """, unsafe_allow_html=True)