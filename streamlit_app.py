# streamlit_app.py
# Run: streamlit run streamlit_app.py

import streamlit as st
import subprocess
import io
import zipfile
import tempfile
import os
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title  = "Bulk MP4 → MP3 Converter Pro",
    page_icon   = "🎬",
    layout      = "wide",
    initial_sidebar_state = "collapsed",
)


# ── ffmpeg check ───────────────────────────────────────────────
@st.cache_resource
def check_ffmpeg():
    try:
        r = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


# ── Core conversion (fully in-memory output) ───────────────────
def convert_to_mp3_inmemory(
        file_bytes  : bytes,
        filename    : str,
        bitrate     : str = '320k',
        sample_rate : str = '44100',
        channels    : str = '2',
) -> tuple:
    """
    Write input bytes to a temp file, run ffmpeg, read output bytes,
    delete both temp files.  Returns (mp3_bytes | None, error_str).
    """
    suffix = Path(filename).suffix.lower() or '.mp4'

    # ffmpeg needs a seekable file for most containers
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
            timeout=7200,          # 2-hour hard limit per file
        )
        if result.returncode != 0:
            err = result.stderr.decode('utf-8', errors='replace')
            return None, f"ffmpeg error:\n{err[-600:]}"

        if not os.path.exists(tmp_out_path):
            return None, "ffmpeg produced no output file."

        with open(tmp_out_path, 'rb') as fh:
            mp3_bytes = fh.read()

        if len(mp3_bytes) < 128:
            return None, "Output MP3 is suspiciously small — check source file."

        return mp3_bytes, ''

    except subprocess.TimeoutExpired:
        return None, "Conversion timed out (2-hour limit exceeded)."
    except Exception as exc:
        return None, str(exc)
    finally:
        for p in (tmp_in_path, tmp_out_path):
            try:
                os.unlink(p)
            except Exception:
                pass


# ── ZIP builder ────────────────────────────────────────────────
def build_zip(results: list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r.get('status') == 'done' and r.get('mp3_bytes'):
                zf.writestr(r['mp3_name'], r['mp3_bytes'])
    buf.seek(0)
    return buf.read()


# ── Formatting helpers ─────────────────────────────────────────
def fmt_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1_048_576:
        return f"{b / 1024:.1f} KB"
    if b < 1_073_741_824:
        return f"{b / 1_048_576:.2f} MB"
    return f"{b / 1_073_741_824:.2f} GB"


def get_limit_display() -> tuple:
    """Returns (limit_mb: int, display_str: str)."""
    try:
        lim = int(st.get_option('server.maxUploadSize') or 200)
    except Exception:
        lim = 200
    disp = f"{lim // 1024} GB" if lim >= 1024 else f"{lim} MB"
    return lim, disp


# ══════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════
def inject_css():
    st.markdown("""
<style>
/* ── Fonts & reset ── */
@import url('https://fonts.googleapis.com/css2?
  family=Inter:wght@400;600;700;800;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}

/* ── App background ── */
.stApp {
    background: linear-gradient(
        135deg,
        #0f0f1a 0%,
        #1a1040 50%,
        #0f1a2e 100%
    );
    min-height: 100vh;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top    : 1.4rem !important;
    padding-bottom : 4rem   !important;
    max-width      : 1100px !important;
}

/* ════════════════════════════════
   HERO
════════════════════════════════ */
.hero {
    text-align       : center;
    padding          : 2.6rem 1rem 1.8rem;
    background       : rgba(124,111,255,.06);
    border           : 1px solid rgba(124,111,255,.2);
    border-radius    : 22px;
    margin-bottom    : 1.4rem;
}
.hero-icon {
    font-size     : 3.6rem;
    display       : block;
    margin-bottom : .55rem;
    animation     : float 3s ease-in-out infinite;
}
@keyframes float {
    0%,100% { transform: translateY(0);   }
    50%     { transform: translateY(-9px); }
}
.hero h1 {
    font-size   : clamp(1.45rem, 3.8vw, 2.3rem);
    font-weight : 900;
    background  : linear-gradient(135deg, #dde0ff 0%, #9d95ff 55%, #00c8f8 100%);
    -webkit-background-clip : text;
    -webkit-text-fill-color : transparent;
    background-clip         : text;
    margin-bottom           : .4rem;
    letter-spacing          : -.5px;
}
.hero p {
    color     : #6868a0;
    font-size : .92rem;
    line-height: 1.6;
}

/* ════════════════════════════════
   BADGES
════════════════════════════════ */
.badge-row {
    display         : flex;
    justify-content : center;
    gap             : .6rem;
    flex-wrap       : wrap;
    margin-top      : 1rem;
}
.badge {
    display      : inline-flex;
    align-items  : center;
    gap          : .35rem;
    padding      : .28rem .9rem;
    border-radius: 99px;
    font-size    : .72rem;
    font-weight  : 700;
    border       : 1px solid;
    letter-spacing: .25px;
}
.badge.green  { background:rgba(0,230,118,.11);  border-color:rgba(0,230,118,.35);  color:#00e676; }
.badge.red    { background:rgba(255,92,122,.11); border-color:rgba(255,92,122,.35); color:#ff5c7a; }
.badge.blue   { background:rgba(0,200,248,.11);  border-color:rgba(0,200,248,.35);  color:#00c8f8; }
.badge.amber  { background:rgba(255,179,0,.11);  border-color:rgba(255,179,0,.35);  color:#ffb300; }
.badge.purple { background:rgba(124,111,255,.12);border-color:rgba(124,111,255,.38);color:#9d95ff; }

/* ════════════════════════════════
   SECTION CARDS
════════════════════════════════ */
.sec-card {
    background    : rgba(26,26,64,.78);
    border        : 1px solid rgba(255,255,255,.08);
    border-radius : 16px;
    padding       : 1.4rem 1.6rem;
    margin-bottom : 1.2rem;
    backdrop-filter: blur(14px);
}
.sec-title {
    font-size      : .78rem;
    font-weight    : 800;
    text-transform : uppercase;
    letter-spacing : 1px;
    color          : #9d95ff;
    margin-bottom  : 1rem;
    display        : flex;
    align-items    : center;
    gap            : .45rem;
}

/* ════════════════════════════════
   LIMIT / INFO BOXES
════════════════════════════════ */
.limit-box {
    background    : rgba(255,179,0,.07);
    border        : 1px solid rgba(255,179,0,.28);
    border-radius : 14px;
    padding       : 1.2rem 1.5rem;
    margin-bottom : 1.2rem;
}
.limit-box h3 {
    color         : #ffb300;
    font-size     : .92rem;
    font-weight   : 800;
    margin-bottom : .55rem;
}
.limit-box p {
    color       : #a08840;
    font-size   : .82rem;
    line-height : 1.7;
    margin      : 0;
}

.tip-box {
    background    : rgba(0,200,248,.07);
    border        : 1px solid rgba(0,200,248,.2);
    border-radius : 10px;
    padding       : .7rem 1rem;
    font-size     : .8rem;
    color         : #5a8a9a;
    margin-bottom : 1rem;
    line-height   : 1.6;
}
.warn-box {
    background    : rgba(255,179,0,.07);
    border        : 1px solid rgba(255,179,0,.24);
    border-radius : 10px;
    padding       : .75rem 1rem;
    font-size     : .82rem;
    color         : #b89030;
    margin-bottom : 1rem;
    line-height   : 1.6;
}
.ok-box {
    background    : rgba(0,230,118,.07);
    border        : 1px solid rgba(0,230,118,.22);
    border-radius : 10px;
    padding       : .7rem 1rem;
    font-size     : .82rem;
    color         : #30a060;
    margin-bottom : 1rem;
    line-height   : 1.6;
}
.err-box {
    background  : rgba(255,92,122,.1);
    border      : 1px solid rgba(255,92,122,.3);
    border-radius: 10px;
    padding     : .8rem 1rem;
    font-size   : .82rem;
    color       : #ff5c7a;
    margin-top  : .5rem;
    word-break  : break-all;
    line-height : 1.6;
}
.success-box {
    background    : rgba(0,230,118,.08);
    border        : 1px solid rgba(0,230,118,.25);
    border-radius : 10px;
    padding       : .85rem 1.1rem;
    font-size     : .9rem;
    color         : #00e676;
    font-weight   : 700;
    margin-top    : .8rem;
}

/* ════════════════════════════════
   FILE TABLE
════════════════════════════════ */
.file-table {
    width           : 100%;
    border-collapse : collapse;
    font-size       : .82rem;
}
.file-table th {
    text-align    : left;
    color         : #5a5a88;
    font-size     : .7rem;
    font-weight   : 700;
    text-transform: uppercase;
    letter-spacing: .7px;
    padding       : .5rem .8rem;
    border-bottom : 1px solid rgba(255,255,255,.07);
}
.file-table td {
    padding        : .68rem .8rem;
    border-bottom  : 1px solid rgba(255,255,255,.04);
    vertical-align : middle;
    color          : #c8caee;
}
.file-table tr:last-child td { border-bottom: none; }
.file-table tr:hover td { background: rgba(124,111,255,.05); }

/* ════════════════════════════════
   STATUS CHIPS
════════════════════════════════ */
.chip {
    display      : inline-flex;
    align-items  : center;
    gap          : .28rem;
    padding      : .22rem .7rem;
    border-radius: 99px;
    font-size    : .7rem;
    font-weight  : 700;
    white-space  : nowrap;
}
.chip.pending { background:rgba(255,255,255,.06); color:#6868a0; }
.chip.queued  { background:rgba(255,179,0,.12);   color:#ffb300; }
.chip.running { background:rgba(124,111,255,.16);  color:#9d95ff; }
.chip.done    { background:rgba(0,230,118,.12);    color:#00e676; }
.chip.error   { background:rgba(255,92,122,.12);   color:#ff5c7a; }

/* ════════════════════════════════
   PROGRESS BARS (per file)
════════════════════════════════ */
.prog-wrap  { width:100%; min-width:130px; }
.prog-track {
    height       : 7px;
    background   : rgba(255,255,255,.07);
    border-radius: 99px;
    overflow     : hidden;
    margin-bottom: 3px;
}
.prog-fill {
    height       : 100%;
    border-radius: 99px;
    background   : linear-gradient(90deg,#7c6fff,#00c8f8);
    transition   : width .45s ease;
}
.prog-fill.done  { background: linear-gradient(90deg,#00e676,#00c853); }
.prog-fill.error { background: #ff5c7a; width:100% !important; }
.prog-pct { font-size:.68rem; color:#6868a0; margin-top:1px; }

/* ════════════════════════════════
   OVERALL PROGRESS CARD
════════════════════════════════ */
.overall-card {
    background    : rgba(124,111,255,.07);
    border        : 1px solid rgba(124,111,255,.22);
    border-radius : 14px;
    padding       : 1.2rem 1.5rem;
    margin-bottom : 1.2rem;
}
.overall-top {
    display        : flex;
    justify-content: space-between;
    align-items    : center;
    margin-bottom  : .7rem;
}
.overall-label { font-size:.9rem; font-weight:700; color:#dde0ff; }
.overall-pct   { font-size:1.55rem; font-weight:900; color:#9d95ff; }
.overall-track {
    height       : 13px;
    background   : rgba(255,255,255,.07);
    border-radius: 99px;
    overflow     : hidden;
    margin-bottom: .85rem;
}
.overall-fill {
    height       : 100%;
    border-radius: 99px;
    background   : linear-gradient(90deg,#7c6fff,#00c8f8);
    transition   : width .55s ease;
}
.overall-fill.done { background: linear-gradient(90deg,#00e676,#00c853); }

.stats-row {
    display  : flex;
    gap      : 1.4rem;
    flex-wrap: wrap;
    font-size: .78rem;
    color    : #9090c0;
}
.stat-item { display:flex; align-items:center; gap:.4rem; }
.sdot      { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.sdot.amber  { background:#ffb300; }
.sdot.purple { background:#7c6fff; }
.sdot.green  { background:#00e676; }
.sdot.red    { background:#ff5c7a; }

/* ════════════════════════════════
   STREAMLIT WIDGET OVERRIDES
════════════════════════════════ */
.stButton > button {
    border-radius  : 10px !important;
    font-weight    : 700  !important;
    letter-spacing : .3px !important;
    transition     : all .2s !important;
}
.stButton > button:hover:not([disabled]) {
    transform: translateY(-2px) !important;
}

/* File uploader */
div[data-testid="stFileUploader"] {
    background    : rgba(124,111,255,.05) !important;
    border        : 2px dashed rgba(124,111,255,.32) !important;
    border-radius : 14px !important;
    padding       : .9rem !important;
    transition    : border-color .3s !important;
}
div[data-testid="stFileUploader"]:hover {
    border-color: rgba(124,111,255,.65) !important;
}

/* Selectbox */
div[data-testid="stSelectbox"] > div > div {
    background    : rgba(26,26,64,.9) !important;
    border        : 1.5px solid rgba(255,255,255,.12) !important;
    border-radius : 10px !important;
    color         : #dde0ff !important;
}

/* Individual download buttons */
.stDownloadButton > button {
    background    : linear-gradient(135deg,#00e676,#00c853) !important;
    color         : #000 !important;
    border        : none !important;
    font-weight   : 800 !important;
    padding       : .62rem 1.4rem !important;
    border-radius : 10px !important;
    font-size     : .85rem !important;
    width         : 100% !important;
    transition    : all .2s !important;
}
.stDownloadButton > button:hover {
    background    : linear-gradient(135deg,#33eb91,#00e676) !important;
    transform     : translateY(-2px) !important;
    box-shadow    : 0 6px 20px rgba(0,230,118,.32) !important;
}

/* ZIP download button override */
.zip-wrap .stDownloadButton > button {
    background  : linear-gradient(135deg,#7c6fff,#00c8f8) !important;
    color       : #fff !important;
    font-size   : .95rem !important;
    padding     : .78rem 2rem !important;
    border-radius: 12px !important;
    box-shadow  : 0 4px 18px rgba(124,111,255,.28) !important;
}
.zip-wrap .stDownloadButton > button:hover {
    box-shadow: 0 8px 28px rgba(124,111,255,.45) !important;
}

/* ── Divider ── */
.my-divider {
    border     : none;
    border-top : 1px solid rgba(255,255,255,.07);
    margin     : 1.3rem 0;
}

/* ── Empty state ── */
.empty-state {
    text-align : center;
    padding    : 2.8rem 1rem;
    color      : #404060;
}
.empty-icon { font-size:2.6rem; margin-bottom:.6rem; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════════════════════════
def init_state():
    defaults = {
        'results'    : [],
        'converting' : False,
        'done'       : False,
        'zip_bytes'  : None,
        'last_files' : [],   # list of (name, size) tuples
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ══════════════════════════════════════════════════════════════
#  RENDER HELPERS
# ══════════════════════════════════════════════════════════════
def render_hero(ffmpeg_ok: bool):
    fb = ('<span class="badge green">✅ ffmpeg ready</span>'
          if ffmpeg_ok else
          '<span class="badge red">❌ ffmpeg not found</span>')
    _, lim_disp = get_limit_display()
    st.markdown(f"""
<div class="hero">
  <span class="hero-icon">🎬</span>
  <h1>Bulk MP4 → MP3 Converter Pro</h1>
  <p>
    Convert multiple video files simultaneously — up to
    <strong style="color:#dde0ff">{lim_disp}</strong> per file<br>
    Audio extracted in memory · Files <strong style="color:#dde0ff">
    never stored</strong> on server · Download direct to your device
  </p>
  <div class="badge-row">
    {fb}
    <span class="badge blue">☁️ In-Memory Processing</span>
    <span class="badge purple">📦 Up to {lim_disp} per file</span>
    <span class="badge green">🔒 Privacy First</span>
  </div>
</div>
""", unsafe_allow_html=True)


def _chip(status: str) -> str:
    labels = {
        'pending' : '⏳ Pending',
        'queued'  : '🕐 Queued',
        'running' : '⚙️ Converting',
        'done'    : '✅ Done',
        'error'   : '❌ Error',
    }
    return (f'<span class="chip {status}">'
            f'{labels.get(status, status)}</span>')


def _prog(pct: int, status: str) -> str:
    cls = ('done'  if status == 'done'  else
           'error' if status == 'error' else '')
    w   = 100 if status in ('done', 'error') else max(0, pct)
    return f"""
<div class="prog-wrap">
  <div class="prog-track">
    <div class="prog-fill {cls}" style="width:{w}%"></div>
  </div>
  <div class="prog-pct">{w}%</div>
</div>"""


def render_overall(results: list):
    total = len(results)
    if not total:
        return
    done    = sum(1 for r in results if r['status'] == 'done')
    errors  = sum(1 for r in results if r['status'] == 'error')
    running = sum(1 for r in results if r['status'] == 'running')
    queued  = sum(1 for r in results
                  if r['status'] in ('queued', 'pending'))
    pct      = round((done + errors) / total * 100)
    is_fin   = (done + errors) == total
    fill_cls = 'done' if is_fin else ''
    label = (
        '🎉 All done!'
        if is_fin and errors == 0 else
        f'Completed with {errors} error(s)'
        if is_fin else
        f'Converting… ({done}/{total} done)'
    )
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
      <div class="sdot red"></div><span>{errors} error(s)</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_file_table(results: list):
    if not results:
        return
    rows = ''
    for r in results:
        sz   = fmt_bytes(r.get('size', 0))
        name = r['orig_name']
        disp = name[:46] + ('…' if len(name) > 46 else '')
        rows += f"""
<tr>
  <td style="font-size:1.1rem">🎬</td>
  <td title="{name}">{disp}</td>
  <td style="color:#6868a0;white-space:nowrap">{sz}</td>
  <td style="color:#9d95ff">{r['mp3_name']}</td>
  <td>{_chip(r['status'])}</td>
  <td>{_prog(r.get('progress', 0), r['status'])}</td>
</tr>"""
    st.markdown(f"""
<div class="sec-card">
  <div class="sec-title">📋 Conversion Queue</div>
  <table class="file-table">
    <thead>
      <tr>
        <th></th>
        <th>Source File</th>
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


def render_limit_info():
    """Show setup instructions and current limit status."""
    lim_mb, lim_disp = get_limit_display()

    st.markdown("""
<div class="limit-box">
  <h3>⚠️ Default Streamlit upload limit is only 200 MB</h3>
  <p>
    To upload files up to <strong>10 GB</strong> you must configure
    Streamlit before starting — see the setup guide below.
    The <code>.streamlit/config.toml</code> file in this project
    already sets it to <strong>10 GB</strong>.
  </p>
</div>
""", unsafe_allow_html=True)

    with st.expander(
        "📖 Setup Guide — How to enable 10 GB uploads",
        expanded=lim_mb < 500,
    ):
        st.markdown("""
### ✅ Method 1 — `.streamlit/config.toml` *(already included)*

The file `.streamlit/config.toml` next to your script contains:
```toml
[server]
maxUploadSize = 10240
