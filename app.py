import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import random

# 1. 페이지 세팅 (초기 사이드바 확장)
st.set_page_config(page_title="REALMAN INVEST", layout="wide", initial_sidebar_state="expanded")

# 2. 테마 상태 관리 (해/달 버튼 클릭형)
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
    .stApp {{ background-color: {bg_color}; color: {text_col}; }}
    #MainMenu, footer, header {{visibility: hidden;}}
    [data-testid="stSidebar"] {{ background-color: {card_bg}; border-right: 1px solid {border_col}; }}
    
    .sidebar-title {{ font-size: 24px; font-weight: 900; color: #DA291C; font-style: italic; text-align: center; margin-bottom: 20px; letter-spacing: -1px; }}
    .section-title {{ background-color: {card_bg}; border-left: 4px solid #DA291C; padding: 12px 16px; border-radius: 6px; font-size: 18px; font-weight: 700; margin-top: 20px; margin-bottom: 15px; border: 1px solid {border_col}; }}
    
    .card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; }}
    .stock-card {{ background-color: {card_bg}; border: 1px solid {border_col}; border-radius: 8px; padding: 16px; display: flex; justify-content: space-between; align-items: center; transition: transform 0.2s; }}
    .stock-name {{ font-size: 15px; font-weight: 700; color: {text_col}; }}
    .stock-ticker {{ font-size: 12px; color: {sub_text}; margin-top: 2px; }}
    .stock-price {{ font-size: 16px; font-weight: 700; color: {text_col}; }}
    .badge {{ font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 4px; color: #fff; }}
    .badge-up {{ background-color: #ef4444; }} 
    .badge-down {{ background-color: #3b82f6; }} 
    .badge-neutral {{ background-color: #475569; }}
    
    .news-item {{ background-color: {card_bg}; border: 1px solid {border_col}; border-radius: 6px; padding: 12px; margin-bottom: 8px; }}
    .news-item a {{ color: {text_col}; text-decoration: none; font-size: 14px; }}
    
    /* 탭 디자인 오버라이드 */
    div[data-baseweb="tab-list"] {{ gap: 24px; margin-bottom: 20px; }}
    div[data-baseweb="tab"] {{ font-size: 16px !important; font-weight: 700 !important; color: {sub_text}; }}
    div[aria-selected="true"] {{ color: {text_col} !important; border-bottom: 3px solid #DA291C !important; }}
</style>
""", unsafe_allow_html=True)


# ==========================================
# 📌 사이드바 및 7대 섹터 라우팅
# ==========================================
st.sidebar.markdown('<div class="sidebar-title">REALMAN INVEST</div>', unsafe_allow_html=True)

# 🌞/🌙 테마 전환 버튼
if st.sidebar.button("🌞 / 🌙 라이트/다크 전환", use_container_width=True):
    st.session_state.theme_dark = not st.session_state.theme_dark
    st.rerun()

st.sidebar.divider()

menus = ["📊 1. 시장지표", "💸 2. 자금흐름", "📄 3. 종목/공시", "🤖 4. AI TRADE", "📡 5. 뉴스/인사이트", "🎯 6. 관심종목", "🧠 7. 마인드셋"]
if "current_page" not in st.query_params:
    st.query_params["current_page"] = menus[0]

# 메뉴 선택
selected_page = st.sidebar.radio("MENU", menus, index=menus.index(st.query_params.get("current_page", menus[0])))
if selected_page != st.query_params.get("current_page"):
    st.query_params["current_page"] = selected_page
    st.rerun()


# ==========================================
# 🛠️ 공통 데이터 함수
# ==========================================
@st.cache_data(ttl=300)
def fetch_krx_adr():
    try:
        res = requests.get("https://finance.naver.com/sise/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        k_up, k_dn = soup.select_one('#KOSPI_now ~ .siselist .up em'), soup.select_one('#KOSPI_now ~ .siselist .down em')
        q_up, q_dn = soup.select_one('#KOSDAQ_now ~ .siselist .up em'), soup.select_one('#KOSDAQ_now ~ .siselist .down em')
        return {
            "KOSPI": (int(k_up.text.replace(',','')) if k_up else 0, int(k_dn.text.replace(',','')) if k_dn else 0),
            "KOSDAQ": (int(q_up.text.replace(',','')) if q_up else 0, int(q_dn.text.replace(',','')) if q_dn else 0)
        }
    except: return {"KOSPI": (0, 0), "KOSDAQ": (0, 0)}

@st.cache_data(ttl=3600)
def get_hist_data(ticker, period):
    return yf.Ticker(ticker).history(period=period)['Close']

def plot_line_chart(series, title, color="#DA291C", hline_upper=None, hline_lower=None):
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode='lines', line=dict(color=color, width=2)))
    if hline_upper: fig.add_hline(y=hline_upper, line_dash="dot", line_color="red", annotation_text="과매수")
    if hline_lower: fig.add_hline(y=hline_lower, line_dash="dot", line_color="blue", annotation_text="과매도")
    fig.update_layout(title=title, template=chart_template, height=300, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig


# ==========================================
# 📊 1. 시장지표
# ==========================================
if selected_page == menus[0]:
    st.markdown('<div class="section-title">시장지표 대시보드</div>', unsafe_allow_html=True)
    
    # 하위 메뉴 (Pills 대체용 Radio)
    sub_menu = st.radio("서브 메뉴", ["⚖️ ADR", "🚨 위험지표", "📅 주요지수 연도별 수익률"], horizontal=True, label_visibility="collapsed")
    
    # ----------------- 1-1. ADR -----------------
    if sub_menu == "⚖️ ADR":
        krx_adr = fetch_krx_adr()
        c1, c2 = st.columns(2)
        
        # KOSPI
        with c1:
            st.markdown(f"<div style='background:{card_bg}; padding:15px; border-radius:8px; border:1px solid {border_col};'>", unsafe_allow_html=True)
            st.subheader("KOSPI 실시간 ADR")
            up, dn = krx_adr["KOSPI"]
            adr_val = (up/dn*100) if dn>0 else 0
            chg = adr_val - 100 # 기준 100 대비
            st.metric("ADR %", f"{adr_val:.1f}%", f"{chg:+.1f}%p (100% 기준)")
            st.caption(f"상승 종목: {up}개 / 하락 종목: {dn}개")
            st.markdown("</div>", unsafe_allow_html=True)
            
        # KOSDAQ
        with c2:
            st.markdown(f"<div style='background:{card_bg}; padding:15px; border-radius:8px; border:1px solid {border_col};'>", unsafe_allow_html=True)
            st.subheader("KOSDAQ 실시간 ADR")
            up, dn = krx_adr["KOSDAQ"]
            adr_val = (up/dn*100) if dn>0 else 0
            chg = adr_val - 100
            st.metric("ADR %", f"{adr_val:.1f}%", f"{chg:+.1f}%p (100% 기준)")
            st.caption(f"상승 종목: {up}개 / 하락 종목: {dn}개")
            st.markdown("</div>", unsafe_allow_html=True)

        st.divider()
        st.markdown("#### 지수 장기 추이 (ADR 프록시)")
        period = st.select_slider("조회 기간 선택", options=["6mo", "1y", "3y", "5y"], value="1y")
        
        kpi_hist = get_hist_data("^KS11", period)
        st.plotly_chart(plot_line_chart(kpi_hist, "KOSPI 지수 추이", "#DA291C"), use_container_width=True)
        
        kdq_hist = get_hist_data("^KQ11", period)
        st.plotly_chart(plot_line_chart(kdq_hist, "KOSDAQ 지수 추이", "#3b82f6"), use_container_width=True)

    # ----------------- 1-2. 위험지표 -----------------
    elif sub_menu == "🚨 위험지표":
        st.markdown("#### 1. 이격도 (과매수/과매도)")
        disp_period = st.radio("기간 선택 (이격도)", ["1mo", "2mo", "6mo", "1y", "3y"], horizontal=True, format_func=lambda x: {"1mo":"25일","2mo":"50일","6mo":"6M","1y":"1Y","3y":"3Y"}[x])
        
        c_kpi, c_kdq = st.columns(2)
        h_kpi = get_hist_data("^KS11", disp_period)
        disp_kpi = (h_kpi / h_kpi.rolling(20).mean() * 100).dropna()
        c_kpi.plotly_chart(plot_line_chart(disp_kpi, "KOSPI 20일 이격도", "#DA291C", 105, 95), use_container_width=True)
        
        h_kdq = get_hist_data("^KQ11", disp_period)
        disp_kdq = (h_kdq / h_kdq.rolling(20).mean() * 100).dropna()
        c_kdq.plotly_chart(plot_line_chart(disp_kdq, "KOSDAQ 20일 이격도", "#3b82f6", 105, 95), use_container_width=True)
        
        st.divider()
        st.markdown("#### 2. 글로벌 위험지표")
        glob_period = st.radio("기간 선택 (글로벌)", ["6mo", "1y", "3y"], horizontal=True, format_func=lambda x: x.upper())
        
        g1, g2 = st.columns(2)
        vix = get_hist_data("^VIX", glob_period)
        g1.plotly_chart(plot_line_chart(vix, "VIX (공포지수)", "#f59e0b", 30), use_container_width=True)
        
        t10 = get_hist_data("^TNX", glob_period)
        t03 = get_hist_data("^IRX", glob_period)
        spread = (t10 - t03).dropna()
        g2.plotly_chart(plot_line_chart(spread, "미국 장단기 금리차 (10Y-3M)", "#8b5cf6", hline_lower=0), use_container_width=True)
        
        g3, g4 = st.columns(2)
        hyg = get_hist_data("HYG", glob_period)
        g3.plotly_chart(plot_line_chart(hyg, "하이일드 스프레드 프록시 (HYG 가격)", "#10b981"), use_container_width=True)
        
        # CNN (차트는 API 불가로 현재값 대체)
        try:
            res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla'}, timeout=2)
            fg = round(res.json()['fear_and_greed']['score'])
        except: fg = 0
        g4.info(f"**CNN 공포탐욕지수 (실시간)**\n\n현재 점수: {fg}점 (차트 API 미제공 영역)")
        
        st.divider()
        st.markdown("#### 3. 한국 위험지표")
        kor_period = st.radio("기간 선택 (한국)", ["6mo", "1y", "3y"], horizontal=True, format_func=lambda x: x.upper(), key="kor")
        
        k1, k2 = st.columns(2)
        vkospi = get_hist_data("^VKOSPI", kor_period)
        k1.plotly_chart(plot_line_chart(vkospi, "VKOSPI (한국 변동성)", "#ec4899", 25), use_container_width=True)
        
        ksp_full = get_hist_data("^KS11", "5y") # 52주 계산을 위해 넉넉히 호출
        h52 = ksp_full.rolling(252).max()
        l52 = ksp_full.rolling(252).min()
        nh_nl = ((ksp_full - l52) / (h52 - l52) * 100).tail(len(vkospi)) # 선택된 기간만큼 슬라이싱
        k2.plotly_chart(plot_line_chart(nh_nl, "KOSPI 신고가-신저가 프록시 (%)", "#14b8a6", 80, 20), use_container_width=True)

    # ----------------- 1-3. 주요지수 연도별 수익률 -----------------
    elif sub_menu == "📅 주요지수 연도별 수익률":
        st.markdown("#### 1970년대 ~ 현재 연도별 수익률")
        st.caption("※ 야후 파이낸스 데이터 제공 시점부터 계산됩니다. (KOSPI는 1990년대부터)")
        
        @st.cache_data(ttl=86400)
        def get_max_annual_returns():
            df = yf.download(["^GSPC", "^IXIC", "^KS11", "^KQ11"], period="max")["Close"]
            yr = df.resample('YE').last().pct_change() * 100
            yr.columns = ["S&P 500", "NASDAQ", "KOSPI", "KOSDAQ"]
            return yr.dropna(how='all')
            
        ret_df = get_max_annual_returns()
        fig = px.bar(ret_df, barmode='group', template=chart_template)
        fig.update_layout(height=500, xaxis_title="연도", yaxis_title="수익률 (%)", legend_title="지수")
        st.plotly_chart(fig, use_container_width=True)


# ==========================================
# 💸 2. 자금흐름 (UI Scaffolding)
# ==========================================
elif selected_page == menus[1]:
    st.markdown('<div class="section-title">자금흐름</div>', unsafe_allow_html=True)
    tabs = st.tabs(["증시자금 추이", "ETF 자금흐름", "ETF 구성종목 변동", "서학개미 순매수 종목"])
    
    with tabs[0]:
        st.info("💡 **증시자금 추이 (고객예탁금, 신용잔고 등)**\n\n금융투자협회(KOFIA) API 연동 또는 자체 DB 서버 구축이 필요한 영역입니다. 주식봇과 동일한 레이아웃이 적용될 자리입니다.")
    with tabs[1]:
        st.info("💡 **ETF 자금흐름**\n\n글로벌 ETF 자금 유입/유출 데이터(예: ETF.com API) 연동이 필요한 영역입니다.")
    with tabs[2]:
        st.info("💡 **ETF 구성종목 변동**\n\n자산운용사(iShares, Vanguard 등) 일일 보유종목 내역 파싱 DB가 필요합니다.")
    with tabs[3]:
        st.info("💡 **서학개미 순매수 종목**\n\n한국예탁결제원(SEIBro) API 연동 시 주식봇과 완벽히 동일하게 구현 가능합니다.")


# ==========================================
# 📄 3. 종목/공시 (UI Scaffolding)
# ==========================================
elif selected_page == menus[2]:
    st.markdown('<div class="section-title">종목 및 공시 데이터</div>', unsafe_allow_html=True)
    tabs = st.tabs(["52주 신고가/등락률", "DART 공시", "수출입데이터"])
    
    with tabs[0]:
        st.info("💡 **52주 신고가 / 당일 등락률**\n\n전 종목 실시간 시세 데이터베이스(KRX/OpenAPI) 스캐너가 필요합니다.")
    with tabs[1]:
        st.info("💡 **DART 공시**\n\n금융감독원 Open DART API 키를 발급받아 연동하면 실시간 공시 목록을 띄울 수 있습니다.")
    with tabs[2]:
        st.info("💡 **수출입데이터**\n\n관세청 수출입 무역통계 API 연동 자리입니다.")


# ==========================================
# 🤖 4. AI TRADE (UI Scaffolding)
# ==========================================
elif selected_page == menus[3]:
    st.markdown('<div class="section-title">AI TRADE 분석</div>', unsafe_allow_html=True)
    tabs = st.tabs(["상대시총", "대만 월별 매출"])
    
    with tabs[0]:
        st.info("💡 **상대시총 (Relative Market Cap)**\n\n삼성전자 vs TSMC 등 두 기업의 시가총액 비율을 계산하여 차트로 그리는 백엔드 연산 영역입니다.")
    with tabs[1]:
        st.info("💡 **대만 월별 매출**\n\nTSMC, 폭스콘 등 대만 상장사들은 매월 10일 의무적으로 월별 매출을 발표합니다. 대만 거래소 데이터 파싱이 필요합니다.")


# ==========================================
# 📡 5. 뉴스 및 투자 인사이트
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
        st.markdown(f"<h6 style='color:{text_col};'>🌍 거시 경제 뉴스</h6>", unsafe_allow_html=True)
        st.markdown(render_rss("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko", 6), unsafe_allow_html=True)
    with c2:
        st.markdown(f"<h6 style='color:{text_col};'>🎯 기술주 및 시장 뉴스</h6>", unsafe_allow_html=True)
        st.markdown(render_rss("https://news.google.com/rss/search?q=나스닥+기술주+반도체&hl=ko&gl=KR&ceid=KR:ko", 6), unsafe_allow_html=True)
    with c3:
        st.markdown(f"<h6 style='color:{text_col};'>📝 이웃 블로그 최신글</h6>", unsafe_allow_html=True)
        st.markdown(render_rss("https://rss.blog.naver.com/jeunkim", 3), unsafe_allow_html=True)
        st.markdown(render_rss("https://rss.blog.naver.com/crush212121", 3), unsafe_allow_html=True)


# ==========================================
# 🎯 6. 관심종목
# ==========================================
elif selected_page == menus[5]:
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
                color = "badge-up" if chg_pct > 0 else "badge-down" if chg_pct < 0 else "badge-neutral"
                p_str = f"₩{close_tdy:,.0f}" if '.KS' in str(t) else f"${close_tdy:,.2f}"
                html_stock += f'<a href="https://finance.yahoo.com/quote/{t}" target="_blank" style="text-decoration:none;"><div class="stock-card"><div class="card-left"><div class="stock-name">{d_name}</div><div class="stock-ticker">{str(t).replace(".KS", "")}</div></div><div class="card-right"><div class="stock-price">{p_str}</div><div class="badge {color}">{chg_pct:+.2f}%</div></div></div></a>'
        except: continue
    html_stock += '</div>'
    st.markdown(html_stock, unsafe_allow_html=True)
    st.caption("※ PER 15 미만, PBR 1.5 미만, 내년 EPS 상향 등의 저평가 스크리닝 조건을 접목하여 관리할 수 있습니다[cite: 1].")


# ==========================================
# 🧠 7. 마인드셋
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
    import urllib.parse
    for i, guru in enumerate(random.sample(gurus, 4)):
        yt = f"https://www.youtube.com/results?search_query={urllib.parse.quote(guru['search'])}&sp=CAM%253D"
        msg = f"**{guru['name']}**\n\n> \"{random.choice(guru['quotes'])}\"\n\n[▶️ 관련 영상 보기]({yt})"
        cols[i].info(msg) if i % 2 == 0 else cols[i].success(msg)

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