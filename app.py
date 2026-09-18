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

# --- 1. 모바일 최적화 다크 박스 UI & 슈프림 로고 배경 (CSS) ---
custom_css = """
<style>
    .stApp { background: linear-gradient(135deg, #E2E8F0 0%, #CBD5E1 100%); }
    #MainMenu, footer, header {visibility: hidden;}
    
    /* 📌 반응형 슈프림(SUPREME) 로고 */
    .supreme-container { display: flex; justify-content: center; margin-top: 5px; margin-bottom: 25px; }
    .supreme-box { 
        background-color: #DA291C; color: #FFFFFF; border-radius: 2px; 
        text-align: center; font-family: 'Futura', 'Trebuchet MS', sans-serif;
        font-weight: 900; font-style: italic; text-transform: uppercase;
        box-shadow: 0 6px 12px rgba(218, 41, 28, 0.3);
        font-size: 40px !important; padding: 6px 24px; letter-spacing: -2px;
    }
    
    .section-title { 
        background-color: #1E293B; color: #FFFFFF; padding: 10px 16px; border-radius: 6px; 
        font-size: 17px; font-weight: 700; margin-top: 35px; margin-bottom: 15px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); letter-spacing: -0.5px;
    }
    
    /* 모바일 2열 배치 (CSS Grid) */
    .card-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
    }
    @media (min-width: 768px) {
        .card-grid { grid-template-columns: repeat(3, 1fr); gap: 12px; }
        .supreme-box { font-size: 48px !important; padding: 8px 30px; }
    }
    
    .card-link { text-decoration: none !important; color: inherit !important; display: block; }
    .card-link:hover .stock-card { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
    
    .stock-card { 
        background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; 
        padding: 12px 14px; display: flex; justify-content: space-between; 
        align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.03); transition: all 0.2s ease-in-out; 
    }
    .card-left { display: flex; flex-direction: column; overflow: hidden; }
    .stock-name { font-size: 14px; font-weight: 700; color: #0F172A; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
    .stock-ticker { font-size: 11px; font-weight: 500; color: #64748B; margin-top: 1px; }
    .card-right { display: flex; flex-direction: column; align-items: flex-end; }
    .stock-price { font-size: 14px; font-weight: 700; color: #0F172A; }
    
    .badge { font-size: 11px; font-weight: 600; margin-top: 3px; padding: 2px 6px; border-radius: 4px; }
    .badge-up { background-color: #DCFCE7; color: #166534; }
    .badge-down { background-color: #FEE2E2; color: #991B1B; }
    .badge-neutral { background-color: #F1F5F9; color: #475569; }
    
    .news-item { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 10px 12px; margin-bottom: 6px; font-size: 13px; font-weight: 500; }
    .news-item a { color: #0F172A; text-decoration: none; display: block; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
    .news-item a:hover { color: #2563EB; text-decoration: underline; }

    /* 📌 마인드셋 소형 카드 전용 스타일 */
    .guru-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .guru-header { font-size: 13px; font-weight: 700; color: #0F172A; margin-bottom: 4px; }
    .guru-quote { font-size: 12px; color: #475569; font-style: italic; margin-bottom: 8px; line-height: 1.4; }
    .guru-link { font-size: 11px; font-weight: 600; }
    .guru-link a { color: #2563EB; text-decoration: none; }
    .guru-link a:hover { text-decoration: underline; }
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

try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://edition.cnn.com/'
    }
    res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers=headers, timeout=5)
    if res.status_code == 200:
        fg = res.json()['fear_and_greed']
        macro_data['CNN 공탐지수'] = {"price": round(fg['score']), "change": fg['rating']}
    else:
        macro_data['CNN 공탐지수'] = {"price": 0, "change": "수집 불가"}
except:
    macro_data['CNN 공탐지수'] = {"price": 0, "change": "수집 불가"}

html_macro = '<div class="card-grid">'
for name, data in macro_data.items():
    html_macro += draw_macro_card(name, data['price'], data['change'])
html_macro += '</div>'
st.markdown(html_macro, unsafe_allow_html=True)

# --- 5. 관심 종목 현황 ---
st.markdown('<div class="section-title">관심 종목 현황</div>', unsafe_allow_html=True)
my_stocks = ['AAPL', 'AMT', 'BAC', 'CRCL', 'GOOGL', 'MSFT', 'MU', 'O', 'QQQ', 'SCHD', 'SOXX', 'UNH', '005930.KS', '000660.KS']
stock_data = []
for t in my_stocks:
    hist = yf.Ticker(t).history(period="2d")
    if len(hist) >= 2: stock_data.append({'ticker': t, 'price': hist['Close'].iloc[-1], 'change': ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100})

html_stock = '<div class="card-grid">'
for stock in stock_data:
    display_name = '삼성전자' if stock['ticker'] == '005930.KS' else 'SK하이닉스' if stock['ticker'] == '000660.KS' else stock['ticker']
    html_stock += draw_stock_card(display_name, stock['ticker'], stock['price'], stock['change'])
html_stock += '</div>'
st.markdown(html_stock, unsafe_allow_html=True)

# --- 6. 시장별 우량주 스크리닝 ---
st.markdown('<div class="section-title">시장별 우량주 스크리닝</div>', unsafe_allow_html=True)
st.caption("※ 수동 업데이트 필요")
if st.button("🔄 스크리닝 DB 최신화"):
    with st.spinner("병렬 스크리닝 진행 중..."): 
        update_market_db()
    st.success("업데이트 완료!")

if os.path.exists(DB_FILE):
    screen_data = pd.read_csv(DB_FILE).to_dict('records')
    tab1, tab2 = st.tabs(["52주 신고가", "저평가&우상향"])

    with tab1:
        with st.expander("💡 '52주 신고가' 스크리닝 기준 보기"):
            st.markdown("""
            <div style="font-size:13px; color:#475569;">
            ✔️ <b>52주 신고가 근접</b> : 현재 주가가 최근 1년(52주) 최고점 대비 <b>5% 이내(95% 이상)</b>에 위치한 강한 상승 추세의 종목
            </div>
            """, unsafe_allow_html=True)
            
        for market in ['NASDAQ', 'S&P 500', 'KOSPI']:
            st.markdown(f"<h6 style='margin-top: 15px; margin-bottom: 8px; color: #1E293B;'>{market}</h6>", unsafe_allow_html=True)
            high_stocks = [s for s in screen_data if s['market'] == market and s['price'] >= s['high52'] * 0.95]
            if high_stocks:
                html_screen = '<div class="card-grid">'
                for s in high_stocks: html_screen += draw_stock_card(s['ticker'], s['ticker'], s['price'], None, "신고가 근접")
                html_screen += '</div>'
                st.markdown(html_screen, unsafe_allow_html=True)
            else:
                st.caption("해당 종목 없음")
                
    with tab2:
        with st.expander("💡 '저평가 & EPS 우상향' 스크리닝 기준 보기"):
            st.markdown("""
            <div style="font-size:13px; color:#475569; line-height: 1.6;">
            ✔️ <b>PER (주가수익비율)</b> : 0 초과 ~ 15 미만<br>
            ✔️ <b>PBR (주가순자산비율)</b> : 0 초과 ~ 1.5 미만<br>
            ✔️ <b>EPS (주당순이익) 우상향</b> : 과거 1년간 흑자를 기록했으며, 내년 예상 실적이 과거 실적보다 높은 성장 기업
            </div>
            """, unsafe_allow_html=True)
            
        for market in ['NASDAQ', 'S&P 500', 'KOSPI']:
            st.markdown(f"<h6 style='margin-top: 15px; margin-bottom: 8px; color: #1E293B;'>{market}</h6>", unsafe_allow_html=True)
            value_stocks = [s for s in screen_data if s['market'] == market and 0 < s['per'] < 15 and 0 < s['pbr'] < 1.5 and s['eps_growth']]
            if value_stocks:
                html_screen = '<div class="card-grid">'
                for s in value_stocks: html_screen += draw_stock_card(s['ticker'], s['ticker'], s['price'], None, f"PER {s['per']:.1f}")
                html_screen += '</div>'
                st.markdown(html_screen, unsafe_allow_html=True)
            else:
                st.caption("해당 종목 없음")
else:
    st.warning("☝️ [스크리닝 DB 최신화] 버튼을 눌러주세요!")

# --- 7. 인사이트 보드 ---
st.markdown('<div class="section-title">인사이트 보드</div>', unsafe_allow_html=True)
c_mac, c_stk, c_blg = st.columns(3)
with c_mac:
    st.markdown("##### 거시 경제")
    try:
        for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=거시경제+주식+금리&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:4]: 
            st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
    except: pass
with c_stk:
    st.markdown("##### 관심종목")
    try:
        for item in ET.fromstring(requests.get("https://news.google.com/rss/search?q=애플+OR+마이크로소프트+OR+테슬라+OR+삼성전자+OR+SK하이닉스&hl=ko&gl=KR&ceid=KR:ko").content).findall('.//item')[:4]: 
            st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank">{item.find("title").text}</a></div>', unsafe_allow_html=True)
    except: pass
with c_blg:
    st.markdown("##### 이웃 블로그")
    for name, url in [("jeunkim", "https://rss.blog.naver.com/jeunkim"), ("crush21", "https://rss.blog.naver.com/crush212121")]:
        try:
            for item in ET.fromstring(requests.get(url).content).findall('.//item')[:2]: 
                st.markdown(f'<div class="news-item"><a href="{item.find("link").text}" target="_blank"><b>[{name}]</b> {item.find("title").text}</a></div>', unsafe_allow_html=True)
        except: pass

# --- 8. 마인드셋 (소형 컴팩트 카드 적용) ---
st.markdown('<div class="section-title">마인드셋</div>', unsafe_allow_html=True)
gurus = [
    {"name": "워런 버핏", "emoji": "👴", "search": "워런 버핏 투자 조언", "quotes": ["위대한 기업을 적당한 가격에 사는 것이 훨씬 낫다.", "원칙 1: 절대 돈을 잃지 마라."]},
    {"name": "찰리 멍거", "emoji": "👓", "search": "찰리 멍거 명언", "quotes": ["바보 같은 짓을 피하는 것이 중요하다.", "이해하지 못하는 것에는 절대 투자하지 마라."]},
    {"name": "피터 린치", "emoji": "🏃‍♂️", "search": "피터 린치 강연", "quotes": ["가장 중요한 기관은 뇌가 아니라 위장(인내심)이다.", "기업 수익이 우상향하면 주가도 우상향한다."]},
    {"name": "코스톨라니", "emoji": "🎩", "search": "앙드레 코스톨라니", "quotes": ["투자는 머리로 하는 것이 아니라 엉덩이로 하는 것이다.", "주가는 결국 기업의 가치로 회귀한다."]},
    {"name": "레이 달리오", "emoji": "🌐", "search": "레이 달리오 원칙", "quotes": ["시장이 어떻게 움직일지 예측하려 하지 마라.", "고통에 반성을 더하면 발전이 된다."]},
    {"name": "존 보글", "emoji": "⛵", "search": "존 보글 인덱스 펀드", "quotes": ["모든 주식을 소유하라.", "투자의 핵심은 비용을 최소화하는 것이다."]}
]

selected_gurus = random.sample(gurus, 4)

def draw_guru_card(guru):
    yt_url = f"https://www.youtube.com/results?search_query={guru['search'].replace(' ', '+')}&sp=CAM%253D"
    q = random.choice(guru['quotes'])
    return f"""
    <div class="guru-card">
        <div class="guru-header">{guru['emoji']} {guru['name']}</div>
        <div class="guru-quote">"{q}"</div>
        <div class="guru-link"><a href="{yt_url}" target="_blank">▶️ 영상 보기 (조회수 순)</a></div>
    </div>
    """

col1, col2 = st.columns(2)
with col1:
    st.markdown(draw_guru_card(selected_gurus[0]), unsafe_allow_html=True)
    st.markdown(draw_guru_card(selected_gurus[1]), unsafe_allow_html=True)
with col2:
    st.markdown(draw_guru_card(selected_gurus[2]), unsafe_allow_html=True)
    st.markdown(draw_guru_card(selected_gurus[3]), unsafe_allow_html=True)

# --- 9. 하락장에서 얻은 깨달음 ---
st.markdown('<div class="section-title" style="font-size: 14px; margin-top: 40px; margin-bottom: 10px;">하락장에서 얻은 깨달음</div>', unsafe_allow_html=True)
st.markdown("""
<div style="font-size: 11px; color: #64748B; background-color: rgba(255, 255, 255, 0.4); padding: 10px 14px; border-radius: 6px; border: 1px solid #E2E8F0; line-height: 1.5; margin-bottom: 20px;">
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