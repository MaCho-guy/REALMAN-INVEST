import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import random
import os
import concurrent.futures
import urllib.parse

# 1. 대시보드 제목 세팅
st.set_page_config(page_title="REALMAN INVEST", layout="wide")

# --- 1. 모던 다크 박스 UI & 슈프림 로고 배경 (CSS) ---
custom_css = """
<style>
    .stApp { background: linear-gradient(135deg, #E2E8F0 0%, #CBD5E1 100%); }
    #MainMenu, footer, header {visibility: hidden;}
    
    /* 📌 슈프림(SUPREME) 로고 스타일 */
    .supreme-container { display: flex; justify-content: center; margin-top: 10px; margin-bottom: 30px; }
    .supreme-box { 
        background-color: #DA291C; color: #FFFFFF; padding: 8px 30px; border-radius: 2px; 
        text-align: center; font-family: 'Futura', 'Trebuchet MS', sans-serif;
        font-size: 48px !important; font-weight: 900; font-style: italic; 
        letter-spacing: -2px; box-shadow: 0 8px 16px rgba(218, 41, 28, 0.3); text-transform: uppercase;
    }
    
    .section-title { 
        background-color: #1E293B; color: #FFFFFF; padding: 12px 20px; border-radius: 8px; 
        font-size: 19px; font-weight: 700; margin-top: 40px; margin-bottom: 20px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); letter-spacing: -0.5px;
    }
    
    .card-link { text-decoration: none !important; color: inherit !important; display: block; }
    .card-link:hover .stock-card { transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0,0,0,0.1); }
    
    .stock-card { 
        background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; 
        padding: 16px 20px; margin-bottom: 12px; display: flex; justify-content: space-between; 
        align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.03); transition: all 0.2s ease-in-out; 
    }
    .card-left { display: flex; flex-direction: column; }
    .stock-name { font-size: 16px; font-weight: 700; color: #0F172A; }
    .stock-ticker { font-size: 13px; font-weight: 500; color: #64748B; margin-top: 2px; }
    .card-right { display: flex; flex-direction: column; align-items: flex-end; }
    .stock-price { font-size: 16px; font-weight: 700; color: #0F172A; }
    
    .badge { font-size: 13px; font-weight: 600; margin-top: 4px; padding: 4px 8px; border-radius: 6px; }
    .badge-up { background-color: #DCFCE7; color: #166534; }
    .badge-down { background-color: #FEE2E2; color: #991B1B; }
    .badge-neutral { background-color: #F1F5F9; color: #475569; }
    
    .news-item { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; font-size: 14px; font-weight: 500; }
    .news-item a { color: #0F172A; text-decoration: none; }
    .news-item a:hover { color: #2563EB; text-decoration: underline; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)
st.markdown('<div class="supreme-container"><div class="supreme-box">REALMAN INVEST</div></div>', unsafe_allow_html=True)

# --- 2. 멀티스레딩 스크리닝 DB 세팅 ---
DB_FILE = "market_db.csv"

def fetch_single_stock(ticker, market):
    try:
        tkr = yf.Ticker(ticker)
        hist = tkr.history(period="1mo")
        if hist.empty: return None
        info = tkr.info
        price = hist['Close'].iloc[-1]
        t_eps, f_eps = info.get('trailingEps', 0), info.get('forwardEps', 0)
        return {
            'market': market, 'ticker': ticker, 'price': price, 
            'high52': info.get('fiftyTwoWeekHigh', price), 'per': info.get('trailingPE', 0), 
            'pbr': info.get('priceToBook', 0), 'eps_growth': (f_eps > t_eps) and (t_eps > 0)
        }
    except: return None

def update_market_db():
    universe = {
        'NASDAQ': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'PEP', 'COST'],
        'S&P 500': ['BRK-B', 'UNH', 'JNJ', 'JPM', 'V', 'PG', 'MA', 'HD', 'CVX', 'ABBV'],
        'KOSPI': ['005930.KS', '000660.KS', '373220.KS', '207940.KS', '005380.KS', '000270.KS']
    }
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_single_stock, t, m) for m, tickers in universe.items() for t in tickers]
        for future in concurrent.futures.as_completed(futures):
            if future.result(): results.append(future.result())
    pd.DataFrame(results).to_csv(DB_FILE, index=False)

with st.sidebar:
    st.markdown("### 시스템 관리")
    if st.button("스크리닝 DB 최신화"):
        with st.spinner("병렬 스크리닝 진행 중..."): update_market_db()
        st.success("데이터베이스 업데이트 완료!")

# --- 3. UI 컴포넌트 렌더링 함수 ---
def draw_macro_card(name, price, change):
    if name == '원/달러 환율':
        p_str, c_str, color_class = f"₩{price:,.2f}", f"{change:+.2f}원", "badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"
    elif name == '미 10년물 국채':
        p_str, c_str, color_class = f"{price:.3f}%", f"{change:+.3f}%p", "badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"
    elif name == 'CNN 공탐지수':
        p_str, c_str, color_class = f"{price} 점", str(change), "badge-neutral"
    else:
        p_str, c_str = (f"${price:,.2f}" if '원유' in name else f"{price:,.2f}"), f"{change:+.2f}"
        color_class = "badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"
        
    return f'<div class="stock-card"><div class="card-left"><div class="stock-name">{name}</div></div><div class="card-right"><div class="stock-price">{p_str}</div><div class="badge {color_class}">{c_str}</div></div></div>'

def draw_stock_card(name, ticker, price, change=None, extra_info=""):
    badge_html = f'<div class="badge {"badge-up" if change > 0 else "badge-down" if change < 0 else "badge-neutral"}">{"+" if change > 0 else ""}{change:.2f}%</div>' if change is not None else f'<div class="badge badge-neutral">{extra_info}</div>'
    price_str = f"₩{price:,.0f}" if '.KS' in str(ticker) else f"${price:,.2f}"
    return f'<a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" class="card-link"><div class="stock-card"><div class="card-left"><div class="stock-name">{name}</div><div class="stock-ticker">{str(ticker).replace(".KS", "")}</div></div><div class="card-right"><div class="stock-price">{price_str}</div>{badge_html}</div></div></a>'

# --- 4. 거시 경제 지표 ---
st.markdown('<div class="section-title">거시 경제 지표</div>', unsafe_allow_html=True)
macro_data = {}

for name, ticker in {'미 10년물 국채': '^TNX', 'WTI 원유': 'CL=F', 'S&P 500': '^GSPC', '원/달러 환율': 'KRW=X', 'VIX (변동성)': '^VIX'}.items():
    hist = yf.Ticker(ticker).history(period="2d")
    macro_data[name] = {"price": hist['Close'].iloc[-1], "change": hist['Close'].iloc[-1] - hist['Close'].iloc[-2]} if len(hist) >= 2 else {"price": hist['Close'].iloc[-1], "change": 0.0}

# 🚨 CNN 공탐지수 스크래핑 안전장치 완벽 적용 (에러 방지)
try:
    res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
    if res.status_code == 200:
        fg = res.json()['fear_and_greed']
        macro_data['CNN 공탐지수'] = {"price": round(fg['score']), "change": fg['rating']}
    else:
        macro_data['CNN 공탐지수'] = {"price": 0, "change": "수집 불가"}
except:
    macro_data['CNN 공탐지수'] = {"price": 0, "change": "수집 불가"}

cols = st.columns(3)
for i, (name, data) in enumerate(macro_data.items()):
    with cols[i % 3]: st.markdown(draw_macro_card(name, data['price'], data['change']), unsafe_allow_html=True)

# --- 5. 관심 종목 현황 ---
st.markdown('<div class="section-title">관심 종목 현황</div>', unsafe_allow_html=True)
my_stocks = ['AAPL', 'AMT', 'BAC', 'CRCL', 'GOOGL', 'MSFT', 'MU', 'O', 'QQQ', 'SCHD', 'SOXX', 'UNH', '005930.KS', '000660.KS']
stock_data = []
for t in my_stocks:
    hist = yf.Ticker(t).history(period="2d")
    if len(hist) >= 2: stock_data.append({'ticker': t, 'price': hist['Close'].iloc[-1], 'change': ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100})

cols = st.columns(3)
for idx, stock in enumerate(stock_data):
    display_name = '삼성전자' if stock['ticker'] == '005930.KS' else 'SK하이닉스' if stock['ticker'] == '000660.KS' else stock['ticker']
    with cols[idx % 3]: st.markdown(draw_stock_card(display_name, stock['ticker'], stock['price'], stock['change']), unsafe_allow_html=True)

# --- 6. 시장별 우량주 스크리닝 ---
st.markdown('<div class="section-title">시장별 우량주 스크리닝</div>', unsafe_allow_html=True)
if os.path.exists(DB_FILE):
    screen_data = pd.read_csv(DB_FILE).to_dict('records')
    tab1, tab2 = st.tabs(["52주 신고가 근접 (5% 이내)", "저평가 & EPS 우상향"])

    with tab1:
        cols = st.columns(3)
        for col, market in zip(cols, ['NASDAQ', 'S&P 500', 'KOSPI']):
            with col:
                st.markdown(f"**{market}**")
                for s in [s for s in screen_data if s['market'] == market and s['price'] >= s['high52'] * 0.95]: 
                    st.markdown(draw_stock_card(s['ticker'], s['ticker'], s['price'], None, "신고가 근접"), unsafe_allow_html=True)
    with tab2:
        cols = st.columns(3)
        for col, market in zip(cols, ['NASDAQ', 'S&P 500', 'KOSPI']):
            with col:
                st.markdown(f"**{market}**")
                for s in [s for s in screen_data if s['market'] == market and 0 < s['per'] < 15 and 0 < s['pbr'] < 1.5 and s['eps_growth']]: 
                    st.markdown(draw_stock_card(s['ticker'], s['ticker'], s['price'], None, f"PER {s['per']:.1f}"), unsafe_allow_html=True)
else:
    st.warning("왼쪽 사이드바에서 [스크리닝 DB 최신화] 버튼을 눌러주세요!")

# --- 7. 인사이트 보드 ---
st.markdown('<div class="section-title">인사이트 보드</div>', unsafe_allow_html=True)
c_mac, c_stk, c_blg = st.columns(3, gap="medium")
with c_mac:
    st.markdown("##### 거시 경제 뉴스")
    try:
        for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:5]: 
            st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
    except: pass
with c_stk:
    st.markdown("##### 관심종목 뉴스")
    try:
        for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=애플+OR+마이크로소프트+OR+테슬라+OR+삼성전자+OR+SK하이닉스&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:5]: 
            st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
    except: pass
with c_blg:
    st.markdown("##### 이웃 블로그 최신글")
    for name, url in [("jeunkim", "https://rss.blog.naver.com/jeunkim"), ("crush21", "https://rss.blog.naver.com/crush212121")]:
        try:
            for item in ET.fromstring(requests.get(url).content).findall('.//item')[:3]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank"><b>[{name}]</b> {item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass

# --- 8. 마인드셋 ---
st.markdown('<div class="section-title">마인드셋</div>', unsafe_allow_html=True)
gurus = [
    {"name": "워런 버핏", "emoji": "👴", "search": "워런 버핏 투자 조언", "quotes": ["위대한 기업을 적당한 가격에 사는 것이 훨씬 낫다.", "원칙 1: 절대 돈을 잃지 마라."]},
    {"name": "찰리 멍거", "emoji": "👓", "search": "찰리 멍거 명언", "quotes": ["단순히 똑똑한 것보다, 바보 같은 짓을 피하는 것이 중요하다.", "이해하지 못하는 것에는 절대 투자하지 마라."]},
    {"name": "피터 린치", "emoji": "🏃‍♂️", "search": "피터 린치 강연", "quotes": ["주식 시장에서 가장 중요한 기관은 뇌가 아니라 위장(인내심)이다.", "기업의 수익이 우상향하면 주가도 우상향한다."]},
    {"name": "앙드레 코스톨라니", "emoji": "🎩", "search": "앙드레 코스톨라니", "quotes": ["투자는 머리로 하는 것이 아니라 엉덩이로 하는 것이다.", "주가는 결국 기업의 가치로 회귀한다."]},
    {"name": "레이 달리오", "emoji": "🌐", "search": "레이 달리오 원칙", "quotes": ["시장이 어떻게 움직일지 예측하려 하지 마라.", "고통에 반성을 더하면 발전이 된다."]},
    {"name": "존 보글", "emoji": "⛵", "search": "존 보글 인덱스 펀드", "quotes": ["모든 주식을 소유하라.", "투자의 핵심은 비용을 최소화하는 것이다."]}
]

selected = random.sample(gurus, 4)
cols = st.columns(2) + st.columns(2)
for i, guru in enumerate(selected):
    yt = f"https://www.youtube.com/results?search_query={urllib.parse.quote(guru['search'])}&sp=CAM%253D"
    msg = f"**{guru['emoji']} {guru['name']}**\n\n> \"{random.choice(guru['quotes'])}\"\n\n[▶️ 관련 유튜브 영상 보기 (조회수 순)]({yt})"
    if i % 2 == 0: cols[i].info(msg)
    else: cols[i].success(msg)

# --- 9. 하락장에서 얻은 깨달음 (디자인 대폭 축소) ---
st.markdown('<div class="section-title" style="font-size: 15px; margin-top: 50px;">하락장에서 얻은 깨달음</div>', unsafe_allow_html=True)
st.markdown("""
<div style="font-size: 12px; color: #64748B; background-color: rgba(255, 255, 255, 0.5); padding: 12px 16px; border-radius: 6px; border: 1px solid #E2E8F0; line-height: 1.6;">
<b>1.</b> 급격한 상승이나 하락세에 올라타지 마라. 기울기는 완만해지는 때가 오며 그때가 매수, 매도 타이밍이다.<br>
<b>2.</b> 시장은 항상 낙관론, 비관론에 쏠리기 마련이다. 과도한 비관론에 매수하라.<br>
<b>3.</b> 전문가라고 하는 사람들도 잘 모른다. 장담하는 사람이 있다면 사기꾼이다.<br>
<b>4.</b> 오른 만큼 떨어지는 것도 가파르며 그 사이 구간에서 수익을 챙겨서 나오는 것은 어렵다.<br>
<b>5.</b> 큰 자본을 한 번에 투하하지 마라. 분할 매수해라.<br>
<b>6.</b> 손절도 할 줄 알아야 한다. 그게 싫으면 인내심을 길러라.<br>
<b>7.</b> 나만 소외된 것 같은 느낌이 들 때가 가장 참아야 할 때이다.<br>
<b>8.</b> 가치분석은 남에게 맡기지 말고 직접 해라.<br>
<b>9.</b> 산업의 기술을 잘 안다고 해서 그 기업의 주가를 잘 아는 것은 아니다.
</div>
""", unsafe_allow_html=True)