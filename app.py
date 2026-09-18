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
import time

# 1. 페이지 세팅
st.set_page_config(page_title="REALMAN INVEST", layout="wide", initial_sidebar_state="collapsed")

# --- 2. 다크/라이트 테마 엔진 ---
col_logo, col_toggle = st.columns([8, 2])
with col_toggle:
    st.write("") 
    is_dark = st.toggle("🌙 다크 모드", value=True)

# 테마 색상 변수 설정
bg_color = "#0F172A" if is_dark else "#F8FAFC"
card_bg = "#1E293B" if is_dark else "#FFFFFF"
text_col = "#F8FAFC" if is_dark else "#0F172A"
sub_text = "#94A3B8" if is_dark else "#64748B"
border_col = "#334155" if is_dark else "#E2E8F0"
chart_template = "plotly_dark" if is_dark else "plotly_white"
tv_theme = "dark" if is_dark else "light"

custom_css = f"""
<style>
    .stApp {{ background-color: {bg_color}; color: {text_col}; }}
    #MainMenu, footer, header {{visibility: hidden;}}
    
    .supreme-container {{ display: flex; justify-content: center; margin-bottom: 25px; }}
    .supreme-box {{ 
        background-color: #DA291C; color: #FFFFFF; border-radius: 2px; 
        text-align: center; font-family: 'Futura', sans-serif;
        font-weight: 900; font-style: italic; text-transform: uppercase;
        box-shadow: 0 4px 10px rgba(218, 41, 28, 0.3); font-size: 34px !important; padding: 4px 20px; letter-spacing: -2px;
    }}
    
    .section-title {{ 
        background-color: {card_bg}; color: {text_col}; border-left: 4px solid #DA291C;
        padding: 8px 16px; border-radius: 4px; font-size: 17px; font-weight: 700; 
        margin-top: 30px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); 
    }}
    
    .stock-card {{ 
        background-color: {card_bg}; border: 1px solid {border_col}; color: {text_col};
        border-radius: 8px; padding: 12px; display: flex; justify-content: space-between; align-items: center; 
        box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 10px;
    }}
    .card-left {{ display: flex; flex-direction: column; }}
    .stock-name {{ font-size: 14px; font-weight: 700; }}
    .stock-ticker {{ font-size: 11px; color: {sub_text}; margin-top: 2px; }}
    .card-right {{ display: flex; flex-direction: column; align-items: flex-end; }}
    .stock-price {{ font-size: 14px; font-weight: 700; }}
    
    .badge {{ font-size: 11px; font-weight: 600; margin-top: 4px; padding: 2px 6px; border-radius: 4px; color: #fff; }}
    .badge-up {{ background-color: #ef4444; }} 
    .badge-down {{ background-color: #3b82f6; }} 
    .badge-neutral {{ background-color: #64748B; }}
    
    .news-item {{ background-color: {card_bg}; border: 1px solid {border_col}; border-radius: 6px; padding: 10px; margin-bottom: 8px; font-size: 13px; }}
    .news-item a {{ color: {text_col}; text-decoration: none; }}
    .news-item a:hover {{ text-decoration: underline; opacity: 0.8; }}
    
    /* 탭 메뉴 스타일링 (Jusikbot 스타일) */
    div[role="tablist"] {{ gap: 15px; border-bottom: 1px solid {border_col}; }}
    button[role="tab"] {{ font-size: 16px !important; font-weight: 600 !important; color: {sub_text} !important; }}
    button[role="tab"][aria-selected="true"] {{ color: {text_col} !important; border-bottom-color: #DA291C !important; }}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

with col_logo:
    st.markdown('<div class="supreme-container"><div class="supreme-box">REALMAN INVEST</div></div>', unsafe_allow_html=True)

# 📌 4섹터 메인 탭
tab_market, tab_watchlist, tab_insight, tab_mind = st.tabs(["📊 시장지표", "🎯 관심종목", "📡 투자인사이트", "🧠 마인드셋"])

# --- 통신 및 렌더링 함수 ---
@st.cache_data(ttl=300)
def fetch_krx_adr():
    try:
        res = requests.get("https://finance.naver.com/sise/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        k_up, k_dn = soup.select_one('#KOSPI_now ~ .siselist .up em'), soup.select_one('#KOSPI_now ~ .siselist .down em')
        q_up, q_dn = soup.select_one('#KOSDAQ_now ~ .siselist .up em'), soup.select_one('#KOSDAQ_now ~ .siselist .down em')
        return {
            "KOSPI": (int(k_up.text.replace(',','')) if k_up else 0, int(k_dn.text.replace(',','')) if k_dn else 0),
            "KOSDAQ": (int(q_up.text.replace(',','')) if q_up else 0, int(q_dn.text.replace(',','')) if q_dn else 0)
        }
    except: return {"KOSPI": (0, 0), "KOSDAQ": (0, 0)}

# 🚨 트레이딩뷰 위젯 로딩 오류 해결을 위한 안정화 코드
def render_tv_widget(symbol, height=400):
    unique_id = f"tv_{symbol.replace(':', '')}_{int(time.time())}"
    html = f"""
    <div class="tradingview-widget-container" style="height:{height}px; width:100%; position:relative;">
      <div id="{unique_id}" style="position:absolute; top:0; left:0; right:0; bottom:0;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
      "autosize": true, "symbol": "{symbol}", "interval": "D", "timezone": "Asia/Seoul",
      "theme": "{tv_theme}", "style": "1", "locale": "kr", "enable_publishing": false,
      "backgroundColor": "rgba(0,0,0,0)", "hide_top_toolbar": false, "hide_legend": false,
      "save_image": false, "container_id": "{unique_id}"
      }});
      </script>
    </div>
    """
    components.html(html, height=height)

def render_plotly_line(series, name, color):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, mode='lines', name=name, line=dict(color=color, width=2)))
    fig.update_layout(template=chart_template, margin=dict(l=10, r=10, t=10, b=10), height=220, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def draw_stock_card(name, ticker, price, change):
    color = "badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"
    p_str = f"₩{price:,.0f}" if '.KS' in str(ticker) else f"${price:,.2f}"
    return f'<a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" style="text-decoration:none;"><div class="stock-card"><div class="card-left"><div class="stock-name">{name}</div><div class="stock-ticker">{str(ticker).replace(".KS", "")}</div></div><div class="card-right"><div class="stock-price">{p_str}</div><div class="badge {color}">{change:+.2f}%</div></div></div></a>'


# ==========================================
# 📊 섹터 1: 시장지표
# ==========================================
with tab_market:
    st.markdown('<div class="section-title">글로벌 지수 & 시장 체력(ADR)</div>', unsafe_allow_html=True)
    krx_adr = fetch_krx_adr()
    
    sub_kpi, sub_kdq, sub_ndq, sub_sp = st.tabs(["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"])
    def render_index_tab(market, symbol, up, dn):
        c1, c2 = st.columns([1, 4])
        with c1:
            if up > 0 or dn > 0:
                adr = (up/dn*100) if dn > 0 else 0
                st.metric(f"{market} ADR", f"{adr:.1f}%", f"상승 {up} / 하락 {dn}")
            else:
                st.metric(f"{market}", "글로벌 지수", "차트 전용")
        with c2:
            render_tv_widget(symbol, height=350)

    with sub_kpi: render_index_tab("KOSPI", "KRX:KOSPI", krx_adr["KOSPI"][0], krx_adr["KOSPI"][1])
    with sub_kdq: render_index_tab("KOSDAQ", "KRX:KOSDAQ", krx_adr["KOSDAQ"][0], krx_adr["KOSDAQ"][1])
    with sub_ndq: render_index_tab("NASDAQ", "NASDAQ:NDX", 0, 0)
    with sub_sp: render_index_tab("S&P 500", "SP:SPX", 0, 0)

    st.markdown('<div class="section-title">글로벌 리스크 & 이격도</div>', unsafe_allow_html=True)
    
    c_risk1, c_risk2 = st.columns(2)
    with c_risk1:
        st.markdown("###### 📉 KOSPI 20일 이격도 (과열/침체)")
        try:
            h_kpi = yf.Ticker('^KS11').history(period="1y")['Close']
            disp_kpi = (h_kpi / h_kpi.rolling(20).mean() * 100).dropna()
            render_plotly_line(disp_kpi, "KOSPI 이격도", "#DA291C")
        except: st.caption("데이터 로딩 실패")

    with c_risk2:
        st.markdown("###### 🚨 핵심 위험 지표")
        g_cols = st.columns(2)
        vix = yf.Ticker('^VIX').history(period="2d")
        v_val, v_chg = (vix['Close'].iloc[-1], vix['Close'].iloc[-1]-vix['Close'].iloc[-2]) if len(vix)>1 else (0,0)
        g_cols[0].metric("VIX (공포지수)", f"{v_val:.2f}", f"{v_chg:+.2f}", delta_color="inverse")
        
        t10, t03 = yf.Ticker('^TNX').history(period="1d")['Close'], yf.Ticker('^IRX').history(period="1d")['Close']
        spread = (t10.iloc[-1] - t03.iloc[-1]) if (not t10.empty and not t03.empty) else 0
        g_cols[1].metric("장단기 금리차", f"{spread:.2f}%p", "침체 경고" if spread < 0 else "정상", delta_color="off")
        
        fg_val, fg_txt = 0, "수집 불가"
        try:
            res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
            if res.status_code == 200: fg_val, fg_txt = round(res.json()['fear_and_greed']['score']), res.json()['fear_and_greed']['rating']
        except: pass
        g_cols[0].metric("CNN 공탐지수", f"{fg_val}점", fg_txt, delta_color="off")
        
        hyg = yf.Ticker('HYG').history(period="2d")
        h_val, h_chg = (hyg['Close'].iloc[-1], hyg['Close'].iloc[-1]-hyg['Close'].iloc[-2]) if len(hyg)>1 else (0,0)
        g_cols[1].metric("하이일드(HYG) ETF", f"${h_val:.2f}", f"{h_chg:+.2f} (하락시 위험)", delta_color="normal")


# ==========================================
# 🎯 섹터 2: 관심종목 
# ==========================================
with tab_watchlist:
    st.markdown('<div class="section-title">내 관심종목 모니터링</div>', unsafe_allow_html=True)
    my_stocks = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 'O', 'SCHD', '005930.KS', '000660.KS']
    
    cols = st.columns(3)
    for idx, t in enumerate(my_stocks):
        hist = yf.Ticker(t).history(period="2d")
        if len(hist) >= 2:
            close_tdy, close_ytd = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
            chg_pct = ((close_tdy - close_ytd) / close_ytd) * 100
            d_name = '삼성전자' if t == '005930.KS' else 'SK하이닉스' if t == '000660.KS' else t
            with cols[idx % 3]:
                st.markdown(draw_stock_card(d_name, t, close_tdy, chg_pct), unsafe_allow_html=True)


# ==========================================
# 📡 섹터 3: 투자인사이트
# ==========================================
with tab_insight:
    st.markdown('<div class="section-title">시장 뉴스 및 이웃 블로그</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"<h6 style='color:{text_col};'>🌍 거시 경제 뉴스</h6>", unsafe_allow_html=True)
        try:
            for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:6]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass
    with c2:
        st.markdown(f"<h6 style='color:{text_col};'>🎯 관심종목 뉴스</h6>", unsafe_allow_html=True)
        try:
            for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=애플+OR+테슬라+OR+삼성전자+OR+엔비디아&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:6]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass
    with c3:
        st.markdown(f"<h6 style='color:{text_col};'>📝 이웃 블로그 최신글</h6>", unsafe_allow_html=True)
        for name, url in [("jeunkim", "https://rss.blog.naver.com/jeunkim"), ("crush21", "https://rss.blog.naver.com/crush212121")]:
            try:
                for item in ET.fromstring(requests.get(url).content).findall('.//item')[:3]: 
                    st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank"><b>[{name}]</b> {item.find("title").text}</a></div>', unsafe_allow_html=True)
            except: pass


# ==========================================
# 🧠 섹터 4: 마인드셋
# ==========================================
with tab_mind:
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

    st.markdown('<div class="section-title" style="margin-top: 40px;">나만의 매수 매도 원칙</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size: 14px; color: {text_col}; background-color: {card_bg}; padding: 20px; border-radius: 8px; line-height: 1.8; border-left: 4px solid #DA291C; border-top: 1px solid {border_col}; border-right: 1px solid {border_col}; border-bottom: 1px solid {border_col};">
    <b>1.</b> 급격한 상승이나 하락세에 올라타지 마라. 매수, 매도 타이밍은 완만해질 때다.<br>
    <b>2.</b> 시장은 쏠리기 마련이다. 과도한 비관론에 매수하라.<br>
    <b>3.</b> 전문가도 잘 모른다. 장담하는 사람은 사기꾼이다.<br>
    <b>4.</b> 오른 만큼 가파르게 떨어진다. 그 사이 수익을 내는 것은 어렵다.<br>
    <b>5.</b> 큰 자본을 한 번에 투하하지 마라. 분할 매수해라.<br>
    <b>6.</b> 손절도 할 줄 알아야 한다. 싫으면 인내심을 길러라.<br>
    <b>7.</b> 나만 소외된 것 같을 때가 가장 참아야 할 때다.<br>
    <b>8.</b> 가치분석은 직접 해라. (저평가주 스크리닝 시 PER, PBR 외에도 이익 성장성을 필수로 확인하라[cite: 1])<br>
    <b>9.</b> 산업의 기술을 잘 안다고 주가를 잘 아는 것은 아니다.
    </div>
    """, unsafe_allow_html=True)