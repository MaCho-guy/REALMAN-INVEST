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
from datetime import datetime
import urllib.parse

# 1. 페이지 세팅 (반드시 최상단)
st.set_page_config(page_title="REALMAN INVEST", layout="wide", initial_sidebar_state="collapsed")

# --- 2. 다크/라이트 모드 토글 및 전역 테마 세팅 ---
col_logo, col_toggle = st.columns([8, 2])
with col_toggle:
    st.write("") # 수직 정렬 여백
    is_dark = st.toggle("🌙 다크 모드", value=True)

# 테마 동적 변수
bg_grad = "linear-gradient(135deg, #0F172A 0%, #1E293B 100%)" if is_dark else "linear-gradient(135deg, #F8FAFC 0%, #E2E8F0 100%)"
card_bg = "#1E293B" if is_dark else "#FFFFFF"
text_col = "#F8FAFC" if is_dark else "#0F172A"
sub_text = "#94A3B8" if is_dark else "#64748B"
border_col = "#334155" if is_dark else "#CBD5E1"
sec_bg = "#0F172A" if is_dark else "#1E293B"
chart_template = "plotly_dark" if is_dark else "plotly_white"
tv_theme = "dark" if is_dark else "light"

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
    
    .badge {{ font-size: 11px; font-weight: 600; margin-top: 3px; padding: 3px 6px; border-radius: 4px; color: #fff; text-align: center; }}
    .badge-up {{ background-color: #ef4444; }} 
    .badge-down {{ background-color: #3b82f6; }} 
    .badge-neutral {{ background-color: #64748B; }}
    
    .news-item {{ background-color: {card_bg}; border: 1px solid {border_col}; border-radius: 6px; padding: 10px 12px; margin-bottom: 6px; font-size: 13px; font-weight: 500; }}
    .news-item a {{ color: {text_col}; text-decoration: none; display: block; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }}
    .news-item a:hover {{ text-decoration: underline; opacity: 0.8; }}
    
    /* 탭 메뉴 스타일링 */
    div[role="tablist"] {{ justify-content: center; gap: 10px; margin-bottom: 20px; }}
    button[role="tab"] {{ font-size: 16px !important; font-weight: 700 !important; }}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

with col_logo:
    st.markdown('<div class="supreme-container"><div class="supreme-box">REALMAN INVEST</div></div>', unsafe_allow_html=True)

# 📌 4섹터 메뉴 (st.tabs를 활용해 앱처럼 부드럽게 전환)
tab_market, tab_stocks, tab_insight, tab_mind = st.tabs(["📊 시장지표", "🎯 관심종목", "📡 투자인사이트", "🧠 마인드셋"])

# --- 공통 데이터 통신 함수 ---
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

def render_tv_widget(symbol, height=400):
    html = f"""
    <div class="tradingview-widget-container" style="height:{height}px; width:100%;">
      <div id="tv_{symbol.replace(':','')}" style="height:calc(100% - 32px); width:100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
      "autosize": true, "symbol": "{symbol}", "interval": "D", "timezone": "Asia/Seoul",
      "theme": "{tv_theme}", "style": "1", "locale": "kr", "enable_publishing": false,
      "backgroundColor": "rgba(0, 0, 0, 0)", "hide_top_toolbar": false, "save_image": false,
      "container_id": "tv_{symbol.replace(':','')}"
      }});
      </script>
    </div>
    """
    components.html(html, height=height)

def render_plotly_line(series, name, color="#DA291C"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, mode='lines', name=name, line=dict(color=color, width=2)))
    fig.update_layout(template=chart_template, margin=dict(l=0, r=0, t=10, b=0), height=200, xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def draw_stock_card(name, ticker, price, change):
    color = "badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"
    p_str = f"₩{price:,.0f}" if '.KS' in str(ticker) else f"${price:,.2f}"
    return f'<a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" style="text-decoration:none;"><div class="stock-card"><div class="card-left"><div class="stock-name">{name}</div><div class="stock-ticker">{str(ticker).replace(".KS", "")}</div></div><div class="card-right"><div class="stock-price">{p_str}</div><div class="badge {color}">{change:+.2f}%</div></div></div></a>'


# ==========================================
# 📊 섹터 1: 시장지표 (Jusikbot 스타일)
# ==========================================
with tab_market:
    st.markdown('<div class="section-title">ADR (시장 체력) & 메인 차트</div>', unsafe_allow_html=True)
    krx_adr = fetch_krx_adr()
    
    sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs(["KOSPI", "KOSDAQ", "NASDAQ", "S&P 500"])
    def render_index_tab(market, symbol, up, dn):
        c1, c2 = st.columns([1, 3])
        with c1:
            if up > 0 or dn > 0:
                adr = (up/dn*100) if dn > 0 else 0
                st.metric(f"{market} 실시간 ADR", f"{adr:.1f}%", f"상승 {up} / 하락 {dn}")
                st.caption("※ 120% 이상 과열 / 75% 이하 바닥")
            else:
                st.metric(f"{market}", "글로벌 지수", "차트 전용")
        with c2:
            render_tv_widget(symbol, height=350)

    with sub_tab1: render_index_tab("KOSPI", "KRX:KOSPI", krx_adr["KOSPI"][0], krx_adr["KOSPI"][1])
    with sub_tab2: render_index_tab("KOSDAQ", "KRX:KOSDAQ", krx_adr["KOSDAQ"][0], krx_adr["KOSDAQ"][1])
    with sub_tab3: render_index_tab("NASDAQ", "NASDAQ:NDX", 0, 0)
    with sub_tab4: render_index_tab("S&P 500", "SP:SPX", 0, 0)

    st.markdown('<div class="section-title">위험지표 (Risk Indicators)</div>', unsafe_allow_html=True)
    
    st.markdown("###### 📉 KOSPI / KOSDAQ 20일 이격도")
    try:
        h_kpi, h_kdq = yf.Ticker('^KS11').history(period="1y")['Close'], yf.Ticker('^KQ11').history(period="1y")['Close']
        disp_kpi, disp_kdq = (h_kpi / h_kpi.rolling(20).mean() * 100).dropna(), (h_kdq / h_kdq.rolling(20).mean() * 100).dropna()
        
        fig_disp = go.Figure()
        fig_disp.add_trace(go.Scatter(x=disp_kpi.index, y=disp_kpi.values, name='KOSPI 이격도', line=dict(color='#DA291C')))
        fig_disp.add_trace(go.Scatter(x=disp_kdq.index, y=disp_kdq.values, name='KOSDAQ 이격도', line=dict(color='#3b82f6')))
        fig_disp.add_hline(y=105, line_dash="dot", line_color="red", annotation_text="과열 (105)")
        fig_disp.add_hline(y=95, line_dash="dot", line_color="blue", annotation_text="침체 (95)")
        fig_disp.update_layout(template=chart_template, height=300, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_disp, use_container_width=True)
    except: st.error("이격도 차트 로딩 실패")

    st.divider()
    
    g_cols = st.columns(4)
    vix = yf.Ticker('^VIX').history(period="2d")
    v_val, v_chg = (vix['Close'].iloc[-1], vix['Close'].iloc[-1]-vix['Close'].iloc[-2]) if len(vix)>1 else (0,0)
    g_cols[0].metric("VIX (공포지수)", f"{v_val:.2f}", f"{v_chg:+.2f}", delta_color="inverse")
    
    t10, t03 = yf.Ticker('^TNX').history(period="1d")['Close'], yf.Ticker('^IRX').history(period="1d")['Close']
    spread = (t10.iloc[-1] - t03.iloc[-1]) if (not t10.empty and not t03.empty) else 0
    g_cols[1].metric("장단기 금리차(10y-3m)", f"{spread:.2f}%p", "침체 경고" if spread < 0 else "정상", delta_color="off")
    
    fg_val, fg_txt = 0, "수집 불가"
    try:
        res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        if res.status_code == 200: fg_val, fg_txt = round(res.json()['fear_and_greed']['score']), res.json()['fear_and_greed']['rating']
    except: pass
    g_cols[2].metric("CNN 공탐지수", f"{fg_val}점", fg_txt, delta_color="off")
    
    hyg = yf.Ticker('HYG').history(period="2d")
    h_val, h_chg = (hyg['Close'].iloc[-1], hyg['Close'].iloc[-1]-hyg['Close'].iloc[-2]) if len(hyg)>1 else (0,0)
    g_cols[3].metric("하이일드(HYG) 채권", f"${h_val:.2f}", f"{h_chg:+.2f} (하락시 위험)", delta_color="normal")

    k_cols = st.columns(2)
    with k_cols[0]:
        st.markdown("###### 🇰🇷 VKOSPI (코스피 변동성)")
        vkospi = yf.Ticker('^VKOSPI').history(period="6mo")['Close']
        render_plotly_line(vkospi, "VKOSPI", "#f59e0b")
    with k_cols[1]:
        st.markdown("###### 🇰🇷 KOSPI 신고가-신저가 프록시 (%)")
        ksp_1y = yf.Ticker('^KS11').history(period="1y")['Close']
        h52, l52 = ksp_1y.rolling(252).max().dropna(), ksp_1y.rolling(252).min().dropna()
        nh_nl = ((ksp_1y.loc[h52.index] - l52) / (h52 - l52) * 100).tail(120)
        render_plotly_line(nh_nl, "52주 위치", "#10b981")

    st.markdown('<div class="section-title">주요지수 연도별 수익률</div>', unsafe_allow_html=True)
    df_ret = get_annual_returns()
    fig_bar = px.bar(df_ret, barmode='group', template=chart_template, text_auto='.1f')
    fig_bar.update_layout(height=350, xaxis_title="연도", yaxis_title="수익률 (%)", legend_title="지수")
    st.plotly_chart(fig_bar, use_container_width=True)


# ==========================================
# 🎯 섹터 2: 관심종목 (Watchlist & Screening)
# ==========================================
with tab_stocks:
    st.markdown('<div class="section-title">내 관심종목 (Watchlist)</div>', unsafe_allow_html=True)
    my_stocks = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 'O', 'SCHD', '005930.KS', '000660.KS']
    
    html_stock = '<div class="card-grid">'
    for t in my_stocks:
        hist = yf.Ticker(t).history(period="2d")
        if len(hist) >= 2:
            close_tdy, close_ytd = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
            chg_pct = ((close_tdy - close_ytd) / close_ytd) * 100
            d_name = '삼성전자' if t == '005930.KS' else 'SK하이닉스' if t == '000660.KS' else t
            html_stock += draw_stock_card(d_name, t, close_tdy, chg_pct)
    html_stock += '</div>'
    st.markdown(html_stock, unsafe_allow_html=True)

    st.markdown('<div class="section-title">우량주 스크리닝 (52주 신고가 & 가치주)</div>', unsafe_allow_html=True)
    st.info("💡 사이트 부하 방지를 위해 아래쪽 종목은 자동 스크리닝 시점의 데이터를 기반으로 합니다.")


# ==========================================
# 📡 섹터 3: 투자인사이트
# ==========================================
with tab_insight:
    st.markdown('<div class="section-title">최신 투자 인사이트</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### 🌍 거시 경제 뉴스")
        try:
            for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:6]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass
    with c2:
        st.markdown("##### 🎯 관심종목 뉴스")
        try:
            for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=애플+OR+테슬라+OR+삼성전자+OR+SK하이닉스+OR+엔비디아&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:6]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass
    with c3:
        st.markdown("##### 📝 이웃 블로그 최신글")
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
    <div style="font-size: 14px; color: {text_col}; background-color: {sec_bg}; padding: 20px; border-radius: 8px; line-height: 1.8; border-left: 4px solid #DA291C;">
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