# streamlit_app.py
# pip install streamlit

import streamlit as st
import subprocess
import io
import zipfile
import tempfile
import os
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="Bulk MP4 → MP3 Converter Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Check ffmpeg ───────────────────────────────────────────────
@st.cache_resource
def check_ffmpeg():
    try:
        r = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


# ── Core conversion (in-memory) ────────────────────────────────
def convert_to_mp3_inmemory(
        file_bytes: bytes,
        filename: str,
        bitrate: str = '320k',
        sample_rate: str = '44100',
        channels: str = '2',
) -> tuple[bytes | None, str]:
    """
    Convert video bytes → MP3 bytes entirely in memory.
    Returns (mp3_bytes, error_message).
    error_message is '' on success.
    """
    suffix = Path(filename).suffix or '.mp4'

    # Write input to a true temp file (ffmpeg needs seekable input)
    with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False) as tmp_in:
        tmp_in.write(file_bytes)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path + '.mp3'

    try:
        cmd = [
            'ffmpeg', '-y',
            '-i',      tmp_in_path,
            '-vn',
            '-acodec', 'libmp3lame',
            '-ab',     bitrate,
            '-ar',     sample_rate,
            '-ac',     channels,
            '-q:a',    '0',
            tmp_out_path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=3600,
        )
        if result.returncode != 0:
            err = result.stderr.decode('utf-8', errors='replace')
            return None, f"ffmpeg error: {err[-300:]}"

        if not os.path.exists(tmp_out_path):
            return None, "ffmpeg produced no output"

        with open(tmp_out_path, 'rb') as f:
            mp3_bytes = f.read()

        return mp3_bytes, ''

    except subprocess.TimeoutExpired:
        return None, "Conversion timed out"
    except Exception as e:
        return None, str(e)
    finally:
        # Always clean up temp files
        try:
            os.unlink(tmp_in_path)
        except Exception:
            pass
        try:
            os.unlink(tmp_out_path)
        except Exception:
            pass


def build_zip(results: list[dict]) -> bytes:
    """Build a ZIP archive in memory from converted results."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r['success'] and r['mp3_bytes']:
                zf.writestr(r['mp3_name'], r['mp3_bytes'])
    buf.seek(0)
    return buf.read()


def fmt_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1_048_576:
        return f"{b/1024:.1f} KB"
    if b < 1_073_741_824:
        return f"{b/1_048_576:.2f} MB"
    return f"{b/1_073_741_824:.2f} GB"


# ── Custom CSS ─────────────────────────────────────────────────
def inject_css():
    st.markdown("""
<style>
/* ── Global ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', sans-serif;
}
.stApp {
    background: linear-gradient(135deg, #0f0f1a 0%, #1a1040 50%, #0f1a2e 100%);
    min-height: 100vh;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 1.5rem !important;
    max-width: 1100px !important;
}

/* ── Hero header ── */
.hero {
    text-align: center;
    padding: 2.5rem 1rem 1.5rem;
    background: rgba(124,111,255,0.06);
    border: 1px solid rgba(124,111,255,0.18);
    border-radius: 20px;
    margin-bottom: 1.5rem;
}
.hero-icon {
    font-size: 3.5rem;
    display: block;
    margin-bottom: .6rem;
    animation: float 3s ease-in-out infinite;
}
@keyframes float {
    0%,100%{transform:translateY(0)}
    50%{transform:translateY(-8px)}
}
.hero h1 {
    font-size: clamp(1.4rem, 3.5vw, 2.2rem);
    font-weight: 900;
    background: linear-gradient(135deg, #dde0ff, #9d95ff, #00c8f8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: .4rem;
    letter-spacing: -.5px;
}
.hero p {
    color: #6868a0;
    font-size: .9rem;
}

/* ── Status badges ── */
.badge-row {
    display: flex;
    justify-content: center;
    gap: .6rem;
    flex-wrap: wrap;
    margin-top: 1rem;
}
.badge {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    padding: .3rem .9rem;
    border-radius: 99px;
    font-size: .72rem;
    font-weight: 700;
    border: 1px solid;
    letter-spacing: .3px;
}
.badge.green { background:rgba(0,230,118,.12); border-color:rgba(0,230,118,.35); color:#00e676; }
.badge.red   { background:rgba(255,92,122,.12); border-color:rgba(255,92,122,.35); color:#ff5c7a; }
.badge.blue  { background:rgba(0,200,248,.12);  border-color:rgba(0,200,248,.35);  color:#00c8f8; }
.badge.amber { background:rgba(255,179,0,.12);  border-color:rgba(255,179,0,.35);  color:#ffb300; }

/* ── Section card ── */
.sec-card {
    background: rgba(26,26,64,0.75);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
    backdrop-filter: blur(12px);
}
.sec-title {
    font-size: .8rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #9d95ff;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: .45rem;
}

/* ── File table ── */
.file-table {
    width: 100%;
    border-collapse: collapse;
    font-size: .82rem;
}
.file-table th {
    text-align: left;
    color: #6868a0;
    font-size: .7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .7px;
    padding: .5rem .8rem;
    border-bottom: 1px solid rgba(255,255,255,.07);
}
.file-table td {
    padding: .65rem .8rem;
    border-bottom: 1px solid rgba(255,255,255,.04);
    vertical-align: middle;
}
.file-table tr:last-child td { border-bottom: none; }
.file-table tr:hover td { background: rgba(124,111,255,.05); }

/* ── Status chips ── */
.chip {
    display: inline-flex;
    align-items: center;
    gap: .3rem;
    padding: .2rem .7rem;
    border-radius: 99px;
    font-size: .7rem;
    font-weight: 700;
}
.chip.pending  { background:rgba(255,255,255,.06); color:#6868a0; }
.chip.queued   { background:rgba(255,179,0,.12);   color:#ffb300; }
.chip.running  { background:rgba(124,111,255,.15); color:#9d95ff; }
.chip.done     { background:rgba(0,230,118,.12);   color:#00e676; }
.chip.error    { background:rgba(255,92,122,.12);  color:#ff5c7a; }

/* ── Progress bar ── */
.prog-wrap { width: 100%; min-width: 120px; }
.prog-track {
    height: 7px;
    background: rgba(255,255,255,.08);
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: 3px;
}
.prog-fill {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg, #7c6fff, #00c8f8);
    transition: width .4s ease;
}
.prog-fill.done  { background: linear-gradient(90deg, #00e676, #00c853); }
.prog-fill.error { background: #ff5c7a; width: 100% !important; }
.prog-pct { font-size: .68rem; color: #6868a0; }

/* ── Overall progress ── */
.overall-card {
    background: rgba(124,111,255,.07);
    border: 1px solid rgba(124,111,255,.2);
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1.2rem;
}
.overall-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: .7rem;
}
.overall-label { font-size: .88rem; font-weight: 700; color: #dde0ff; }
.overall-pct   { font-size: 1.5rem; font-weight: 900; color: #9d95ff; }
.overall-track {
    height: 12px;
    background: rgba(255,255,255,.07);
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: .8rem;
}
.overall-fill {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg, #7c6fff, #00c8f8);
    transition: width .5s ease;
}
.overall-fill.done { background: linear-gradient(90deg, #00e676, #00c853); }
.stats-row {
    display: flex;
    gap: 1.4rem;
    flex-wrap: wrap;
    font-size: .78rem;
}
.stat-item { display: flex; align-items: center; gap: .4rem; }
.sdot {
    width: 8px; height: 8px;
    border-radius: 50%; flex-shrink: 0;
}
.sdot.amber  { background: #ffb300; }
.sdot.purple { background: #7c6fff; }
.sdot.green  { background: #00e676; }
.sdot.red    { background: #ff5c7a; }

/* ── Streamlit overrides ── */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 700 !important;
    letter-spacing: .3px !important;
    transition: all .2s !important;
}
.stButton > button:hover { transform: translateY(-1px) !important; }

div[data-testid="stFileUploader"] {
    background: rgba(124,111,255,.05) !important;
    border: 2px dashed rgba(124,111,255,.3) !important;
    border-radius: 14px !important;
    padding: .8rem !important;
    transition: border-color .3s !important;
}
div[data-testid="stFileUploader"]:hover {
    border-color: rgba(124,111,255,.6) !important;
}

div[data-testid="stSelectbox"] > div > div {
    background: rgba(26,26,64,.9) !important;
    border: 1.5px solid rgba(255,255,255,.12) !important;
    border-radius: 10px !important;
    color: #dde0ff !important;
}

.stDownloadButton > button {
    background: linear-gradient(135deg, #00e676, #00c853) !important;
    color: #000 !important;
    border: none !important;
    font-weight: 800 !important;
    padding: .6rem 1.4rem !important;
    border-radius: 10px !important;
    font-size: .85rem !important;
    width: 100% !important;
}
.stDownloadButton > button:hover {
    background: linear-gradient(135deg, #33eb91, #00e676) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(0,230,118,.3) !important;
}

/* Download ZIP button */
.zip-dl > div > button {
    background: linear-gradient(135deg, #7c6fff, #00c8f8) !important;
    color: #fff !important;
    font-size: .95rem !important;
    padding: .75rem 2rem !important;
    border-radius: 12px !important;
    width: 100% !important;
}
.zip-dl > div > button:hover {
    box-shadow: 0 8px 28px rgba(124,111,255,.4) !important;
}

/* ── Tip box ── */
.tip-box {
    background: rgba(0,200,248,.07);
    border: 1px solid rgba(0,200,248,.2);
    border-radius: 10px;
    padding: .7rem 1rem;
    font-size: .8rem;
    color: #6868a0;
    margin-bottom: 1.2rem;
    display: flex;
    align-items: center;
    gap: .5rem;
}

/* ── Error box ── */
.err-box {
    background: rgba(255,92,122,.1);
    border: 1px solid rgba(255,92,122,.3);
    border-radius: 10px;
    padding: .8rem 1rem;
    font-size: .82rem;
    color: #ff5c7a;
    margin-top: .5rem;
    word-break: break-all;
}

/* ── Divider ── */
.my-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,.07);
    margin: 1.2rem 0;
}

/* ── Preset button row ── */
.preset-row {
    display: flex;
    gap: .5rem;
    flex-wrap: wrap;
    margin-top: .4rem;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 2.5rem 1rem;
    color: #4a4a70;
}
.empty-state-icon { font-size: 2.5rem; margin-bottom: .6rem; }
</style>
""", unsafe_allow_html=True)


# ── Session state init ─────────────────────────────────────────
def init_state():
    defaults = {
        'results':      [],   # list of result dicts
        'converting':   False,
        'done':         False,
        'zip_bytes':    None,
        'bitrate':      '320k',
        'sample_rate':  '44100',
        'channels':     '2',
        'last_files':   [],   # track uploaded file names
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Render helpers ─────────────────────────────────────────────
def render_hero(ffmpeg_ok: bool):
    ffmpeg_badge = (
        '<span class="badge green">✅ ffmpeg ready</span>'
        if ffmpeg_ok else
        '<span class="badge red">❌ ffmpeg not found</span>'
    )
    st.markdown(f"""
<div class="hero">
  <span class="hero-icon">🎬</span>
  <h1>Bulk MP4 → MP3 Converter Pro</h1>
  <p>Convert multiple video files to MP3 simultaneously — no files saved on server</p>
  <div class="badge-row">
    {ffmpeg_badge}
    <span class="badge blue">☁️ In-Memory Processing</span>
    <span class="badge green">🔒 Privacy First — Files Never Stored</span>
  </div>
</div>
""", unsafe_allow_html=True)


def chip(status: str) -> str:
    labels = {
        'pending': '⏳ Pending',
        'queued':  '🕐 Queued',
        'running': '⚙️ Converting',
        'done':    '✅ Done',
        'error':   '❌ Error',
    }
    return (f'<span class="chip {status}">'
            f'{labels.get(status, status)}</span>')


def prog_bar(pct: int, status: str) -> str:
    cls = 'done' if status == 'done' else 'error' if status == 'error' else ''
    w   = 100 if status in ('done', 'error') else pct
    return f"""
<div class="prog-wrap">
  <div class="prog-track">
    <div class="prog-fill {cls}" style="width:{w}%"></div>
  </div>
  <div class="prog-pct">{w}%</div>
</div>"""


def render_file_table(results: list[dict]):
    rows = ''
    for r in results:
        sz    = fmt_bytes(r.get('size', 0))
        out   = r.get('mp3_name', '')
        rows += f"""
<tr>
  <td>🎬</td>
  <td title="{r['orig_name']}">{r['orig_name'][:42]}
    {'…' if len(r['orig_name']) > 42 else ''}</td>
  <td style="color:#6868a0">{sz}</td>
  <td>{out}</td>
  <td>{chip(r['status'])}</td>
  <td>{prog_bar(r.get('progress', 0), r['status'])}</td>
</tr>"""
    st.markdown(f"""
<div class="sec-card">
  <div class="sec-title">📋 Conversion Queue</div>
  <table class="file-table">
    <thead>
      <tr>
        <th></th>
        <th>File</th>
        <th>Size</th>
        <th>Output</th>
        <th>Status</th>
        <th>Progress</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
""", unsafe_allow_html=True)


def render_overall(results: list[dict]):
    total   = len(results)
    done    = sum(1 for r in results if r['status'] == 'done')
    errors  = sum(1 for r in results if r['status'] == 'error')
    running = sum(1 for r in results if r['status'] == 'running')
    queued  = sum(1 for r in results if r['status'] in ('queued', 'pending'))

    if total == 0:
        return
    pct    = round((done + errors) / total * 100)
    is_done = (done + errors) == total
    fill_cls = 'done' if is_done else ''

    label = ('All done! 🎉' if is_done and errors == 0
             else f'Completed with {errors} error(s)' if is_done
             else f'Converting… ({done}/{total} done)')

    st.markdown(f"""
<div class="overall-card">
  <div class="overall-top">
    <span class="overall-label">{label}</span>
    <span class="overall-pct">{pct}%</span>
  </div>
  <div class="overall-track">
    <div class="overall-fill {fill_cls}" style="width:{pct}%"></div>
  </div>
  <div class="stats-row">
    <div class="stat-item">
      <div class="sdot amber"></div><span>{queued} queued</span>
    </div>
    <div class="stat-item">
      <div class="sdot purple"></div><span>{running} converting</span>
    </div>
    <div class="stat-item">
      <div class="sdot green"></div><span>{done} done</span>
    </div>
    <div class="stat-item">
      <div class="sdot red"></div><span>{errors} errors</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Main app ───────────────────────────────────────────────────
def main():
    inject_css()
    init_state()

    ffmpeg_ok = check_ffmpeg()
    render_hero(ffmpeg_ok)

    if not ffmpeg_ok:
        st.markdown("""
<div class="err-box">
  ⚠️ <strong>ffmpeg not found!</strong><br>
  Install it: &nbsp;
  <code>brew install ffmpeg</code> (Mac) &nbsp;|&nbsp;
  <code>sudo apt install ffmpeg</code> (Linux) &nbsp;|&nbsp;
  <a href="https://www.gyan.dev/ffmpeg/builds/" target="_blank"
     style="color:#ff9999">gyan.dev/ffmpeg</a> (Windows)
</div>
""", unsafe_allow_html=True)
        return

    # ── Settings ───────────────────────────────────────────────
    st.markdown("""
<div class="sec-card">
  <div class="sec-title">⚙️ Audio Quality Settings</div>
</div>
""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**🎵 Bitrate**")
        bitrate = st.selectbox(
            "Bitrate", ['96k', '128k', '192k', '256k', '320k'],
            index=4, label_visibility='collapsed', key='sel_bitrate')
    with col2:
        st.markdown("**📊 Sample Rate**")
        sample_rate = st.selectbox(
            "Sample Rate",
            ['22050', '44100', '48000', '96000'],
            index=1, label_visibility='collapsed', key='sel_sr')
    with col3:
        st.markdown("**🎤 Channels**")
        ch_opt = st.selectbox(
            "Channels",
            ['1 – Mono', '2 – Stereo'],
            index=1, label_visibility='collapsed', key='sel_ch')
    channels = '1' if '1' in ch_opt else '2'

    # Presets
    st.markdown('<div style="margin-top:.3rem;font-size:.78rem;'
                'color:#6868a0;font-weight:700;'
                'text-transform:uppercase;letter-spacing:.5px">'
                'Quick Presets</div>', unsafe_allow_html=True)
    pc1, pc2, pc3, pc4, _ = st.columns([1, 1, 1, 1, 3])
    with pc1:
        if st.button("🎧 High", use_container_width=True, key='p1'):
            st.session_state.sel_bitrate   = '320k'
            st.session_state.sel_sr        = '44100'
            st.session_state.sel_ch        = '2 – Stereo'
            st.rerun()
    with pc2:
        if st.button("📱 Standard", use_container_width=True, key='p2'):
            st.session_state.sel_bitrate   = '192k'
            st.session_state.sel_sr        = '44100'
            st.session_state.sel_ch        = '2 – Stereo'
            st.rerun()
    with pc3:
        if st.button("💾 Compact", use_container_width=True, key='p3'):
            st.session_state.sel_bitrate   = '128k'
            st.session_state.sel_sr        = '22050'
            st.session_state.sel_ch        = '2 – Stereo'
            st.rerun()
    with pc4:
        if st.button("🎙 Voice", use_container_width=True, key='p4'):
            st.session_state.sel_bitrate   = '128k'
            st.session_state.sel_sr        = '22050'
            st.session_state.sel_ch        = '1 – Mono'
            st.rerun()

    st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

    # ── File uploader ──────────────────────────────────────────
    st.markdown("""
<div class="sec-title" style="margin-bottom:.6rem">
  📁 Upload Video Files
</div>
""", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Drop video files here or click to browse",
        type=['mp4', 'avi', 'mkv', 'mov', 'wmv',
              'flv', 'webm', 'm4v', 'ts'],
        accept_multiple_files=True,
        label_visibility='collapsed',
        key='file_uploader',
    )

    st.markdown("""
<div class="tip-box">
  💡 Files are processed entirely in memory and
  <strong>never saved to the server</strong>.
  Download your MP3s directly from your browser.
</div>
""", unsafe_allow_html=True)

    # Detect newly uploaded files → reset results
    if uploaded:
        names = [f.name for f in uploaded]
        if names != st.session_state.last_files:
            st.session_state.last_files = names
            st.session_state.results    = [
                {
                    'orig_name': f.name,
                    'mp3_name':  Path(f.name).stem + '.mp3',
                    'size':      f.size,
                    'status':    'pending',
                    'progress':  0,
                    'mp3_bytes': None,
                    'error':     None,
                }
                for f in uploaded
            ]
            st.session_state.done      = False
            st.session_state.converting = False
            st.session_state.zip_bytes = None

    # ── Show queue if files selected ───────────────────────────
    if st.session_state.results:
        render_overall(st.session_state.results)
        render_file_table(st.session_state.results)
    else:
        st.markdown("""
<div class="empty-state">
  <div class="empty-state-icon">🎬</div>
  <p>Upload video files above to get started</p>
</div>
""", unsafe_allow_html=True)

    st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

    # ── Action buttons ─────────────────────────────────────────
    a1, a2 = st.columns([2, 1])

    with a1:
        convert_disabled = (
            not uploaded
            or st.session_state.converting
            or not ffmpeg_ok
        )
        if st.button(
            "🚀 Convert All to MP3",
            disabled=convert_disabled,
            use_container_width=True,
            type='primary',
            key='btn_convert',
        ):
            if uploaded and not st.session_state.converting:
                # Reset results
                st.session_state.results = [
                    {
                        'orig_name': f.name,
                        'mp3_name':  Path(f.name).stem + '.mp3',
                        'size':      f.size,
                        'status':    'queued',
                        'progress':  0,
                        'mp3_bytes': None,
                        'error':     None,
                        '_file_obj': f,
                    }
                    for f in uploaded
                ]
                st.session_state.converting = True
                st.session_state.done       = False
                st.session_state.zip_bytes  = None
                st.rerun()

    with a2:
        zip_ready = (
            st.session_state.done
            and st.session_state.zip_bytes
            and len(st.session_state.zip_bytes) > 0
        )
        st.markdown('<div class="zip-dl">', unsafe_allow_html=True)
        st.download_button(
            label="📦 Download All as ZIP",
            data=st.session_state.zip_bytes or b'',
            file_name='converted_mp3s.zip',
            mime='application/zip',
            disabled=not zip_ready,
            use_container_width=True,
            key='btn_zip',
        )
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Run conversion ─────────────────────────────────────────
    if st.session_state.converting:
        st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

        prog_placeholder  = st.empty()
        table_placeholder = st.empty()
        status_text       = st.empty()

        results = st.session_state.results

        # Read file bytes before threading
        # (Streamlit UploadedFile is not thread-safe)
        file_data = []
        for i, r in enumerate(results):
            if '_file_obj' in r:
                raw = r['_file_obj'].read()
                file_data.append((i, raw, r['orig_name']))
            else:
                file_data.append((i, None, r['orig_name']))

        # ── Sequential conversion with live updates ────────────
        # (Streamlit widgets must be updated from main thread)
        MAX_WORKERS = 3

        def do_conversion(idx, raw_bytes, fname):
            results[idx]['status']   = 'running'
            results[idx]['progress'] = 10
            mp3, err = convert_to_mp3_inmemory(
                raw_bytes, fname, bitrate, sample_rate, channels)
            if err:
                results[idx]['status']   = 'error'
                results[idx]['error']    = err
                results[idx]['progress'] = 0
            else:
                results[idx]['status']   = 'done'
                results[idx]['mp3_bytes'] = mp3
                results[idx]['progress'] = 100
            # Remove internal file obj
            results[idx].pop('_file_obj', None)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {
                ex.submit(do_conversion, idx, raw, fname): idx
                for idx, raw, fname in file_data
                if raw is not None
            }

            while futures:
                done_futs = {
                    f for f in futures if f.done()
                }
                for f in done_futs:
                    del futures[f]

                # Update UI
                with prog_placeholder.container():
                    render_overall(results)
                with table_placeholder.container():
                    render_file_table(results)

                n_done = sum(1 for r in results
                             if r['status'] in ('done', 'error'))
                status_text.markdown(
                    f"**Processing… {n_done}/{len(results)} complete**")

                if futures:
                    time.sleep(0.6)

        # Final UI update
        with prog_placeholder.container():
            render_overall(results)
        with table_placeholder.container():
            render_file_table(results)
        status_text.empty()

        # Build ZIP
        ready = [r for r in results
                 if r['status'] == 'done' and r['mp3_bytes']]
        if ready:
            st.session_state.zip_bytes = build_zip(ready)

        st.session_state.converting = False
        st.session_state.done       = True
        st.session_state.results    = results
        st.rerun()

    # ── Download buttons for individual files ──────────────────
    done_results = [r for r in st.session_state.results
                    if r['status'] == 'done' and r.get('mp3_bytes')]

    if done_results:
        st.markdown('<hr class="my-divider">', unsafe_allow_html=True)
        st.markdown("""
<div class="sec-card">
  <div class="sec-title">⬇️ Download Converted Files</div>
</div>
""", unsafe_allow_html=True)

        # Show errors if any
        errors = [r for r in st.session_state.results
                  if r['status'] == 'error']
        if errors:
            for r in errors:
                st.markdown(
                    f'<div class="err-box">❌ <strong>{r["orig_name"]}</strong>'
                    f'<br>{r.get("error", "Unknown error")}</div>',
                    unsafe_allow_html=True)

        # Grid of download buttons
        cols_per_row = 2
        for i in range(0, len(done_results), cols_per_row):
            row_items = done_results[i:i + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, r in zip(cols, row_items):
                with col:
                    sz = fmt_bytes(len(r['mp3_bytes']))
                    st.markdown(
                        f"**{r['mp3_name']}** "
                        f"<span style='color:#6868a0;font-size:.78rem'>"
                        f"({sz})</span>",
                        unsafe_allow_html=True)
                    st.download_button(
                        label=f"⬇️ Download {r['mp3_name']}",
                        data=r['mp3_bytes'],
                        file_name=r['mp3_name'],
                        mime='audio/mpeg',
                        use_container_width=True,
                        key=f"dl_{r['mp3_name']}_{i}",
                    )

        # ZIP download (again at bottom for convenience)
        if st.session_state.zip_bytes and len(done_results) > 1:
            st.markdown('<hr class="my-divider">', unsafe_allow_html=True)
            st.markdown('<div class="zip-dl">', unsafe_allow_html=True)
            st.download_button(
                label=f"📦 Download All {len(done_results)} Files as ZIP",
                data=st.session_state.zip_bytes,
                file_name='converted_mp3s.zip',
                mime='application/zip',
                use_container_width=True,
                key='btn_zip_bottom',
            )
            st.markdown('</div>', unsafe_allow_html=True)

        # Success message
        if st.session_state.done:
            n_ok   = len(done_results)
            n_fail = len([r for r in st.session_state.results
                          if r['status'] == 'error'])
            if n_fail == 0:
                st.success(
                    f"🎉 All {n_ok} file(s) converted successfully! "
                    f"Click the buttons above to download.")
            else:
                st.warning(
                    f"✅ {n_ok} converted, ❌ {n_fail} failed.")

    # ── Footer ─────────────────────────────────────────────────
    st.markdown("""
<div style="text-align:center;padding:2rem 0 .5rem;
  color:#3a3a60;font-size:.75rem">
  Bulk MP4 → MP3 Converter Pro · In-Memory Edition · Powered by ffmpeg
</div>
""", unsafe_allow_html=True)


if __name__ == '__main__':
    main()
