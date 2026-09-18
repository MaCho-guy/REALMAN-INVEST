import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import random
import uuid
import urllib.parse

# 1. 페이지 세팅 (초기 사이드바 확장)
st.set_page_config(page_title="REALMAN INVEST", layout="wide", initial_sidebar_state="expanded")

# 2. 테마 상태 관리 (다크/라이트)
if "theme_dark" not in st.session_state:
    st.session_state.theme_dark = True

# 테마 색상 변수 세팅
if st.session_state.theme_dark:
    bg_color, card_bg, text_col, sub_text, border_col = "#0B1120", "#1E293B", "#F8FAFC", "#94A3B8", "#334155"
    chart_template = "plotly_dark"
else:
    bg_color, card_bg, text_col, sub_text, border_col = "#F1F5F9", "#FFFFFF", "#0F172A", "#64748B", "#CBD5E1"
    chart_template = "plotly_white"

# 커스텀 CSS 주입
st.markdown(f"""
<style>
    /* 전체 배경 및 텍스트 색상 */
    .stApp, .stApp p, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {{ color: {text_col}; background-color: {bg_color}; }}
    
    /* header를 숨기지 않아야 사이드바 펼치기 버튼(>)이 보입니다 */
    #MainMenu, footer {{visibility: hidden;}}
    
    [data-testid="stSidebar"] {{ background-color: {card_bg}; border-right: 1px solid {border_col}; }}
    
    /* 📌 사이드바 타이틀 로고 색상 보호 */
    .sidebar-title {{ font-size: 24px; font-weight: 900; color: #DA291C !important; font-style: italic; text-align: center; margin-bottom: 20px; letter-spacing: -1px; }}
    
    /* 📌 메인 화면 슈프림 타이틀 색상 보호 */
    .supreme-container {{ display: flex; justify-content: center; margin-top: 10px; margin-bottom: 25px; }}
    .supreme-box {{ 
        background-color: #DA291C !important; color: #FFFFFF !important; 
        padding: 8px 30px; border-radius: 2px; text-align: center; 
        font-family: 'Futura', sans-serif; font-size: 38px !important; font-weight: 900; 
        font-style: italic; letter-spacing: -2px; box-shadow: 0 6px 12px rgba(218, 41, 28, 0.3); 
        text-transform: uppercase;
    }}
    
    .section-title {{ background-color: {card_bg}; color: {text_col} !important; border-left: 4px solid #DA291C; padding: 12px 16px; border-radius: 6px; font-size: 18px; font-weight: 700; margin-top: 20px; margin-bottom: 15px; border: 1px solid {border_col}; }}
    
    .card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; }}
    .stock-card {{ background-color: {card_bg}; border: 1px solid {border_col}; border-radius: 8px; padding: 16px; display: flex; justify-content: space-between; align-items: center; transition: transform 0.2s; }}
    .stock-card:hover {{ transform: translateY(-2px); border-color: #DA291C; }}
    
    .stock-name {{ font-size: 15px; font-weight: 700; color: {text_col} !important; }}
    .stock-ticker {{ font-size: 12px; color: {sub_text} !important; margin-top: 2px; }}
    .stock-price {{ font-size: 16px; font-weight: 700; color: {text_col} !important; }}
    
    .badge {{ font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 4px; color: #fff !important; }}
    .badge-up {{ background-color: #ef4444 !important; }} 
    .badge-down {{ background-color: #3b82f6 !important; }} 
    .badge-neutral {{ background-color: #475569 !important; }}
    
    .news-item {{ background-color: {card_bg}; border: 1px solid {border_col}; border-radius: 6px; padding: 12px; margin-bottom: 8px; }}
    .news-item a {{ color: {text_col} !important; text-decoration: none; font-size: 14px; }}
    .news-item a:hover {{ color: #DA291C !important; text-decoration: underline; }}
    
    div[data-baseweb="tab-list"] {{ gap: 24px; margin-bottom: 20px; }}
    div[data-baseweb="tab"] {{ font-size: 16px !important; font-weight: 700 !important; color: {sub_text} !important; border: none !important; }}
    div[aria-selected="true"] {{ color: {text_col} !important; border-bottom: 3px solid #DA291C !important; }}
</style>
""", unsafe_allow_html=True)


# ==========================================
# 📌 사이드바 및 7대 섹터 라우팅
# ==========================================
st.sidebar.markdown('<div class="sidebar-title">REALMAN INVEST</div>', unsafe_allow_html=True)

if st.sidebar.button("🌞 / 🌙 라이트/다크 전환", use_container_width=True):
    st.session_state.theme_dark = not st.session_state.theme_dark
    st.rerun()

st.sidebar.divider()

menus = ["시장지표", "자금흐름", "종목/공시", "AI TRADE", "뉴스/인사이트", "관심종목", "마인드셋"]
current_param = st.query_params.get("current_page", menus[0])
if current_param not in menus:
    current_param = menus[0]
    st.query_params["current_page"] = current_param

selected_page = st.sidebar.radio("MENU", menus, index=menus.index(current_param))
if selected_page != st.query_params.get("current_page"):
    st.query_params["current_page"] = selected_page
    st.rerun()


# 메인 화면 슈프림 타이틀
st.markdown('<div class="supreme-container"><div class="supreme-box">REALMAN INVEST</div></div>', unsafe_allow_html=True)

# ==========================================
# 🛠️ 데이터 연동 함수
# ==========================================
@st.cache_data(ttl=300)
def fetch_krx_adr():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res_kpi = requests.get("https://finance.naver.com/sise/sise_index.naver?code=KOSPI", headers=headers, timeout=3)
        soup_kpi = BeautifulSoup(res_kpi.text, 'html.parser')
        kpi_up = int(soup_kpi.find(id='now_up').text.replace(',', ''))
        kpi_dn = int(soup_kpi.find(id='now_down').text.replace(',', ''))
        
        res_kdq = requests.get("https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ", headers=headers, timeout=3)
        soup_kdq = BeautifulSoup(res_kdq.text, 'html.parser')
        kdq_up = int(soup_kdq.find(id='now_up').text.replace(',', ''))
        kdq_dn = int(soup_kdq.find(id='now_down').text.replace(',', ''))
        
        return {"KOSPI": (kpi_up, kpi_dn), "KOSDAQ": (kdq_up, kdq_dn)}
    except: 
        return {"KOSPI": (0, 0), "KOSDAQ": (0, 0)}

@st.cache_data(ttl=3600)
def get_hist_data(ticker, period):
    try:
        df = yf.Ticker(ticker).history(period=period)
        return df if not df.empty else pd.DataFrame()
    except:
        return pd.DataFrame()

def plot_line_chart(series, title, color="#DA291C", hline_upper=None, hline_lower=None, chart_type='line'):
    fig = go.Figure()
    if chart_type == 'line':
        fig.add_trace(go.Scatter(x=series.index, y=series.values, mode='lines', line=dict(color=color, width=2)))
    elif chart_type == 'bar':
        fig.add_trace(go.Bar(x=series.index, y=series.values, marker_color=color))
        
    if hline_upper: fig.add_hline(y=hline_upper, line_dash="dot", line_color="red", annotation_text="과매수")
    if hline_lower: fig.add_hline(y=hline_lower, line_dash="dot", line_color="blue", annotation_text="과매도")
    fig.update_layout(title=title, template=chart_template, height=300, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def render_tv_widget(symbol, height=450):
    unique_id = f"tv_{uuid.uuid4().hex}"
    tv_theme = "dark" if st.session_state.theme_dark else "light"
    bg_code = "#1E293B" if st.session_state.theme_dark else "#FFFFFF"
    html_code = f"""
    <div class="tradingview-widget-container" style="height:{height}px;width:100%">
      <div id="{unique_id}" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
      "autosize": true, "symbol": "{symbol}", "interval": "D", "timezone": "Asia/Seoul",
      "theme": "{tv_theme}", "style": "1", "locale": "kr", "enable_publishing": false,
      "backgroundColor": "{bg_code}", "hide_top_toolbar": false, "hide_legend": false,
      "save_image": false, "container_id": "{unique_id}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=height)


# ==========================================
# 📊 [섹터 1] 시장지표
# ==========================================
if selected_page == menus[0]:
    st.markdown('<div class="section-title">시장지표 대시보드</div>', unsafe_allow_html=True)
    sub_menu = st.radio("서브 메뉴", ["ADR", "위험지표", "주요지수 연도별 수익률"], horizontal=True, label_visibility="collapsed")
    
    if sub_menu == "ADR":
        krx_adr = fetch_krx_adr()
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown(f"<div style='background:{card_bg}; padding:15px; border-radius:8px; border:1px solid {border_col};'>", unsafe_allow_html=True)
            st.subheader("KOSPI 실시간 ADR")
            up, dn = krx_adr["KOSPI"]
            adr_val = (up/dn*100) if dn>0 else 0
            st.metric("ADR %", f"{adr_val:.1f}%", f"{adr_val - 100:+.1f}%p (100% 기준)")
            st.caption(f"상승 종목: {up}개 / 하락 종목: {dn}개")
            st.markdown("</div>", unsafe_allow_html=True)
            
        with c2:
            st.markdown(f"<div style='background:{card_bg}; padding:15px; border-radius:8px; border:1px solid {border_col};'>", unsafe_allow_html=True)
            st.subheader("KOSDAQ 실시간 ADR")
            up, dn = krx_adr["KOSDAQ"]
            adr_val = (up/dn*100) if dn>0 else 0
            st.metric("ADR %", f"{adr_val:.1f}%", f"{adr_val - 100:+.1f}%p (100% 기준)")
            st.caption(f"상승 종목: {up}개 / 하락 종목: {dn}개")
            st.markdown("</div>", unsafe_allow_html=True)

        st.divider()
        st.markdown("#### 지수 장기 추이 및 차트")
        t_kpi, t_kdq, t_ndq, t_sp = st.tabs(["KOSPI", "KOSDAQ", "NASDAQ 100", "S&P 500"])
        
        with t_kpi: render_tv_widget("KRX:KOSPI")
        with t_kdq: render_tv_widget("KRX:KOSDAQ")
        with t_ndq: render_tv_widget("OANDA:NAS100USD")
        with t_sp: render_tv_widget("OANDA:SPX500USD")

    elif sub_menu == "위험지표":
        st.markdown("#### 1. 이격도 (과매수/과매도)")
        disp_period = st.radio("기간 선택 (이격도)", ["1mo", "2mo", "6mo", "1y", "3y"], horizontal=True, format_func=lambda x: {"1mo":"25일","2mo":"50일","6mo":"6M","1y":"1Y","3y":"3Y"}[x])
        c_kpi, c_kdq = st.columns(2)
        h_kpi = get_hist_data("^KS11", disp_period)
        if not h_kpi.empty:
            disp_kpi = (h_kpi['Close'] / h_kpi['Close'].rolling(20).mean() * 100).dropna()
            c_kpi.plotly_chart(plot_line_chart(disp_kpi, f"KOSPI 20일 이격도 ({disp_kpi.iloc[-1]:.1f}%)", "#DA291C", 105, 95), use_container_width=True)
        
        h_kdq = get_hist_data("^KQ11", disp_period)
        if not h_kdq.empty:
            disp_kdq = (h_kdq['Close'] / h_kdq['Close'].rolling(20).mean() * 100).dropna()
            c_kdq.plotly_chart(plot_line_chart(disp_kdq, f"KOSDAQ 20일 이격도 ({disp_kdq.iloc[-1]:.1f}%)", "#3b82f6", 105, 95), use_container_width=True)
        
        st.divider()
        st.markdown("#### 2. 글로벌 위험지표 (6M, 1Y, 3Y)")
        glob_period = st.radio("기간 선택 (글로벌)", ["6mo", "1y", "3y"], horizontal=True, format_func=lambda x: x.upper())
        g1, g2 = st.columns(2)
        vix = get_hist_data("^VIX", glob_period)
        if not vix.empty: g1.plotly_chart(plot_line_chart(vix['Close'], f"VIX 공포지수 ({vix['Close'].iloc[-1]:.2f})", "#f59e0b", 30), use_container_width=True)
        
        t10, t03 = get_hist_data("^TNX", glob_period), get_hist_data("^IRX", glob_period)
        if not t10.empty and not t03.empty:
            spread = (t10['Close'] - t03['Close']).dropna()
            g2.plotly_chart(plot_line_chart(spread, f"미국 장단기 금리차 ({spread.iloc[-1]:.2f}%p)", "#8b5cf6", hline_lower=0), use_container_width=True)
        
        g3, g4 = st.columns(2)
        hyg = get_hist_data("HYG", glob_period)
        if not hyg.empty: g3.plotly_chart(plot_line_chart(hyg['Close'], f"하이일드 스프레드 프록시 (HYG ${hyg['Close'].iloc[-1]:.2f})", "#10b981"), use_container_width=True)
        
        try:
            res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla'}, timeout=2)
            fg = round(res.json()['fear_and_greed']['score'])
        except: fg = 50
        g4.metric("CNN 공포탐욕지수 (실시간)", f"{fg}점")
        
        st.divider()
        st.markdown("#### 3. 한국 위험지표")
        kor_period = st.radio("기간 선택 (한국)", ["6mo", "1y", "3y"], horizontal=True, format_func=lambda x: x.upper(), key="kor")
        k1, k2 = st.columns(2)
        vkospi = get_hist_data("^VKOSPI", kor_period)
        if not vkospi.empty: k1.plotly_chart(plot_line_chart(vkospi['Close'], f"VKOSPI 변동성 ({vkospi['Close'].iloc[-1]:.2f})", "#ec4899", 25), use_container_width=True)
        
        ksp_full = get_hist_data("^KS11", "5y")
        if not ksp_full.empty and not vkospi.empty:
            h52, l52 = ksp_full['Close'].rolling(252).max(), ksp_full['Close'].rolling(252).min()
            nh_nl = ((ksp_full['Close'] - l52) / (h52 - l52) * 100).tail(len(vkospi))
            k2.plotly_chart(plot_line_chart(nh_nl, f"KOSPI 신고가-신저가 프록시 ({nh_nl.iloc[-1]:.1f}%)", "#14b8a6", 80, 20), use_container_width=True)

    elif sub_menu == "주요지수 연도별 수익률":
        st.markdown("#### 1970년대 ~ 현재 연도별 수익률 (S&P500, NASDAQ, KOSPI, KOSDAQ)")
        @st.cache_data(ttl=86400)
        def get_max_annual_returns():
            df = yf.download(["^GSPC", "^IXIC", "^KS11", "^KQ11"], period="max")["Close"]
            yr = df.resample('YE').last().pct_change() * 100
            yr.columns = ["S&P 500", "NASDAQ", "KOSPI", "KOSDAQ"]
            return yr.dropna(how='all')
            
        ret_df = get_max_annual_returns()
        fig = px.bar(ret_df, barmode='group', template=chart_template)
        fig.update_layout(height=500, xaxis_title="연도", yaxis_title="수익률 (%)", legend_title="지수", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)


# ==========================================
# 💸 [섹터 2] 자금흐름
# ==========================================
elif selected_page == menus[1]:
    st.markdown('<div class="section-title">자금흐름 및 ETF 트렌드</div>', unsafe_allow_html=True)
    tabs = st.tabs(["글로벌 ETF 자금 (QQQ/SPY/SOXX)", "서학개미 인기종목 트렌드"])
    
    with tabs[0]:
        st.markdown("#### 글로벌 주요 ETF 최근 3개월 성과 (자금 유입 프록시)")
        etf_list = ["QQQ", "SPY", "SOXX", "TQQQ"]
        etf_data = yf.download(etf_list, period="3mo")["Close"]
        etf_norm = (etf_data / etf_data.iloc[0] - 1) * 100
        fig_etf = px.line(etf_norm, template=chart_template, height=350)
        fig_etf.update_layout(yaxis_title="수익률 (%)", xaxis_title="")
        st.plotly_chart(fig_etf, use_container_width=True)
        
    with tabs[1]:
        st.markdown("#### 미국 주요 빅테크 서학개미 선호 종목 동향")
        us_stocks = ["NVDA", "TSLA", "AAPL", "MSFT"]
        us_df = yf.download(us_stocks, period="1mo")["Close"]
        us_norm = (us_df / us_df.iloc[0] - 1) * 100
        fig_us = px.line(us_norm, template=chart_template, height=350)
        st.plotly_chart(fig_us, use_container_width=True)


# ==========================================
# 📄 [섹터 3] 종목/공시
# ==========================================
elif selected_page == menus[2]:
    st.markdown('<div class="section-title">종목 및 공시 데이터</div>', unsafe_allow_html=True)
    tabs = st.tabs(["주요 주도주 52주 신고가 현황", "실시간 공시 및 뉴스"])
    
    with tabs[0]:
        st.markdown("#### 글로벌 및 국내 주요 주도주 52주 고점 대비 위치")
        target_pool = ["NVDA", "AAPL", "MSFT", "TSM", "ASML", "005930.KS", "000660.KS", "373220.KS"]
        card_html = '<div class="card-grid">'
        for t in target_pool:
            try:
                hist = get_hist_data(t, "1y")
                if not hist.empty:
                    cur = hist['Close'].iloc[-1]
                    high52 = hist['High'].max()
                    ratio = (cur / high52) * 100
                    disp_t = t.replace(".KS", "")
                    card_html += f'<div class="stock-card"><div class="card-left"><div class="stock-name">{disp_t}</div><div class="stock-ticker">현재: {cur:,.0f}</div></div><div class="card-right"><div class="stock-price">{ratio:.1f}%</div><div class="badge badge-up">고점대비</div></div></div>'
            except: pass
        card_html += '</div>'
        st.markdown(card_html, unsafe_allow_html=True)
        
    with tabs[1]:
        st.markdown("#### DART 및 기업 공시 관련 실시간 뉴스")
        try:
            feed = requests.get("https://news.google.com/rss/search?q=전자공시+OR+DART+OR+상장공시&hl=ko&gl=KR&ceid=KR:ko", timeout=3)
            for item in ET.fromstring(feed.content).findall('.//item')[:8]:
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
        except:
            st.info("공시 뉴스 로딩 중...")


# ==========================================
# 🤖 [섹터 4] AI TRADE
# ==========================================
elif selected_page == menus[3]:
    st.markdown('<div class="section-title">AI TRADE & 반도체 프록시 분석</div>', unsafe_allow_html=True)
    st.markdown("#### TSMC vs 삼성전자 상대 퍼포먼스 비교 (글로벌 반도체 자금 흐름)")
    try:
        semi_df = yf.download(["TSM", "005930.KS"], period="6mo")["Close"]
        semi_norm = (semi_df / semi_df.iloc[0] - 1) * 100
        fig_semi = px.line(semi_norm, template=chart_template, height=350)
        fig_semi.update_layout(yaxis_title="상승률 (%)", xaxis_title="")
        st.plotly_chart(fig_semi, use_container_width=True)
    except:
        st.error("데이터 로딩 실패")


# ==========================================
# 📡 [섹터 5] 뉴스/인사이트
# ==========================================
elif selected_page == menus[4]:
    st.markdown('<div class="section-title">뉴스 및 이웃 블로그 인사이트</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    
    def render_rss(url, limit=5):
        html = ""
        try:
            for item in ET.fromstring(requests.get(url, timeout=3).content).findall('.//item')[:limit]:
                html += f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>'
        except: html = '<div class="news-item">데이터 로딩 실패</div>'
        return html

    with c1:
        st.markdown("<h6>🌍 거시 경제 뉴스</h6>", unsafe_allow_html=True)
        st.markdown(render_rss("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko", 6), unsafe_allow_html=True)
    with c2:
        st.markdown("<h6>🎯 기술주 및 시장 뉴스</h6>", unsafe_allow_html=True)
        st.markdown(render_rss("https://news.google.com/rss/search?q=나스닥+기술주+반도체&hl=ko&gl=KR&ceid=KR:ko", 6), unsafe_allow_html=True)
    with c3:
        st.markdown("<h6>📝 이웃 블로그 최신글</h6>", unsafe_allow_html=True)
        st.markdown(render_rss("https://rss.blog.naver.com/jeunkim", 3), unsafe_allow_html=True)
        st.markdown(render_rss("https://rss.blog.naver.com/crush212121", 3), unsafe_allow_html=True)


# ==========================================
# 🎯 [섹터 6] 관심종목
# ==========================================
elif selected_page == menus[5]:
    st.markdown('<div class="section-title">내 관심종목 모니터링</div>', unsafe_allow_html=True)
    my_stocks = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 'O', 'SCHD', '005930.KS', '000660.KS']
    
    html_stock = '<div class="card-grid">'
    for t in my_stocks:
        try:
            hist = get_hist_data(t, "5d")
            if not hist.empty and len(hist) >= 2:
                close_tdy = hist['Close'].iloc[-1]
                close_ytd = hist['Close'].iloc[-2]
                chg_pct = ((close_tdy - close_ytd) / close_ytd) * 100
                p_str = f"₩{close_tdy:,.0f}" if '.KS' in str(t) else f"${close_tdy:,.2f}"
            else:
                close_tdy, chg_pct, p_str = 0.0, 0.0, "데이터 없음"
                
            d_name = '삼성전자' if t == '005930.KS' else 'SK하이닉스' if t == '000660.KS' else t
            color = "badge-up" if chg_pct > 0 else "badge-down" if chg_pct < 0 else "badge-neutral"
            
            html_stock += f'<a href="https://finance.yahoo.com/quote/{t}" target="_blank" style="text-decoration:none;"><div class="stock-card"><div class="card-left"><div class="stock-name">{d_name}</div><div class="stock-ticker">{str(t).replace(".KS", "")}</div></div><div class="card-right"><div class="stock-price">{p_str}</div><div class="badge {color}">{chg_pct:+.2f}%</div></div></div></a>'
        except:
            html_stock += f'<div class="stock-card"><div class="card-left"><div class="stock-name">{t}</div><div class="stock-ticker">로딩 지연</div></div><div class="card-right"><div class="stock-price">-</div><div class="badge badge-neutral">N/A</div></div></div>'
            continue
            
    html_stock += '</div>'
    st.markdown(html_stock, unsafe_allow_html=True)
    st.caption("[cite: 1]")


# ==========================================
# 🧠 [섹터 7] 마인드셋
# ==========================================
elif selected_page == menus[6]:
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
        
        html_card = f"""
        <div style="background-color: {card_bg}; padding: 20px; border-radius: 8px; border: 1px solid {border_col}; margin-bottom: 15px; height: 160px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <strong style="font-size: 16px; color: {text_col};">{guru['name']}</strong>
                <p style="font-size: 14px; color: {sub_text}; margin-top: 8px; line-height: 1.4;">"{random.choice(guru['quotes'])}"</p>
            </div>
            <a href="{yt}" target="_blank" style="display: inline-block; background-color: #DA291C; color: #FFFFFF; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: 700; width: fit-content; margin-top: 10px;">▶️ 관련 영상 보기</a>
        </div>
        """
        cols[i].markdown(html_card, unsafe_allow_html=True)

    st.markdown('<div class="section-title">나만의 매수 매도 원칙</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size: 15px; background-color: {card_bg}; padding: 24px; border-radius: 8px; line-height: 1.8; border-left: 4px solid #DA291C;">
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