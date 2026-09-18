import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import random
import os
import concurrent.futures

# 1. 대시보드 제목 세팅 (반드시 최상단)
st.set_page_config(page_title="REALMAN INVEST", layout="wide")

# --- 2. 다크/라이트 모드 토글 (우측 상단 배치) ---
col_logo, col_toggle = st.columns([8, 2])
with col_toggle:
    st.write("") # 수직 정렬용 여백
    is_dark = st.toggle("🌙 다크 모드", value=True)

# 테마 상태에 따른 CSS 변수 동적 할당
bg_grad = "linear-gradient(135deg, #0F172A 0%, #1E293B 100%)" if is_dark else "linear-gradient(135deg, #F1F5F9 0%, #E2E8F0 100%)"
card_bg = "#1E293B" if is_dark else "#FFFFFF"
text_col = "#F8FAFC" if is_dark else "#0F172A"
sub_text = "#94A3B8" if is_dark else "#64748B"
border_col = "#334155" if is_dark else "#CBD5E1"
sec_bg = "#0F172A" if is_dark else "#1E293B"

custom_css = f"""
<style>
    .stApp {{ background: {bg_grad}; color: {text_col}; }}
    #MainMenu, footer, header {{visibility: hidden;}}
    
    .supreme-container {{ display: flex; justify-content: center; margin-bottom: 25px; }}
    .supreme-box {{ 
        background-color: #DA291C; color: #FFFFFF; border-radius: 2px; 
        text-align: center; font-family: 'Futura', 'Trebuchet MS', sans-serif;
        font-weight: 900; font-style: italic; text-transform: uppercase;
        box-shadow: 0 6px 12px rgba(218, 41, 28, 0.3); font-size: 38px !important; padding: 4px 24px; letter-spacing: -2px;
    }}
    
    /* 섹터 소제목 스타일 */
    .section-title {{ 
        background-color: {sec_bg}; color: #FFFFFF; border-left: 5px solid #DA291C;
        padding: 10px 16px; border-radius: 4px; font-size: 18px; font-weight: 700; 
        margin-top: 30px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
    }}
    
    .card-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    @media (min-width: 768px) {{ .card-grid {{ grid-template-columns: repeat(3, 1fr); gap: 12px; }} }}
    
    .stock-card {{ 
        background-color: {card_bg}; border: 1px solid {border_col}; color: {text_col};
        border-radius: 10px; padding: 12px 14px; display: flex; justify-content: space-between; align-items: center; 
    }}
    .card-left {{ display: flex; flex-direction: column; overflow: hidden; }}
    .stock-name {{ font-size: 14px; font-weight: 700; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }}
    .stock-ticker {{ font-size: 11px; font-weight: 500; color: {sub_text}; margin-top: 2px; }}
    .stock-price {{ font-size: 14px; font-weight: 700; }}
    
    .badge {{ font-size: 11px; font-weight: 600; margin-top: 3px; padding: 3px 6px; border-radius: 4px; color: #fff; }}
    .badge-up {{ background-color: #ef4444; }} 
    .badge-down {{ background-color: #3b82f6; }} 
    .badge-neutral {{ background-color: #64748B; }}
    
    .news-item {{ background-color: {card_bg}; border: 1px solid {border_col}; border-radius: 6px; padding: 10px 12px; margin-bottom: 6px; font-size: 13px; font-weight: 500; }}
    .news-item a {{ color: {text_col}; text-decoration: none; display: block; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }}
    .news-item a:hover {{ text-decoration: underline; opacity: 0.8; }}
    
    div[role="radiogroup"] {{ justify-content: center; margin-bottom: 20px; }}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

with col_logo:
    st.markdown('<div class="supreme-container"><div class="supreme-box">REALMAN INVEST</div></div>', unsafe_allow_html=True)

# 📌 4섹터 메뉴 (이모티콘 제거)
menu = st.radio("메뉴 이동", ["시장지표", "우량주 스크리닝", "인사이트 보드", "매수 매도 원칙"], horizontal=True, label_visibility="collapsed")

# --- 데이터 통신 함수 모음 ---
DB_FILE = "market_db.csv"

def fetch_single_stock(ticker, market):
    try:
        info = yf.Ticker(ticker).info
        hist = yf.Ticker(ticker).history(period="1mo")
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
    return f'<a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" style="text-decoration:none;"><div class="stock-card"><div class="card-left"><div class="stock-name">{name}</div><div class="stock-ticker">{str(ticker).replace(".KS", "")}</div></div><div class="card-right"><div class="stock-price">{p_str}</div>{badge}</div></div></a>'

@st.cache_data(ttl=300)
def fetch_krx_adr():
    try:
        res = requests.get("https://finance.naver.com/sise/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        k_up = soup.select_one('#KOSPI_now ~ .siselist .up em')
        k_dn = soup.select_one('#KOSPI_now ~ .siselist .down em')
        q_up = soup.select_one('#KOSDAQ_now ~ .siselist .up em')
        q_dn = soup.select_one('#KOSDAQ_now ~ .siselist .down em')
        return {
            "KOSPI": (int(k_up.text.replace(',','')) if k_up else 0, int(k_dn.text.replace(',','')) if k_dn else 0),
            "KOSDAQ": (int(q_up.text.replace(',','')) if q_up else 0, int(q_dn.text.replace(',','')) if q_dn else 0)
        }
    except: return {"KOSPI": (0, 0), "KOSDAQ": (0, 0)}

@st.cache_data(ttl=86400)
def get_annual_returns():
    tkrs = {'S&P 500': '^GSPC', 'NASDAQ': '^IXIC', 'KOSPI': '^KS11'}
    res = {}
    for name, tk in tkrs.items():
        h = yf.Ticker(tk).history(period="5y")['Close']
        if not h.empty:
            res[name] = (h.resample('YE').last().pct_change() * 100).iloc[-4:].round(2)
    df = pd.DataFrame(res)
    df.index = df.index.year
    return df


# ==========================================
# 📊 섹터 1: 시장지표
# ==========================================
if menu == "시장지표":
    
    # 📌 소제목 1: ADR
    st.markdown('<div class="section-title">ADR (시장 체력)</div>', unsafe_allow_html=True)
    krx_adr = fetch_krx_adr()
    c1, c2 = st.columns(2)
    with c1:
        up, dn = krx_adr["KOSPI"]
        st.metric("KOSPI 실시간 ADR", f"{(up/dn*100):.1f}%" if dn > 0 else "집계중", f"상승 {up} / 하락 {dn}")
    with c2:
        up, dn = krx_adr["KOSDAQ"]
        st.metric("KOSDAQ 실시간 ADR", f"{(up/dn*100):.1f}%" if dn > 0 else "집계중", f"상승 {up} / 하락 {dn}")
    st.caption("※ ADR이 120% 이상이면 과열, 75% 이하면 바닥권(침체)을 의미합니다.")

    # 📌 소제목 2: 위험지표
    st.markdown('<div class="section-title">위험지표</div>', unsafe_allow_html=True)
    
    st.markdown("###### 📉 KOSPI / KOSDAQ 20일 이격도 (차트 확대/축소 지원)")
    # 기간 선택 버튼 (라디오)
    period_map = {'25일': '1mo', '50일': '2mo', '6M': '6mo', '1Y': '1y', '3Y': '3y'}
    sel_p = st.radio("기간 선택", list(period_map.keys()), horizontal=True, label_visibility="collapsed")
    
    try:
        h_kpi = yf.Ticker('^KS11').history(period=period_map[sel_p])['Close']
        h_kdq = yf.Ticker('^KQ11').history(period=period_map[sel_p])['Close']
        disp_kpi = (h_kpi / h_kpi.rolling(20).mean() * 100).dropna()
        disp_kdq = (h_kdq / h_kdq.rolling(20).mean() * 100).dropna()
        df_disp = pd.DataFrame({'KOSPI 이격도': disp_kpi, 'KOSDAQ 이격도': disp_kdq})
        st.line_chart(df_disp, height=250)
    except:
        st.error("차트 데이터를 불러오는 중 오류가 발생했습니다.")

    st.divider()
    
    st.markdown("###### 🌍 글로벌 리스크 지표")
    g_cols = st.columns(4)
    # VIX
    vix = yf.Ticker('^VIX').history(period="2d")
    v_val, v_chg = (vix['Close'].iloc[-1], vix['Close'].iloc[-1]-vix['Close'].iloc[-2]) if len(vix)>1 else (0,0)
    g_cols[0].metric("VIX (공포지수)", f"{v_val:.2f}", f"{v_chg:+.2f}", delta_color="inverse")
    
    # 장단기 금리차
    t10 = yf.Ticker('^TNX').history(period="1d")['Close']
    t03 = yf.Ticker('^IRX').history(period="1d")['Close']
    spread = (t10.iloc[-1] - t03.iloc[-1]) if (not t10.empty and not t03.empty) else 0
    g_cols[1].metric("장단기 금리차(10y-3m)", f"{spread:.2f}%p", "침체 경고" if spread < 0 else "정상", delta_color="off")
    
    # CNN 공탐지수 (안전한 스크래핑 헤더 적용)
    fg_val, fg_txt = 0, "수집 불가"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36', 'Accept': 'application/json'}
        res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers=headers, timeout=3)
        if res.status_code == 200: fg_val, fg_txt = round(res.json()['fear_and_greed']['score']), res.json()['fear_and_greed']['rating']
    except: pass
    g_cols[2].metric("CNN 공탐지수", f"{fg_val}점", fg_txt, delta_color="off")
    
    # 하이일드 스프레드 (HYG)
    hyg = yf.Ticker('HYG').history(period="2d")
    h_val, h_chg = (hyg['Close'].iloc[-1], hyg['Close'].iloc[-1]-hyg['Close'].iloc[-2]) if len(hyg)>1 else (0,0)
    g_cols[3].metric("하이일드(HYG) 채권", f"${h_val:.2f}", f"{h_chg:+.2f} (하락시 위험)", delta_color="normal")

    st.divider()

    st.markdown("###### 🇰🇷 한국 리스크 지표 차트 (최근 6개월)")
    k_cols = st.columns(2)
    with k_cols[0]:
        st.caption("VKOSPI (한국 코스피 변동성 지수)")
        vkospi = yf.Ticker('^VKOSPI').history(period="6mo")['Close']
        st.line_chart(vkospi, height=200)
    with k_cols[1]:
        st.caption("KOSPI 신고가-신저가 프록시 (52주 밴드 내 현재 위치 %)")
        ksp_1y = yf.Ticker('^KS11').history(period="1y")['Close']
        h52 = ksp_1y.rolling(252).max().dropna()
        l52 = ksp_1y.rolling(252).min().dropna()
        cls = ksp_1y.loc[h52.index]
        nh_nl = (cls - l52) / (h52 - l52) * 100
        st.line_chart(nh_nl.tail(120), height=200) # 6개월 분량만 렌더링

    # 📌 소제목 3: 주요지수 연도별 수익률 (막대 차트)
    st.markdown('<div class="section-title">주요지수 연도별 수익률</div>', unsafe_allow_html=True)
    df_ret = get_annual_returns()
    st.bar_chart(df_ret, height=300)
    st.caption("※ 단위: %, 각 연도 말 기준 상승/하락률 (마우스 오버 시 상세 수치 확인 가능)")


# ==========================================
# 🎯 섹터 2: 우량주 스크리닝
# ==========================================
elif menu == "우량주 스크리닝":
    st.markdown('<div class="section-title">우량주 스크리닝</div>', unsafe_allow_html=True)
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
            st.caption("※ 조건: PER 15 미만, PBR 1.5 미만, 미래 EPS > 과거 EPS")
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
# 🧠 섹터 4: 매수 매도 원칙
# ==========================================
elif menu == "매수 매도 원칙":
    st.markdown('<div class="section-title">투자의 대가들</div>', unsafe_allow_html=True)
    gurus = [
        {"name": "워런 버핏", "search": "워런 버핏 투자 조언", "quotes": ["위대한 기업을 적당한 가격에 사는 것이 훨씬 낫다.", "원칙 1: 절대 돈을 잃지 마라."]},
        {"name": "찰리 멍거", "search": "찰리 멍거 명언", "quotes": ["바보 같은 짓을 피하는 것이 중요하다.", "이해하지 못하는 것에는 절대 투자하지 마라."]},
        {"name": "피터 린치", "search": "피터 린치 강연", "quotes": ["가장 중요한 기관은 뇌가 아니라 위장(인내심)이다.", "기업 수익이 우상향하면 주가도 우상향한다."]},
        {"name": "코스톨라니", "search": "앙드레 코스톨라니", "quotes": ["투자는 머리로 하는 것이 아니라 엉덩이로 하는 것이다.", "주가는 결국 기업의 가치로 회귀한다."]}
    ]
    cols = st.columns(2) + st.columns(2)
    import urllib.parse
    for i, guru in enumerate(random.sample(gurus, 4)):
        yt = f"https://www.youtube.com/results?search_query={urllib.parse.quote(guru['search'])}&sp=CAM%253D"
        msg = f"**{guru['name']}**\n\n> \"{random.choice(guru['quotes'])}\"\n\n[▶️ 영상 보기]({yt})"
        cols[i].info(msg) if i % 2 == 0 else cols[i].success(msg)

    st.markdown('<div class="section-title" style="margin-top: 40px;">매수 매도 원칙</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size: 13px; color: {text_col}; background-color: {sec_bg}; padding: 16px; border-radius: 8px; line-height: 1.6;">
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