import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import pytz
from datetime import datetime, time

# ==========================================
# PENGATURAN HALAMAN & CEK JAM BURSA
# ==========================================
st.set_page_config(page_title="Super Scanner Saham", layout="centered", page_icon="📈")

tz_jkt = pytz.timezone('Asia/Jakarta')
waktu_sekarang = datetime.now(tz_jkt)
hari_ini = waktu_sekarang.weekday()
jam_sekarang = waktu_sekarang.time()
tanggal_sekarang = waktu_sekarang.strftime('%Y-%m-%d')

libur_bursa = [
    '2026-01-01', '2026-02-16', '2026-03-19', '2026-03-20', '2026-04-03', 
    '2026-04-10', '2026-04-13', '2026-04-14', '2026-05-01', '2026-05-14', 
    '2026-06-01', '2026-08-17', '2026-12-25'
]

market_buka = (hari_ini < 5) and (time(9, 0) <= jam_sekarang <= time(16, 0)) and (tanggal_sekarang not in libur_bursa)

if market_buka:
    st_autorefresh(interval=60000, limit=2000, key="data_refresh") 
    status_market = "🟢 MARKET BUKA"
else:
    status_market = "🔴 MARKET TUTUP"

# ==========================================
# INJEKSI DESAIN CUSTOM (CSS)
# ==========================================
st.markdown("""
<style>
    [data-testid="stMetric"] { background-color: #121212; border: 1px solid #2a2a2a; padding: 15px 20px; border-radius: 2px; }
    [data-testid="stMetricLabel"] { color: #a0a0a0 !important; font-weight: 600; letter-spacing: 1px; }
    [data-testid="stMetricValue"] { color: #ffffff !important; }
    hr { border: 0; height: 1px; background: #2a2a2a; margin: 20px 0; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# FUNGSI HELPER
# ==========================================
def highlight_signal(val):
    if isinstance(val, str):
        if 'BULLISH' in val: return 'color: #81c784; font-weight: bold;'
        elif 'OVERSOLD' in val: return 'color: #4dd0e1; font-weight: bold;'
        elif 'BEARISH' in val: return 'color: #e57373; font-weight: bold;'
    return ''

def format_volume(vol):
    if vol >= 1_000_000: return f"{vol/1_000_000:.1f}M"
    elif vol >= 1_000: return f"{vol/1_000:.1f}K"
    return str(vol)

# ==========================================
# FUNGSI CACHING & DATA FETCHING
# ==========================================
@st.cache_data(ttl=60)
def fetch_stock_data(ticker_symbol):
    try: return yf.Ticker(ticker_symbol).history(period="6mo")
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_stock_info(ticker_symbol):
    try: return yf.Ticker(ticker_symbol).info
    except: return None

@st.cache_data(ttl=300, max_entries=10) 
def compute_screener_data(saham_tuple):
    now_jkt = datetime.now(pytz.timezone('Asia/Jakarta'))
    csv_timestamp = now_jkt.strftime('%Y%m%d_%H%M%S')
    display_timestamp = now_jkt.strftime('%H:%M:%S')

    tickers_str = " ".join([f"{t}.JK" for t in saham_tuple])
    try: 
        batch_df = yf.download(tickers_str, period="1mo", progress=False)
    except Exception:
        return None, [], csv_timestamp, display_timestamp

    if batch_df is None or batch_df.empty:
        return None, [], csv_timestamp, display_timestamp

    hasil_scan = []
    invalid_tickers = []
    
    for s in saham_tuple:
        ticker_jk = f"{s}.JK"
        try:
            if len(saham_tuple) > 1:
                if ticker_jk in batch_df['Close'].columns and ticker_jk in batch_df['Volume'].columns:
                    close_prices = batch_df['Close'][ticker_jk].dropna()
                    vol_data = batch_df['Volume'][ticker_jk].dropna()
                else: 
                    invalid_tickers.append(s)
                    continue
            else:
                close_prices = batch_df['Close'].dropna()
                vol_data = batch_df['Volume'].dropna()

            if len(close_prices) >= 20:
                harga = close_prices.iloc[-1]
                sma20 = close_prices.rolling(window=20).mean().iloc[-1]
                volume_terakhir = vol_data.iloc[-1] if len(vol_data) > 0 else 0
                
                delta = close_prices.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean().iloc[-1]
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().iloc[-1]
                
                if pd.isna(loss) or pd.isna(gain): rsi = 50
                elif loss == 0: rsi = 100 
                else:
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                
                if harga > sma20 and rsi < 70: status = "BULLISH 🚀"
                elif rsi <= 30: status = "OVERSOLD 🟢"
                else: status = "BEARISH 📉"
                
                hasil_scan.append({
                    "Kode": s, 
                    "Harga": harga, 
                    "Sinyal": status, 
                    "RSI": round(rsi, 1),
                    "Volume": format_volume(volume_terakhir)
                })
            else:
                invalid_tickers.append(s)
        except: 
            invalid_tickers.append(s)
            
    if not hasil_scan:
        return pd.DataFrame(), invalid_tickers, csv_timestamp, display_timestamp

    return pd.DataFrame(hasil_scan).sort_values(by='RSI', ascending=True), invalid_tickers, csv_timestamp, display_timestamp

# ==========================================
# HEADER
# ==========================================
st.title("📈 Super Scanner Saham IDX")
st.caption(f"Status: {status_market} | ⚡ Cache Limit: 5 Menit | Refreshed: {waktu_sekarang.strftime('%H:%M:%S')} WIB")
st.markdown("<hr>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📉 Teknikal", "🏢 Fundamental", "📋 Live Screener", "🧮 Kalkulator"])

# ==========================================
# SIDEBAR
# ==========================================
st.sidebar.markdown("### 🔍 Pencarian Utama")
ticker_input = st.sidebar.text_input("Masukkan Kode Saham:", value="BBCA").upper().strip()
ticker = f"{ticker_input}.JK"

df_utama = fetch_stock_data(ticker)

# ==========================================
# TAB 1: ANALISIS TEKNIKAL
# ==========================================
with tab1:
    if df_utama.empty:
        st.error(f"Data untuk {ticker_input} tidak ditemukan.")
    else:
        st.markdown(f"### 📊 Analisis Teknikal: **{ticker_input}**")
        data = df_utama.copy()
        
        data['SMA_20'] = data['Close'].rolling(window=20).mean()
        data['SMA_50'] = data['Close'].rolling(window=50).mean()
        
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = np.where(loss == 0, 100, gain / loss)
        data['RSI'] = np.where(loss == 0, 100, 100 - (100 / (1 + rs)))
        
        exp1 = data['Close'].ewm(span=12, adjust=False).mean()
        exp2 = data['Close'].ewm(span=26, adjust=False).mean()
        data['MACD'] = exp1 - exp2
        data['Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
        
        harga_terakhir = data['Close'].iloc[-1]
        if len(data) >= 2:
            perubahan = harga_terakhir - data['Close'].iloc[-2]
            persen = (perubahan / data['Close'].iloc[-2]) * 100
        else:
            perubahan, persen = 0.0, 0.0
            
        st.metric(label="HARGA SAAT INI", value=f"Rp {harga_terakhir:,.0f}", delta=f"{perubahan:,.0f} ({persen:.2f}%)")
        st.markdown("<br>", unsafe_allow_html=True)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
        
        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'],
                        increasing_line_color='#ffffff', increasing_fillcolor='#ffffff',
                        decreasing_line_color='#333333', decreasing_fillcolor='#333333', name="Harga"), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=data.index, y=data['SMA_20'], opacity=0.7, line=dict(color='#888888', width=2), name='SMA 20'), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['SMA_50'], opacity=0.7, line=dict(color='#555555', width=2), name='SMA 50'), row=1, col=1)
        
        volume_colors = ['#ffffff' if row['Close'] >= row['Open'] else '#333333' for index, row in data.iterrows()]
        fig.add_trace(go.Bar(x=data.index, y=data['Volume'], marker_color=volume_colors, name="Volume"), row=2, col=1)
        
        fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                          margin=dict(l=0, r=0, t=0, b=0), xaxis_rangeslider_visible=False, showlegend=False, height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("#### Sinyal MACD")
        st.line_chart(data[['MACD', 'Signal']], height=200)
        st.markdown("#### Momentum (RSI)")
        st.line_chart(data['RSI'], height=200)

# ==========================================
# TAB 2: DATA FUNDAMENTAL
# ==========================================
with tab2:
    if df_utama.empty:
        st.warning("Perbaiki kode saham di sidebar terlebih dahulu.")
    else:
        st.markdown(f"### 🏢 Profil Perusahaan: **{ticker_input}**")
        info = fetch_stock_info(ticker)
        
        if info:
            col1, col2 = st.columns(2)
            market_cap = info.get('marketCap', 0)
            pe_ratio = info.get('trailingPE', 0)
            if market_cap > 0: col1.metric("Kapitalisasi Pasar", f"Rp {(market_cap / 1_000_000_000_000):.2f} T")
            else: col1.metric("Kapitalisasi Pasar", "N/A")
            col2.metric("P/E Ratio (PER)", f"{pe_ratio:.2f}x" if pe_ratio else "N/A")
        else:
            st.error("Data fundamental gagal ditarik dari API.")

# ==========================================
# TAB 3: LIVE SCREENER
# ==========================================
with tab3:
    st.markdown("### 📋 Fast Screener & Filter")
    
    top_liquid_idx = [
        "BBCA","BBRI","BMRI","BBNI","TLKM","ASII","GOTO","AMMN","ADRO","UNVR",
        "ICBP","KLBF","PGEO","PTBA","ITMG","MEDC","BRPT","ANTM","INCO","MDKA",
        "AKRA","AMRT","ARTO","BRIS","CPIN","EXCL","HRUM","INDF","INKP","ISAT",
        "MAPI","MBMA","PGAS","SIDO","SMGR","TPIA","BUKA","CTRA","EMTK","ESSA",
        "GGRM","SART","TOWR","ACES","BSDE","JPFA","MIKA","MNCN","MTEL","MYOR",
        "PTMP","SCMA","WIFI","WIIM","AUTO","BFIN","BMTR","CRAI","DMMX",
        "DOID","ERAA","HEAL","HMSP","INDY","JSMR","KEEN","KRYA","LSIP","MAHA",
        "MAPA","MARK","NCKL","NISP","PANI","PNBN","PNLF","PTPP","RAJA","RALS",
        "SGER","SILO","SMRA","SSIA","TAPG","TINS","TMAS","UNTR","WIKA"
    ]
    
    input_saham = st.text_input("Watchlist Manual (koma):", value="BBCA, BBRI")
    pakai_top100 = st.checkbox("➕ Gabung dgn Top Saham Liquid IDX", value=True)
    is_scanning = st.toggle("🟢 Aktifkan Auto-Scan (Tiap Refresh)", key="live_scan_toggle")
    
    if not is_scanning:
        st.session_state.scan_history = pd.DataFrame()
        st.info("💡 Aktifkan toggle 'Auto-Scan' di atas untuk memulai pemindaian pasar secara live.")
    else:
        manual_list = [s.strip().upper() for s in input_saham.split(",") if s.strip()]
        saham_tuple = tuple(dict.fromkeys(manual_list + top_liquid_idx)) if pakai_top100 else tuple(dict.fromkeys(manual_list))
        
        api_error = False
        
        with st.spinner(f"Mendownload & mengurai {len(saham_tuple)} saham (Proses instan jika di-cache)..."):
            df_scan, invalid_tickers, exact_csv_time, exact_display_time = compute_screener_data(saham_tuple)
            
        if df_scan is None:
            st.error("⚠️ Koneksi API ke Yahoo Finance terputus atau terkena Rate-Limit.")
            api_error = True 
        else:
            if invalid_tickers:
                st.warning(f"⚠️ Ticker tidak valid / Data tidak lengkap di-skip: {', '.join(invalid_tickers)}")
            
            # BUG FIXED: Hapus 'if not df_scan.empty' agar session selalu tertimpa state terbaru (termasuk state kosong)
            st.session_state.scan_history = df_scan
            st.session_state.last_scan_time = exact_display_time
            st.session_state.csv_filename = f"screener_{exact_csv_time}.csv"

        if 'scan_history' in st.session_state and not st.session_state.scan_history.empty:
            df_scan_state = st.session_state.scan_history
            
            if api_error:
                st.warning("🚨 **PERHATIAN: MENAMPILKAN DATA LAMA (STALE DATA)**. Pembaruan gagal karena gangguan koneksi API.")

            bullish_cnt = len(df_scan_state[df_scan_state['Sinyal'].str.contains('BULLISH')])
            oversold_cnt = len(df_scan_state[df_scan_state['Sinyal'].str.contains('OVERSOLD')])
            bearish_cnt = len(df_scan_state[df_scan_state['Sinyal'].str.contains('BEARISH')])
            
            st.markdown("##### 📈 Ringkasan Pasar")
            c1, c2, c3 = st.columns(3)
            c1.metric("Tren BULLISH 🚀", bullish_cnt)
            c2.metric("Potensi OVERSOLD 🟢", oversold_cnt)
            c3.metric("Tren BEARISH 📉", bearish_cnt)
            st.markdown("<hr>", unsafe_allow_html=True)

            filter_sinyal = st.selectbox("Filter Tabel:", ["Semua", "BULLISH", "OVERSOLD", "BEARISH"])
            
            df_display = df_scan_state.copy()
            if filter_sinyal != "Semua":
                df_display = df_display[df_display['Sinyal'].str.contains(filter_sinyal)]
            
            st.dataframe(
                df_display.style.map(highlight_signal, subset=['Sinyal']),
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Harga": st.column_config.NumberColumn("Harga (Rp)", format="%d"),
                }
            )
            
            if api_error:
                st.error(f"⏱️ DATA BASI. Terakhir berhasil diproses: {st.session_state.last_scan_time} WIB")
            else:
                st.caption(f"⏱️ *Data batch dicache 5 menit. Terakhir diproses: {st.session_state.last_scan_time} WIB*")
            
            csv_data = df_display.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data (CSV)", 
                data=csv_data, 
                file_name=st.session_state.get('csv_filename', 'screener_data.csv'), 
                mime="text/csv"
            )
        elif not api_error:
            st.info("⚠️ Semua ticker yang dimasukkan tidak valid atau kosong.")

# ==========================================
# TAB 4: KALKULATOR TRADING
# ==========================================
with tab4:
    st.markdown("### 🧮 Manajemen Risiko")
    harga_beli = st.number_input("Harga Beli (Rp):", min_value=1, value=1000, step=10)
    modal = st.number_input("Modal Trading (Rp):", min_value=100000, value=1000000, step=100000)
    
    col_tp, col_sl = st.columns(2)
    target_persen = col_tp.number_input("Target Untung (%):", min_value=1, value=10)
    stop_persen = col_sl.number_input("Batas Rugi (%):", min_value=1, value=5)
    
    harga_1_lot = harga_beli * 100
    lot_didapat = int(modal // harga_1_lot)
    harga_tp = harga_beli + (harga_beli * target_persen / 100)
    harga_sl = harga_beli - (harga_beli * stop_persen / 100)
    
    st.success(f"📦 **Lot Maksimal:** {lot_didapat} Lot")
    st.info(f"✅ **Target Jual (TP): Rp {harga_tp:,.0f}**")
    st.error(f"🛑 **Batas Cut Loss (SL): Rp {harga_sl:,.0f}**")
