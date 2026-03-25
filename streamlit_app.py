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
    page_title="Bulk MP4 to MP3 Converter Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ── ffmpeg check ───────────────────────────────────────────────
@st.cache_resource
def check_ffmpeg():
    try:
        r = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


# ── Core conversion ────────────────────────────────────────────
def convert_to_mp3_inmemory(
    file_bytes,
    filename,
    bitrate="320k",
    sample_rate="44100",
    channels="2",
):
    suffix = Path(filename).suffix.lower() or ".mp4"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
        tmp_in.write(file_bytes)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path + ".mp3"

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", tmp_in_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", bitrate,
            "-ar", sample_rate,
            "-ac", channels,
            "-q:a", "0",
            tmp_out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=7200)

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            return None, "ffmpeg error:\n" + err[-600:]

        if not os.path.exists(tmp_out_path):
            return None, "ffmpeg produced no output file."

        with open(tmp_out_path, "rb") as fh:
            mp3_bytes = fh.read()

        if len(mp3_bytes) < 128:
            return None, "Output MP3 is suspiciously small."

        return mp3_bytes, ""

    except subprocess.TimeoutExpired:
        return None, "Conversion timed out (2-hour limit)."
    except Exception as exc:
        return None, str(exc)
    finally:
        for p in (tmp_in_path, tmp_out_path):
            try:
                os.unlink(p)
            except Exception:
                pass


# ── ZIP builder ────────────────────────────────────────────────
def build_zip(results):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r.get("status") == "done" and r.get("mp3_bytes"):
                zf.writestr(r["mp3_name"], r["mp3_bytes"])
    buf.seek(0)
    return buf.read()


# ── Helpers ────────────────────────────────────────────────────
def fmt_bytes(b):
    if b < 1024:
        return str(b) + " B"
    if b < 1_048_576:
        return "{:.1f} KB".format(b / 1024)
    if b < 1_073_741_824:
        return "{:.2f} MB".format(b / 1_048_576)
    return "{:.2f} GB".format(b / 1_073_741_824)


def get_limit_info():
    try:
        lim = int(st.get_option("server.maxUploadSize") or 200)
    except Exception:
        lim = 200
    disp = "{} GB".format(lim // 1024) if lim >= 1024 else "{} MB".format(lim)
    return lim, disp


# ── Session state ──────────────────────────────────────────────
def init_state():
    defaults = {
        "results": [],
        "converting": False,
        "done": False,
        "zip_bytes": None,
        "last_files": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── CSS ────────────────────────────────────────────────────────
CSS = """
<style>
html, body, [class*="css"] {
    font-family: 'Segoe UI', system-ui, sans-serif;
}
.stApp {
    background: linear-gradient(135deg, #0f0f1a 0%, #1a1040 50%, #0f1a2e 100%);
    min-height: 100vh;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 1.4rem !important;
    padding-bottom: 4rem !important;
    max-width: 1100px !important;
}

/* Hero */
.hero {
    text-align: center;
    padding: 2.6rem 1rem 1.8rem;
    background: rgba(124,111,255,0.06);
    border: 1px solid rgba(124,111,255,0.2);
    border-radius: 22px;
    margin-bottom: 1.4rem;
}
.hero-icon {
    font-size: 3.6rem;
    display: block;
    margin-bottom: .55rem;
    animation: float 3s ease-in-out infinite;
}
@keyframes float {
    0%,100% { transform: translateY(0); }
    50%     { transform: translateY(-9px); }
}
.hero h1 {
    font-size: 2.2rem;
    font-weight: 900;
    background: linear-gradient(135deg, #dde0ff 0%, #9d95ff 55%, #00c8f8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: .4rem;
    letter-spacing: -.5px;
}
.hero p {
    color: #6868a0;
    font-size: .92rem;
    line-height: 1.6;
}

/* Badges */
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
    padding: .28rem .9rem;
    border-radius: 99px;
    font-size: .72rem;
    font-weight: 700;
    border: 1px solid;
}
.badge.green  { background:rgba(0,230,118,.11);  border-color:rgba(0,230,118,.35);  color:#00e676; }
.badge.red    { background:rgba(255,92,122,.11); border-color:rgba(255,92,122,.35); color:#ff5c7a; }
.badge.blue   { background:rgba(0,200,248,.11);  border-color:rgba(0,200,248,.35);  color:#00c8f8; }
.badge.amber  { background:rgba(255,179,0,.11);  border-color:rgba(255,179,0,.35);  color:#ffb300; }
.badge.purple { background:rgba(124,111,255,.12);border-color:rgba(124,111,255,.38);color:#9d95ff; }

/* Section card */
.sec-card {
    background: rgba(26,26,64,.78);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 16px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
}
.sec-title {
    font-size: .78rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #9d95ff;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: .45rem;
}

/* Info boxes */
.limit-box {
    background: rgba(255,179,0,.07);
    border: 1px solid rgba(255,179,0,.28);
    border-radius: 14px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1.2rem;
}
.limit-box h3 {
    color: #ffb300;
    font-size: .92rem;
    font-weight: 800;
    margin-bottom: .55rem;
}
.limit-box p {
    color: #a08840;
    font-size: .82rem;
    line-height: 1.7;
    margin: 0;
}
.tip-box {
    background: rgba(0,200,248,.07);
    border: 1px solid rgba(0,200,248,.2);
    border-radius: 10px;
    padding: .7rem 1rem;
    font-size: .8rem;
    color: #5a8a9a;
    margin-bottom: 1rem;
    line-height: 1.6;
}
.warn-box {
    background: rgba(255,179,0,.07);
    border: 1px solid rgba(255,179,0,.24);
    border-radius: 10px;
    padding: .75rem 1rem;
    font-size: .82rem;
    color: #b89030;
    margin-bottom: 1rem;
    line-height: 1.6;
}
.ok-box {
    background: rgba(0,230,118,.07);
    border: 1px solid rgba(0,230,118,.22);
    border-radius: 10px;
    padding: .7rem 1rem;
    font-size: .82rem;
    color: #30a060;
    margin-bottom: 1rem;
    line-height: 1.6;
}
.err-box {
    background: rgba(255,92,122,.1);
    border: 1px solid rgba(255,92,122,.3);
    border-radius: 10px;
    padding: .8rem 1rem;
    font-size: .82rem;
    color: #ff5c7a;
    margin-top: .5rem;
    word-break: break-all;
    line-height: 1.6;
}
.success-box {
    background: rgba(0,230,118,.08);
    border: 1px solid rgba(0,230,118,.25);
    border-radius: 10px;
    padding: .85rem 1.1rem;
    font-size: .9rem;
    color: #00e676;
    font-weight: 700;
    margin-top: .8rem;
}

/* File table */
.file-table {
    width: 100%;
    border-collapse: collapse;
    font-size: .82rem;
}
.file-table th {
    text-align: left;
    color: #5a5a88;
    font-size: .7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .7px;
    padding: .5rem .8rem;
    border-bottom: 1px solid rgba(255,255,255,.07);
}
.file-table td {
    padding: .68rem .8rem;
    border-bottom: 1px solid rgba(255,255,255,.04);
    vertical-align: middle;
    color: #c8caee;
}
.file-table tr:last-child td { border-bottom: none; }
.file-table tr:hover td { background: rgba(124,111,255,.05); }

/* Status chips */
.chip {
    display: inline-flex;
    align-items: center;
    gap: .28rem;
    padding: .22rem .7rem;
    border-radius: 99px;
    font-size: .7rem;
    font-weight: 700;
    white-space: nowrap;
}
.chip.pending { background:rgba(255,255,255,.06); color:#6868a0; }
.chip.queued  { background:rgba(255,179,0,.12);   color:#ffb300; }
.chip.running { background:rgba(124,111,255,.16); color:#9d95ff; }
.chip.done    { background:rgba(0,230,118,.12);   color:#00e676; }
.chip.error   { background:rgba(255,92,122,.12);  color:#ff5c7a; }

/* Per-file progress */
.prog-wrap  { width:100%; min-width:130px; }
.prog-track {
    height: 7px;
    background: rgba(255,255,255,.07);
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: 3px;
}
.prog-fill {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg,#7c6fff,#00c8f8);
    transition: width .45s ease;
}
.prog-fill.done  { background: linear-gradient(90deg,#00e676,#00c853); }
.prog-fill.error { background: #ff5c7a; width:100% !important; }
.prog-pct { font-size:.68rem; color:#6868a0; margin-top:1px; }

/* Overall progress */
.overall-card {
    background: rgba(124,111,255,.07);
    border: 1px solid rgba(124,111,255,.22);
    border-radius: 14px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1.2rem;
}
.overall-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: .7rem;
}
.overall-label { font-size:.9rem; font-weight:700; color:#dde0ff; }
.overall-pct   { font-size:1.55rem; font-weight:900; color:#9d95ff; }
.overall-track {
    height: 13px;
    background: rgba(255,255,255,.07);
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: .85rem;
}
.overall-fill {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg,#7c6fff,#00c8f8);
    transition: width .55s ease;
}
.overall-fill.done { background: linear-gradient(90deg,#00e676,#00c853); }
.stats-row {
    display: flex;
    gap: 1.4rem;
    flex-wrap: wrap;
    font-size: .78rem;
    color: #9090c0;
}
.stat-item { display:flex; align-items:center; gap:.4rem; }
.sdot      { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.sdot.amber  { background:#ffb300; }
.sdot.purple { background:#7c6fff; }
.sdot.green  { background:#00e676; }
.sdot.red    { background:#ff5c7a; }

/* Streamlit widget overrides */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 700 !important;
    letter-spacing: .3px !important;
    transition: all .2s !important;
}
.stButton > button:hover:not([disabled]) {
    transform: translateY(-2px) !important;
}
div[data-testid="stFileUploader"] {
    background: rgba(124,111,255,.05) !important;
    border: 2px dashed rgba(124,111,255,.32) !important;
    border-radius: 14px !important;
    padding: .9rem !important;
}
div[data-testid="stFileUploader"]:hover {
    border-color: rgba(124,111,255,.65) !important;
}
div[data-testid="stSelectbox"] > div > div {
    background: rgba(26,26,64,.9) !important;
    border: 1.5px solid rgba(255,255,255,.12) !important;
    border-radius: 10px !important;
    color: #dde0ff !important;
}
.stDownloadButton > button {
    background: linear-gradient(135deg,#00e676,#00c853) !important;
    color: #000 !important;
    border: none !important;
    font-weight: 800 !important;
    padding: .62rem 1.4rem !important;
    border-radius: 10px !important;
    font-size: .85rem !important;
    width: 100% !important;
    transition: all .2s !important;
}
.stDownloadButton > button:hover {
    background: linear-gradient(135deg,#33eb91,#00e676) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(0,230,118,.32) !important;
}
.zip-wrap .stDownloadButton > button {
    background: linear-gradient(135deg,#7c6fff,#00c8f8) !important;
    color: #fff !important;
    font-size: .95rem !important;
    padding: .78rem 2rem !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 18px rgba(124,111,255,.28) !important;
}
.zip-wrap .stDownloadButton > button:hover {
    box-shadow: 0 8px 28px rgba(124,111,255,.45) !important;
}

/* Misc */
.my-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,.07);
    margin: 1.3rem 0;
}
.empty-state {
    text-align: center;
    padding: 2.8rem 1rem;
    color: #404060;
}
.empty-icon { font-size:2.6rem; margin-bottom:.6rem; }
</style>
"""


# ── Render helpers ─────────────────────────────────────────────
def render_hero(ffmpeg_ok):
    lim_mb, lim_disp = get_limit_info()
    fb = (
        '<span class="badge green">&#x2705; ffmpeg ready</span>'
        if ffmpeg_ok
        else '<span class="badge red">&#x274C; ffmpeg not found</span>'
    )
    html = (
        '<div class="hero">'
        '<span class="hero-icon">&#x1F3AC;</span>'
        '<h1>Bulk MP4 &#x2192; MP3 Converter Pro</h1>'
        '<p>Convert multiple video files simultaneously &mdash; up to '
        '<strong style="color:#dde0ff">' + lim_disp + '</strong> per file<br>'
        'Audio extracted in memory &middot; Files '
        '<strong style="color:#dde0ff">never stored</strong> on server &middot; '
        'Download direct to your device</p>'
        '<div class="badge-row">'
        + fb +
        '<span class="badge blue">&#x2601;&#xFE0F; In-Memory Processing</span>'
        '<span class="badge purple">&#x1F4E6; Up to ' + lim_disp + ' per file</span>'
        '<span class="badge green">&#x1F512; Privacy First</span>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def make_chip(status):
    labels = {
        "pending": "&#x23F3; Pending",
        "queued":  "&#x1F550; Queued",
        "running": "&#x2699;&#xFE0F; Converting",
        "done":    "&#x2705; Done",
        "error":   "&#x274C; Error",
    }
    return (
        '<span class="chip ' + status + '">'
        + labels.get(status, status)
        + "</span>"
    )


def make_prog(pct, status):
    cls = "done" if status == "done" else "error" if status == "error" else ""
    w = 100 if status in ("done", "error") else max(0, pct)
    return (
        '<div class="prog-wrap">'
        '<div class="prog-track">'
        '<div class="prog-fill ' + cls + '" style="width:' + str(w) + '%"></div>'
        "</div>"
        '<div class="prog-pct">' + str(w) + "%</div>"
        "</div>"
    )


def render_overall(results):
    total = len(results)
    if not total:
        return
    done    = sum(1 for r in results if r["status"] == "done")
    errors  = sum(1 for r in results if r["status"] == "error")
    running = sum(1 for r in results if r["status"] == "running")
    queued  = sum(1 for r in results if r["status"] in ("queued", "pending"))
    pct     = round((done + errors) / total * 100)
    is_fin  = (done + errors) == total
    fill_cls = "done" if is_fin else ""

    if is_fin and errors == 0:
        label = "&#x1F389; All done!"
    elif is_fin:
        label = "Completed with {} error(s)".format(errors)
    else:
        label = "Converting&hellip; ({}/{} done)".format(done, total)

    html = (
        '<div class="overall-card">'
        '<div class="overall-top">'
        '<span class="overall-label">' + label + "</span>"
        '<span class="overall-pct">' + str(pct) + "%</span>"
        "</div>"
        '<div class="overall-track">'
        '<div class="overall-fill ' + fill_cls + '" style="width:' + str(pct) + '%"></div>'
        "</div>"
        '<div class="stats-row">'
        '<div class="stat-item"><div class="sdot amber"></div><span>' + str(queued) + " queued</span></div>"
        '<div class="stat-item"><div class="sdot purple"></div><span>' + str(running) + " converting</span></div>"
        '<div class="stat-item"><div class="sdot green"></div><span>' + str(done) + " done</span></div>"
        '<div class="stat-item"><div class="sdot red"></div><span>' + str(errors) + " error(s)</span></div>"
        "</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_file_table(results):
    if not results:
        return
    rows = ""
    for r in results:
        sz   = fmt_bytes(r.get("size", 0))
        name = r["orig_name"]
        disp = name[:46] + ("&hellip;" if len(name) > 46 else "")
        rows += (
            "<tr>"
            '<td style="font-size:1.1rem">&#x1F3AC;</td>'
            '<td title="' + name + '">' + disp + "</td>"
            '<td style="color:#6868a0;white-space:nowrap">' + sz + "</td>"
            '<td style="color:#9d95ff">' + r["mp3_name"] + "</td>"
            "<td>" + make_chip(r["status"]) + "</td>"
            "<td>" + make_prog(r.get("progress", 0), r["status"]) + "</td>"
            "</tr>"
        )
    html = (
        '<div class="sec-card">'
        '<div class="sec-title">&#x1F4CB; Conversion Queue</div>'
        '<table class="file-table">'
        "<thead><tr>"
        "<th></th>"
        "<th>Source File</th>"
        "<th>Size</th>"
        "<th>Output</th>"
        "<th>Status</th>"
        "<th>Progress</th>"
        "</tr></thead>"
        "<tbody>" + rows + "</tbody>"
        "</table>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_limit_info():
    lim_mb, lim_disp = get_limit_info()

    st.markdown(
        '<div class="limit-box">'
        "<h3>&#x26A0;&#xFE0F; Default Streamlit upload limit is only 200 MB</h3>"
        "<p>To upload files up to <strong>10 GB</strong> you must configure "
        "Streamlit before starting. The <code>.streamlit/config.toml</code> "
        "file in this project already sets it to <strong>10 GB</strong>.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.expander(
        "📖 Setup Guide — How to enable 10 GB uploads",
        expanded=(lim_mb < 500),
    ):
        st.markdown(
            "### Method 1 — `.streamlit/config.toml` (already included)\n\n"
            "Create `.streamlit/config.toml` next to your script:\n"
            "```toml\n"
            "[server]\n"
            "maxUploadSize = 10240\n"
            "```\n"
            "Then run normally:\n"
            "```bash\n"
            "streamlit run streamlit_app.py\n"
            "```\n\n"
            "---\n\n"
            "### Method 2 — Command-line flag\n"
            "```bash\n"
            "streamlit run streamlit_app.py --server.maxUploadSize=10240\n"
            "```\n\n"
            "---\n\n"
            "### Method 3 — Environment variable\n"
            "```bash\n"
            "# Linux / Mac\n"
            "STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10240 streamlit run streamlit_app.py\n\n"
            "# Windows PowerShell\n"
            "$env:STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10240\n"
            "streamlit run streamlit_app.py\n"
            "```\n\n"
            "---\n\n"
            "### Streamlit Cloud deployment\n"
            "Commit `.streamlit/config.toml` to your GitHub repo:\n"
            "```toml\n"
            "[server]\n"
            "maxUploadSize = 10240\n"
            "headless = true\n"
            "```"
        )

    if lim_mb >= 1024:
        st.markdown(
            '<div class="ok-box">&#x2705; Upload limit is '
            "<strong>" + lim_disp + "</strong> &mdash; large files supported.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="warn-box">&#x26A0;&#xFE0F; Current limit is '
            "<strong>" + lim_disp + "</strong>. "
            "Follow the setup guide above to raise it to 10 GB.</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
def main():
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()

    ffmpeg_ok = check_ffmpeg()
    render_hero(ffmpeg_ok)

    # Hard stop if ffmpeg missing
    if not ffmpeg_ok:
        st.markdown(
            '<div class="err-box">'
            "&#x26A0;&#xFE0F; <strong>ffmpeg not found!</strong><br><br>"
            "<strong>Mac:</strong> <code>brew install ffmpeg</code><br>"
            "<strong>Linux:</strong> <code>sudo apt install ffmpeg</code><br>"
            "<strong>Windows:</strong> "
            '<a href="https://www.gyan.dev/ffmpeg/builds/" '
            'target="_blank" style="color:#ff9999">gyan.dev/ffmpeg/builds</a>'
            " &rarr; download, unzip, add to PATH."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # Limit info
    render_limit_info()
    st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

    # ── Audio settings ─────────────────────────────────────────
    st.markdown(
        '<div class="sec-title">&#x2699;&#xFE0F; Audio Quality Settings</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**🎵 Bitrate**")
        bitrate = st.selectbox(
            "Bitrate",
            ["96k", "128k", "192k", "256k", "320k"],
            index=4,
            label_visibility="collapsed",
            key="sel_bitrate",
        )
    with c2:
        st.markdown("**📊 Sample Rate**")
        sample_rate = st.selectbox(
            "Sample Rate",
            ["22050", "44100", "48000", "96000"],
            index=1,
            label_visibility="collapsed",
            key="sel_sr",
        )
    with c3:
        st.markdown("**🎤 Channels**")
        ch_opt = st.selectbox(
            "Channels",
            ["1 - Mono", "2 - Stereo"],
            index=1,
            label_visibility="collapsed",
            key="sel_ch",
        )
    channels = "1" if ch_opt.startswith("1") else "2"

    # Presets
    st.markdown(
        '<div style="margin:.45rem 0 .2rem;font-size:.74rem;'
        "color:#6868a0;font-weight:700;text-transform:uppercase;"
        'letter-spacing:.5px">Quick Presets</div>',
        unsafe_allow_html=True,
    )
    pr1, pr2, pr3, pr4, _gap = st.columns([1, 1, 1, 1, 3])
    with pr1:
        if st.button("🎧 High", use_container_width=True, key="p_hi"):
            st.session_state.update(
                sel_bitrate="320k", sel_sr="44100", sel_ch="2 - Stereo"
            )
            st.rerun()
    with pr2:
        if st.button("📱 Standard", use_container_width=True, key="p_std"):
            st.session_state.update(
                sel_bitrate="192k", sel_sr="44100", sel_ch="2 - Stereo"
            )
            st.rerun()
    with pr3:
        if st.button("💾 Compact", use_container_width=True, key="p_cmp"):
            st.session_state.update(
                sel_bitrate="128k", sel_sr="22050", sel_ch="2 - Stereo"
            )
            st.rerun()
    with pr4:
        if st.button("🎙 Voice", use_container_width=True, key="p_vc"):
            st.session_state.update(
                sel_bitrate="128k", sel_sr="22050", sel_ch="1 - Mono"
            )
            st.rerun()

    st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

    # ── File uploader ──────────────────────────────────────────
    _, lim_disp = get_limit_info()
    st.markdown(
        '<div class="sec-title" style="margin-bottom:.5rem">'
        "&#x1F4C1; Upload Video Files</div>",
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Drag and drop or click to browse — up to " + lim_disp + " per file",
        type=["mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "m4v", "ts"],
        accept_multiple_files=True,
        label_visibility="visible",
        key="file_uploader",
    )

    st.markdown(
        '<div class="tip-box">'
        "&#x1F4A1; Files are converted <strong>entirely in memory</strong>. "
        "The <strong>server never stores your videos or audio</strong>. "
        "Output MP3s download directly to your device."
        "</div>",
        unsafe_allow_html=True,
    )

    # Detect file-list change
    if uploaded:
        sig = [(f.name, f.size) for f in uploaded]
        if sig != st.session_state.last_files:
            st.session_state.last_files = sig
            st.session_state.results = [
                {
                    "orig_name": f.name,
                    "mp3_name":  Path(f.name).stem + ".mp3",
                    "size":      f.size,
                    "status":    "pending",
                    "progress":  0,
                    "mp3_bytes": None,
                    "success":   False,
                    "error":     None,
                }
                for f in uploaded
            ]
            st.session_state.done       = False
            st.session_state.converting = False
            st.session_state.zip_bytes  = None

    # Queue display
    if st.session_state.results:
        render_overall(st.session_state.results)
        render_file_table(st.session_state.results)
    else:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-icon">&#x1F39E;&#xFE0F;</div>'
            "<p>Upload video files above to get started</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

    # ── Action buttons ─────────────────────────────────────────
    btn_col, zip_col = st.columns([2, 1])

    with btn_col:
        can_convert = (
            bool(uploaded)
            and not st.session_state.converting
            and ffmpeg_ok
        )
        if st.button(
            "🚀  Convert All to MP3",
            disabled=not can_convert,
            use_container_width=True,
            type="primary",
            key="btn_convert",
        ):
            # Read all bytes NOW before rerun clears the buffer
            snapshots = []
            for f in uploaded:
                try:
                    raw = f.read()
                except Exception:
                    raw = None
                snapshots.append((f.name, f.size, raw))

            st.session_state.results = [
                {
                    "orig_name": name,
                    "mp3_name":  Path(name).stem + ".mp3",
                    "size":      size,
                    "status":    "queued",
                    "progress":  0,
                    "mp3_bytes": None,
                    "success":   False,
                    "error":     None,
                    "_raw":      raw,
                }
                for name, size, raw in snapshots
            ]
            st.session_state.converting = True
            st.session_state.done       = False
            st.session_state.zip_bytes  = None
            st.rerun()

    with zip_col:
        zip_ready = (
            st.session_state.done
            and bool(st.session_state.zip_bytes)
            and len(st.session_state.zip_bytes) > 22
        )
        st.markdown('<div class="zip-wrap">', unsafe_allow_html=True)
        st.download_button(
            label="📦  Download All as ZIP",
            data=st.session_state.zip_bytes or b"empty",
            file_name="converted_mp3s.zip",
            mime="application/zip",
            disabled=not zip_ready,
            use_container_width=True,
            key="btn_zip_top",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════
    #  CONVERSION RUNNER
    # ══════════════════════════════════════════════════════════
    if st.session_state.converting:
        st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

        overall_ph = st.empty()
        table_ph   = st.empty()
        status_ph  = st.empty()

        results = st.session_state.results
        lock    = threading.Lock()

        def do_one(idx):
            r   = results[idx]
            raw = r.pop("_raw", None)
            if raw is None:
                with lock:
                    r["status"] = "error"
                    r["error"]  = "Could not read file — please re-upload."
                return
            with lock:
                r["status"]   = "running"
                r["progress"] = 5

            mp3, err = convert_to_mp3_inmemory(
                raw,
                r["orig_name"],
                bitrate,
                sample_rate,
                channels,
            )
            with lock:
                if err:
                    r["status"]   = "error"
                    r["error"]    = err
                    r["success"]  = False
                    r["progress"] = 0
                else:
                    r["status"]    = "done"
                    r["mp3_bytes"] = mp3
                    r["success"]   = True
                    r["progress"]  = 100

        valid_indices = [
            i for i, r in enumerate(results)
            if r.get("_raw") is not None
        ]
        max_workers = min(3, max(1, len(valid_indices)))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(do_one, i): i
                for i in valid_indices
            }
            while futures:
                finished_now = {f for f in futures if f.done()}
                for f in finished_now:
                    del futures[f]

                with overall_ph.container():
                    render_overall(results)
                with table_ph.container():
                    render_file_table(results)

                n_fin = sum(
                    1 for r in results
                    if r["status"] in ("done", "error")
                )
                status_ph.markdown(
                    "**⚙️  Processing… {}/{} complete**".format(
                        n_fin, len(results)
                    )
                )
                if futures:
                    time.sleep(0.8)

        # Final render
        with overall_ph.container():
            render_overall(results)
        with table_ph.container():
            render_file_table(results)
        status_ph.empty()

        # Build ZIP
        done_list = [
            r for r in results
            if r["status"] == "done" and r.get("mp3_bytes")
        ]
        if done_list:
            st.session_state.zip_bytes = build_zip(done_list)

        st.session_state.converting = False
        st.session_state.done       = True
        st.session_state.results    = results
        st.rerun()

    # ══════════════════════════════════════════════════════════
    #  DOWNLOAD SECTION
    # ══════════════════════════════════════════════════════════
    done_results  = [
        r for r in st.session_state.results
        if r.get("status") == "done" and r.get("mp3_bytes")
    ]
    error_results = [
        r for r in st.session_state.results
        if r.get("status") == "error"
    ]

    if done_results or error_results:
        st.markdown('<hr class="my-divider">', unsafe_allow_html=True)

        # Error list
        for r in error_results:
            st.markdown(
                '<div class="err-box">'
                "&#x274C; <strong>" + r["orig_name"] + "</strong><br>"
                + r.get("error", "Unknown error")
                + "</div>",
                unsafe_allow_html=True,
            )

        # Individual downloads
        if done_results:
            st.markdown(
                '<div class="sec-title">'
                "&#x2B07;&#xFE0F; Download Converted Files</div>",
                unsafe_allow_html=True,
            )

            per_row = 2
            for row_start in range(0, len(done_results), per_row):
                batch = done_results[row_start: row_start + per_row]
                cols  = st.columns(per_row)
                for col, r in zip(cols, batch):
                    with col:
                        sz = fmt_bytes(len(r["mp3_bytes"]))
                        st.markdown(
                            "**" + r["mp3_name"] + "** "
                            '<span style="color:#6868a0;font-size:.76rem">'
                            "(" + sz + ")</span>",
                            unsafe_allow_html=True,
                        )
                        st.download_button(
                            label=("⬇️  " + r["mp3_name"]),
                            data=r["mp3_bytes"],
                            file_name=r["mp3_name"],
                            mime="audio/mpeg",
                            use_container_width=True,
                            key="dl_{}_{}".format(row_start, r["mp3_name"]),
                        )

            # ZIP at bottom
            if st.session_state.zip_bytes and len(done_results) > 1:
                st.markdown('<hr class="my-divider">', unsafe_allow_html=True)
                st.markdown('<div class="zip-wrap">', unsafe_allow_html=True)
                st.download_button(
                    label="📦  Download All {} Files as ZIP".format(
                        len(done_results)
                    ),
                    data=st.session_state.zip_bytes,
                    file_name="converted_mp3s.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="btn_zip_bottom",
                )
                st.markdown("</div>", unsafe_allow_html=True)

            # Summary
            n_ok   = len(done_results)
            n_fail = len(error_results)
            if n_fail == 0:
                st.markdown(
                    '<div class="success-box">'
                    "&#x1F389; All {} file(s) converted successfully! "
                    "Click the buttons above to download your MP3s."
                    "</div>".format(n_ok),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="warn-box">'
                    "&#x2705; {} converted &middot; "
                    "&#x274C; {} failed &mdash; see errors above."
                    "</div>".format(n_ok, n_fail),
                    unsafe_allow_html=True,
                )

    # Footer
    st.markdown(
        '<div style="text-align:center;padding:2.5rem 0 .5rem;'
        "color:#2a2a50;font-size:.74rem;letter-spacing:.3px\">"
        "Bulk MP4 &rarr; MP3 Converter Pro &nbsp;&middot;&nbsp; "
        "In-Memory Edition &nbsp;&middot;&nbsp; Powered by ffmpeg"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
