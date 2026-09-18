import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import random
import os
import concurrent.futures
import urllib.parse
from datetime import datetime

# 1. 대시보드 제목 세팅
st.set_page_config(page_title="REALMAN INVEST", layout="wide")

# --- 1. 밤/낮(Dark/Light) 테마 반응형 UI (CSS 변수 활용) ---
custom_css = """
<style>
    /* 기본 스트림릿 테마(Settings -> Theme)를 따라가도록 배경색 하드코딩 제거 */
    #MainMenu, footer, header {visibility: hidden;}
    
    .supreme-container { display: flex; justify-content: center; margin-top: 5px; margin-bottom: 20px; }
    .supreme-box { 
        background-color: #DA291C; color: #FFFFFF; border-radius: 2px; 
        text-align: center; font-family: 'Futura', 'Trebuchet MS', sans-serif;
        font-weight: 900; font-style: italic; text-transform: uppercase;
        box-shadow: 0 6px 12px rgba(218, 41, 28, 0.3); font-size: 36px !important; padding: 4px 20px; letter-spacing: -2px;
    }
    
    /* 📌 다크/라이트 모드에 자동 반응하는 섹션 타이틀 */
    .section-title { 
        background-color: var(--secondary-background-color); 
        color: var(--text-color); 
        border-left: 5px solid #DA291C;
        padding: 10px 16px; border-radius: 4px; 
        font-size: 17px; font-weight: 700; margin-top: 25px; margin-bottom: 15px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); letter-spacing: -0.5px;
    }
    
    .card-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    @media (min-width: 768px) { .card-grid { grid-template-columns: repeat(3, 1fr); gap: 12px; } .supreme-box { font-size: 48px !important; padding: 8px 30px; } }
    
    .card-link { text-decoration: none !important; color: inherit !important; display: block; }
    .card-link:hover .stock-card { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
    
    /* 📌 다크/라이트 모드에 자동 반응하는 카드 배경 */
    .stock-card { 
        background-color: var(--background-color); 
        border: 1px solid var(--secondary-background-color); 
        color: var(--text-color);
        border-radius: 10px; padding: 12px 14px; display: flex; justify-content: space-between; align-items: center; 
        box-shadow: 0 1px 3px rgba(0,0,0,0.05); transition: all 0.2s ease-in-out; 
    }
    .card-left { display: flex; flex-direction: column; overflow: hidden; }
    .stock-name { font-size: 14px; font-weight: 700; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
    .stock-ticker { font-size: 11px; font-weight: 500; opacity: 0.7; margin-top: 1px; }
    .card-right { display: flex; flex-direction: column; align-items: flex-end; }
    .stock-price { font-size: 14px; font-weight: 700; }
    
    .badge { font-size: 11px; font-weight: 600; margin-top: 3px; padding: 2px 6px; border-radius: 4px; color: #fff; }
    .badge-up { background-color: #ef4444; } /* 빨간색 (상승) */
    .badge-down { background-color: #3b82f6; } /* 파란색 (하락) */
    .badge-neutral { background-color: #64748B; }
    
    .news-item { 
        background-color: var(--background-color); 
        border: 1px solid var(--secondary-background-color); 
        border-radius: 6px; padding: 10px 12px; margin-bottom: 6px; font-size: 13px; font-weight: 500; 
    }
    .news-item a { color: var(--text-color); text-decoration: none; display: block; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
    .news-item a:hover { opacity: 0.7; text-decoration: underline; }
    div[role="radiogroup"] { justify-content: center; margin-bottom: 20px; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)
st.markdown('<div class="supreme-container"><div class="supreme-box">REALMAN INVEST</div></div>', unsafe_allow_html=True)

# 📌 이모티콘을 뺀 깔끔한 4섹터 네비게이션
menu = st.radio("메뉴 이동", ["시장 동향", "우량주 스크리닝", "인사이트 보드", "투자 마인드셋"], horizontal=True, label_visibility="collapsed")

# --- 2. 스크리닝 & 보조 함수 ---
DB_FILE = "market_db.csv"

def fetch_single_stock(ticker, market):
    try:
        info, hist = yf.Ticker(ticker).info, yf.Ticker(ticker).history(period="1mo")
        if hist.empty: return None
        t_eps, f_eps = info.get('trailingEps', 0), info.get('forwardEps', 0)
        return {'market': market, 'ticker': ticker, 'price': hist['Close'].iloc[-1], 'high52': info.get('fiftyTwoWeekHigh', hist['Close'].iloc[-1]), 'per': info.get('trailingPE', 0), 'pbr': info.get('priceToBook', 0), 'eps_growth': (f_eps > t_eps) and (t_eps > 0)}
    except: return None

def update_market_db():
    universe = {'NASDAQ': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO'], 'S&P 500': ['BRK-B', 'UNH', 'JNJ', 'JPM', 'V', 'PG', 'MA'], 'KOSPI': ['005930.KS', '000660.KS', '373220.KS', '207940.KS', '005380.KS']}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for f in concurrent.futures.as_completed([executor.submit(fetch_single_stock, t, m) for m, tickers in universe.items() for t in tickers]):
            if f.result(): results.append(f.result())
    pd.DataFrame(results).to_csv(DB_FILE, index=False)

def draw_stock_card(name, ticker, price, change=None, extra_info=""):
    color = "badge-up" if (change or 0) > 0 else "badge-down" if (change or 0) < 0 else "badge-neutral"
    badge = f'<div class="badge {color}">{"+" if change and change>0 else ""}{change:.2f}%</div>' if change is not None else f'<div class="badge badge-neutral">{extra_info}</div>'
    p_str = f"₩{price:,.0f}" if '.KS' in str(ticker) else f"${price:,.2f}"
    return f'<a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" class="card-link"><div class="stock-card"><div class="card-left"><div class="stock-name">{name}</div><div class="stock-ticker">{str(ticker).replace(".KS", "")}</div></div><div class="card-right"><div class="stock-price">{p_str}</div>{badge}</div></div></a>'

@st.cache_data(ttl=600)
def fetch_krx_adr():
    # 🚨 에러 원인 완벽 차단: try-except와 구조 변경 방어 로직 적용
    try:
        res = requests.get("https://finance.naver.com/sise/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        kpi_up_el = soup.select_one('#KOSPI_now ~ .siselist .up em')
        kpi_dn_el = soup.select_one('#KOSPI_now ~ .siselist .down em')
        kdq_up_el = soup.select_one('#KOSDAQ_now ~ .siselist .up em')
        kdq_dn_el = soup.select_one('#KOSDAQ_now ~ .siselist .down em')
        
        kpi_up = int(kpi_up_el.text.replace(',','')) if kpi_up_el else 0
        kpi_dn = int(kpi_dn_el.text.replace(',','')) if kpi_dn_el else 0
        kdq_up = int(kdq_up_el.text.replace(',','')) if kdq_up_el else 0
        kdq_dn = int(kdq_dn_el.text.replace(',','')) if kdq_dn_el else 0
        
        return {"KOSPI": (kpi_up, kpi_dn), "KOSDAQ": (kdq_up, kdq_dn)}
    except: 
        return {"KOSPI": (0, 0), "KOSDAQ": (0, 0)}

# 📌 트레이딩뷰 인터랙티브 위젯 렌더링 함수 (주식봇 사이트와 동일)
def render_tradingview_widget(symbol):
    html = f"""
    <div class="tradingview-widget-container" style="height:400px; width:100%;">
      <div id="tradingview_{symbol.replace(':','')}" style="height:calc(100% - 32px); width:100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
      "autosize": true,
      "symbol": "{symbol}",
      "interval": "D",
      "timezone": "Asia/Seoul",
      "theme": "dark",
      "style": "1",
      "locale": "kr",
      "enable_publishing": false,
      "backgroundColor": "rgba(0, 0, 0, 1)",
      "hide_top_toolbar": false,
      "save_image": false,
      "container_id": "tradingview_{symbol.replace(':','')}"
    }}
      );
      </script>
    </div>
    """
    components.html(html, height=400)


# ==========================================
# 📊 섹터 1: 시장 동향
# ==========================================
if menu == "시장 동향":
    st.markdown('<div class="section-title">시장 체력 (ADR) & 확대형 차트</div>', unsafe_allow_html=True)
    
    krx_adr = fetch_krx_adr()
    tab_kpi, tab_kdq, tab_ndq, tab_sp = st.tabs(["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"])
    
    def render_market_tab(market_name, tv_symbol, up_cnt, dn_cnt):
        c1, c2 = st.columns([1, 3])
        with c1:
            if up_cnt > 0 or dn_cnt > 0:
                adr_val = (up_cnt / dn_cnt * 100) if dn_cnt > 0 else 0
                st.metric(f"{market_name} 실시간 ADR", f"{adr_val:.1f}%", f"상승 {up_cnt} / 하락 {dn_cnt}")
                st.caption("ADR이 120% 이상이면 과열, 75% 이하면 바닥권(침체)을 의미합니다.")
            else:
                st.metric(f"{market_name}", "해당 지표", "실시간 장 운영 아님 / 차트 전용")
        with c2:
            # 📌 주식봇 사이트처럼 줌인/줌아웃 가능한 트레이딩뷰 위젯 띄우기
            render_tradingview_widget(tv_symbol)

    with tab_kpi: render_market_tab("KOSPI", "KRX:KOSPI", krx_adr["KOSPI"][0], krx_adr["KOSPI"][1])
    with tab_kdq: render_market_tab("KOSDAQ", "KRX:KOSDAQ", krx_adr["KOSDAQ"][0], krx_adr["KOSDAQ"][1])
    with tab_ndq: render_market_tab("NASDAQ", "NASDAQ:NDX", 0, 0)
    with tab_sp: render_market_tab("S&P 500", "SP:SPX", 0, 0)

    st.markdown('<div class="section-title">시스템 리스크 레이더</div>', unsafe_allow_html=True)
    
    risk_cols = st.columns(4)
    vix = yf.Ticker('^VIX').history(period="2d")
    vix_val, vix_chg = (vix['Close'].iloc[-1], vix['Close'].iloc[-1]-vix['Close'].iloc[-2]) if len(vix)>1 else (0,0)
    risk_cols[0].metric("VIX (월가 공포지수)", f"{vix_val:.2f}", f"{vix_chg:+.2f}", delta_color="inverse")
    
    t10 = yf.Ticker('^TNX').history(period="1d")['Close']
    t03 = yf.Ticker('^IRX').history(period="1d")['Close']
    spread = (t10.iloc[-1] - t03.iloc[-1]) if (not t10.empty and not t03.empty) else 0
    risk_cols[1].metric("장단기 금리차(10y-3m)", f"{spread:.2f}%p", "침체 경고(역전)" if spread < 0 else "정상", delta_color="off")
    
    ksp_hist = yf.Ticker('^KS11').history(period="1mo")['Close']
    ksp_disp = (ksp_hist.iloc[-1] / ksp_hist.rolling(20).mean().iloc[-1]) * 100 if len(ksp_hist)>20 else 100
    risk_cols[2].metric("KOSPI 20일 이격도", f"{ksp_disp:.1f}", "과열(105 이상)" if ksp_disp>105 else "침체(95 이하)" if ksp_disp<95 else "적정 수준", delta_color="off")
    
    fg_val, fg_txt = 0, "수집 불가"
    try:
        res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
        if res.status_code == 200: fg_val, fg_txt = round(res.json()['fear_and_greed']['score']), res.json()['fear_and_greed']['rating']
    except: pass
    risk_cols[3].metric("CNN 공탐지수", f"{fg_val}점", fg_txt, delta_color="off")

    st.markdown('<div class="section-title">주요 지수 연도별 수익률</div>', unsafe_allow_html=True)
    @st.cache_data(ttl=86400)
    def get_annual_returns():
        tkrs = {'S&P 500': '^GSPC', 'NASDAQ': '^IXIC', 'KOSPI': '^KS11'}
        res = {}
        for name, tk in tkrs.items():
            h = yf.Ticker(tk).history(period="5y")['Close']
            if not h.empty:
                yr_end = h.resample('Y').last()
                ret = yr_end.pct_change() * 100
                res[name] = ret.iloc[-4:].round(2)
        df = pd.DataFrame(res)
        df.index = df.index.year
        return df.T
    
    st.dataframe(get_annual_returns(), use_container_width=True)

# ==========================================
# 🎯 섹터 2: 우량주 스크리닝
# ==========================================
elif menu == "우량주 스크리닝":
    st.markdown('<div class="section-title">시장별 우량주 스크리닝</div>', unsafe_allow_html=True)
    if st.button("🔄 스크리닝 DB 최신화"):
        with st.spinner("병렬 스크리닝 진행 중..."): update_market_db()
        st.success("업데이트 완료!")

    if os.path.exists(DB_FILE):
        screen_data = pd.read_csv(DB_FILE).to_dict('records')
        tab1, tab2 = st.tabs(["52주 신고가", "저평가 & EPS 우상향"])

        with tab1:
            for market in ['NASDAQ', 'S&P 500', 'KOSPI']:
                st.markdown(f"<h6 style='margin-top: 15px; margin-bottom: 8px;'>{market}</h6>", unsafe_allow_html=True)
                high_stocks = [s for s in screen_data if s['market'] == market and s['price'] >= s['high52'] * 0.95]
                if high_stocks:
                    html_screen = '<div class="card-grid">'
                    for s in high_stocks: html_screen += draw_stock_card(s['ticker'], s['ticker'], s['price'], None, "신고가 근접")
                    st.markdown(html_screen + '</div>', unsafe_allow_html=True)
                else: st.caption("해당 종목 없음")
                    
        with tab2:
            st.caption("※ 조건: PER 15 미만, PBR 1.5 미만, 미래 EPS > 과거 EPS[cite: 1]")
            for market in ['NASDAQ', 'S&P 500', 'KOSPI']:
                st.markdown(f"<h6 style='margin-top: 15px; margin-bottom: 8px;'>{market}</h6>", unsafe_allow_html=True)
                val_stocks = [s for s in screen_data if s['market'] == market and 0 < s['per'] < 15 and 0 < s['pbr'] < 1.5 and s['eps_growth']]
                if val_stocks:
                    html_screen = '<div class="card-grid">'
                    for s in val_stocks: html_screen += draw_stock_card(s['ticker'], s['ticker'], s['price'], None, f"PER {s['per']:.1f}")
                    st.markdown(html_screen + '</div>', unsafe_allow_html=True)
                else: st.caption("해당 종목 없음")
    else: st.warning("☝️ [스크리닝 DB 최신화] 버튼을 먼저 눌러주세요!")

# ==========================================
# 📡 섹터 3: 인사이트 보드
# ==========================================
elif menu == "인사이트 보드":
    st.markdown('<div class="section-title">인사이트 보드</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### 거시 경제 뉴스")
        try:
            for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:5]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass
    with c2:
        st.markdown("##### 관심종목 뉴스")
        try:
            for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=애플+OR+테슬라+OR+삼성전자+OR+SK하이닉스&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:5]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass
    with c3:
        st.markdown("##### 이웃 블로그")
        for name, url in [("jeunkim", "https://rss.blog.naver.com/jeunkim"), ("crush21", "https://rss.blog.naver.com/crush212121")]:
            try:
                for item in ET.fromstring(requests.get(url).content).findall('.//item')[:3]: 
                    st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank"><b>[{name}]</b> {item.find("title").text}</a></div>', unsafe_allow_html=True)
            except: pass

# ==========================================
# 🧠 섹터 4: 투자 마인드셋
# ==========================================
elif menu == "투자 마인드셋":
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
        msg = f"**{guru['name']}**\n\n> \"{random.choice(guru['quotes'])}\"\n\n[▶️ 영상 보기]({yt})"
        cols[i].info(msg) if i % 2 == 0 else cols[i].success(msg)

    st.markdown('<div class="section-title" style="margin-top: 40px;">매수 매도 원칙</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size: 13px; color: var(--text-color); background-color: var(--secondary-background-color); padding: 16px; border-radius: 8px; line-height: 1.6;">
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