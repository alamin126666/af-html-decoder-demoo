#!/usr/bin/env python3
import asyncio, os, re, pickle, logging, tempfile, base64, html as html_module
from datetime import datetime
from threading import Thread
from dotenv import load_dotenv
load_dotenv()
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode
from playwright.async_api import async_playwright

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
OWNER_ID       = int(os.environ.get("OWNER_ID", "0"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "BDALAMINHACKER")
DB_FILE        = "database.pkl"
if not BOT_TOKEN: raise ValueError("BOT_TOKEN not set.")
if not OWNER_ID:  raise ValueError("OWNER_ID not set.")

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
@flask_app.route("/")
def home(): return "Bot is alive!"
def run_flask(): flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

def _default_db():
    return {"users": {}, "admins": [], "channels": [], "settings": {"bot_active": True}, "stats": {"total_decodes": 0}}

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "rb") as f: data = pickle.load(f)
            for k, v in _default_db().items(): data.setdefault(k, v)
            return data
        except Exception as e: logger.error(f"DB load error: {e}")
    return _default_db()

def save_db(db):
    try:
        with open(DB_FILE, "wb") as f: pickle.dump(db, f)
    except Exception as e: logger.error(f"DB save error: {e}")

db = load_db()

def is_owner(uid): return uid == OWNER_ID
def is_admin(uid): return uid == OWNER_ID or uid in db["admins"]
def is_banned(uid): return db["users"].get(uid, {}).get("banned", False)
def bot_active(): return db["settings"].get("bot_active", True)

def register_user(user):
    if user.id not in db["users"]:
        db["users"][user.id] = {"username": user.username or "", "name": user.full_name or "",
                                "joined": datetime.now().isoformat(), "banned": False, "private_acked": []}
        save_db(db)
    elif "private_acked" not in db["users"][user.id]:
        db["users"][user.id]["private_acked"] = []; save_db(db)

async def check_channels(bot, uid):
    if not db["channels"]: return True, []
    acked, missing = db["users"].get(uid, {}).get("private_acked", []), []
    for ch in db["channels"]:
        try:
            m = await bot.get_chat_member(ch["id"], uid)
            if m.status in ("left", "kicked"): missing.append(ch)
        except Exception:
            if not (ch.get("type") == "private" and ch["id"] in acked): missing.append(ch)
    return len(missing) == 0, missing

# ══════════════════════════════════════════════════════
#   KEYBOARDS
# ══════════════════════════════════════════════════════
def channels_inline_kb(missing):
    rows = []
    for ch in missing:
        icon = "🔐" if ch.get("type") == "private" else "📡"
        rows.append([InlineKeyboardButton(f"{icon}  {ch.get('name','Channel')}", url=ch.get("link",""))])
    return InlineKeyboardMarkup(rows)

def joined_reply_kb():
    return ReplyKeyboardMarkup([["✅  𝗜'𝘃𝗲 𝗝𝗼𝗶𝗻𝗲𝗱 𝗔𝗹𝗹 𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀"]], resize_keyboard=True, one_time_keyboard=True)

def main_kb():
    return ReplyKeyboardMarkup(
        [["⚡  𝗛𝗧𝗠𝗟 𝗗𝗲𝗰𝗼𝗱𝗲𝗿",  "🧑‍💻  𝗗𝗲𝘃𝗲𝗹𝗼𝗽𝗲𝗿"]],
        resize_keyboard=True,
    )

# ══════════════════════════════════════════════════════
#   WELCOME
# ══════════════════════════════════════════════════════
async def send_welcome(bot, chat_id, first_name):
    txt = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "  🧬  <b>𝗛𝗧𝗠𝗟  𝗗𝗘𝗖𝗢𝗗𝗘𝗥  𝗕𝗢𝗧</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👾  𝖧𝖾𝗒 <b>{first_name}</b>!  𝖶𝖾𝗅𝖼𝗈𝗆𝖾 𝖺𝖻𝗈𝖺𝗋𝖽.\n\n"
        "𝙸 𝚌𝚊𝚗 𝚒𝚗𝚜𝚝𝚊𝚗𝚝𝚕𝚢 𝚍𝚎𝚌𝚛𝚢𝚙𝚝 𝚊𝚗𝚢\n"
        "𝚎𝚗𝚌𝚛𝚢𝚙𝚝𝚎𝚍 <b>.html</b> 𝚏𝚒𝚕𝚎 𝚢𝚘𝚞 𝚜𝚎𝚗𝚍.\n\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "⚙️  <b>𝗗𝗲𝗰𝗿𝘆𝗽𝘁𝗶𝗼𝗻 𝗘𝗻𝗴𝗶𝗻𝗲𝘀</b>\n"
        "◈  ⚡ <b>𝗽𝗵𝗽𝗸𝗼𝗯𝗼</b>   ╌  𝖺𝗎𝗍𝗈-𝖽𝖾𝗍𝖾𝖼𝗍𝖾𝖽\n"
        "◈  🔴 <b>𝗥𝗗𝗫 𝗩𝟳.𝟭</b>  ╌  𝖺𝗎𝗍𝗈-𝖽𝖾𝗍𝖾𝖼𝗍𝖾𝖽\n"
        "◈  🖥️ <b>𝗦𝗲𝗿𝘃𝗲𝗿</b>   ╌  𝗌𝗍𝖺𝗇𝖽𝖺𝗋𝖽 𝖾𝗇𝖼\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n\n"
        "𝖴𝗌𝖾 𝗍𝗁𝖾 𝗆𝖾𝗇𝗎 𝖻𝖾𝗅𝗈𝗐 𝗍𝗈 𝗀𝖾𝗍 𝗌𝗍𝖺𝗋𝗍𝖾𝖽 ↓"
    )
    await bot.send_message(chat_id, txt, parse_mode=ParseMode.HTML, reply_markup=main_kb())

def ban_text(uid):
    return (
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "  🚷  <b>𝗔𝗖𝗖𝗘𝗦𝗦  𝗗𝗘𝗡𝗜𝗘𝗗</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "𝚈𝚘𝚞 𝚑𝚊𝚟𝚎 𝚋𝚎𝚎𝚗 <b>𝗯𝗮𝗻𝗻𝗲𝗱</b> 𝚏𝚛𝚘𝚖 𝚝𝚑𝚒𝚜 𝚋𝚘𝚝.\n\n"
        f"🪪  <b>𝗬𝗼𝘂𝗿 𝗜𝗗</b>  ╌  <code>{uid}</code>\n"
        f"👑  <b>𝗢𝘄𝗻𝗲𝗿</b>   ╌  @{OWNER_USERNAME}\n\n"
        "𝙲𝚘𝚗𝚝𝚊𝚌𝚝 𝚝𝚑𝚎 𝙾𝚠𝚗𝚎𝚛 𝚠𝚒𝚝𝚑 𝚢𝚘𝚞𝚛 𝙸𝙳 𝚝𝚘 𝚛𝚎𝚚𝚞𝚎𝚜𝚝 𝚞𝚗𝚋𝚊𝚗."
    )

# ══════════════════════════════════════════════════════
#   BROWSER RENDERER  (returns html + screenshot bytes)
# ══════════════════════════════════════════════════════
async def render_html(path):
    """Load HTML in headless browser -> returns (decoded_html, screenshot_bytes)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        page    = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(f"file://{os.path.abspath(path)}", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        html       = await page.evaluate("() => document.documentElement.outerHTML")
        screenshot = await page.screenshot(full_page=True, type="png")
        await browser.close()
    return html, screenshot

async def take_screenshot(html_path):
    """Load an already-decoded HTML file and capture a full-page screenshot."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        page    = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(f"file://{os.path.abspath(html_path)}", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        screenshot = await page.screenshot(full_page=True, type="png")
        await browser.close()
    return screenshot

# ══════════════════════════════════════════════════════
#   PHPKOBO ENGINE
# ══════════════════════════════════════════════════════
def _js_unescape(s):
    s = s.replace('\n', '\\n')
    s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
    s = s.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
    return s

def detect_phpkobo(html):
    sm = re.search(r'<script[^>]*>([\s\S]*?)<\/script>', html, re.IGNORECASE)
    if not sm: return False
    sc = sm.group(1).lstrip(';').strip()
    return 'Function("' in sc or "Function('" in sc

def decode_phpkobo(html):
    sm = re.search(r'<script[^>]*>([\s\S]*?)<\/script>', html, re.IGNORECASE)
    if not sm: raise ValueError("No <script> tag found")
    sc = sm.group(1).lstrip(';').strip()
    if 'Function("' in sc:
        inner = sc[sc.index('Function("')+10 : sc.rindex('")()')  ]
    elif "Function('" in sc:
        inner = sc[sc.index("Function('")+10 : sc.rindex("')()")  ]
    else: raise ValueError("phpkobo wrapper not found")
    code = _js_unescape(inner)
    p    = code.find('_Srkpv=')
    if p < 0: raise ValueError("_Srkpv not found")
    qs    = code.index('"', p+7)+1
    qe    = code.index('";', qs)
    srkpv = code[qs:qe].rstrip('\\').rstrip('"')
    bi    = srkpv.find('B')
    if bi < 0: raise ValueError("B marker not found")
    sp    = srkpv[bi+1:].rstrip('\\').rstrip('"')
    if len(sp) < 8: raise ValueError("Payload too short")
    hdr   = sp[-8:]; step = int(hdr[4:6],16); start = int(hdr[6:8],16); sp = sp[:-8]
    sp    = re.sub(r'[Xx]','e', re.sub(r'[Yy]','a', re.sub(r'[Zz]','c', sp)))
    sp    = re.sub(r'[^0-9a-fA-F]','0', sp)
    pairs = re.findall(r'.{2}', sp)
    if not pairs: raise ValueError("No hex pairs")
    W = [0]*256; j = start
    for i in range(256): W[j] = i; j = (j+step)%256
    bv = [(int(px,16)-W[i%256]+256)%256 for i,px in enumerate(pairs)]
    r  = bytes(bv).decode('utf-8', errors='replace')
    if len(r) < 30: raise ValueError("Result too short")
    return r

# ══════════════════════════════════════════════════════
#   RDX DECODER V7.1 ENGINE
# ══════════════════════════════════════════════════════
def detect_rdx(html_content):
    """
    Auto-detect RDX V7.1 encoded HTML files.
    Checks for multiple RDX encoding signatures.
    """
    patterns = [
        # Dean Edwards packer style
        r'eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k\s*,\s*e\s*,\s*[dr]\s*\)',
        # Base64 wrapped eval
        r'eval\s*\(\s*atob\s*\(',
        # RDX specific marker
        r'(?:var|let|const)\s+[_$]?[0-9a-zA-Z]{1,6}\s*=\s*["\'](?:[A-Za-z0-9+/]{50,}={0,2})["\']',
        # unescape + fromCharCode patterns
        r'document\.write\s*\(\s*unescape\s*\(',
        # String.fromCharCode massive array
        r'String\.fromCharCode\s*\(\s*(?:\d+\s*,\s*){20,}',
        # Hex encoded string with eval
        r'eval\s*\(\s*["\']\\x',
        # RDX V7 specific: encoded with specific length markers
        r'<script[^>]*>[^<]{200,}<\/script>',
    ]
    for pat in patterns:
        if re.search(pat, html_content, re.IGNORECASE | re.DOTALL):
            return True
    return False

def _rdx_decode_packer(script_content):
    """Decode Dean Edwards p,a,c,k,e,d packer."""
    m = re.search(
        r"eval\s*\(\s*function\s*\(p,a,c,k,e,(?:r|d)\)\s*\{.*?\}\s*\('(.*?)',\s*(\d+),\s*(\d+),\s*'(.*?)'\.split\('\|'\)",
        script_content, re.DOTALL
    )
    if not m:
        return None
    payload, base, count, keys_str = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    keys = keys_str.split('|')

    def unbase(num, base):
        chars = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        result = ''
        while num > 0:
            result = chars[num % base] + result
            num //= base
        return result or '0'

    def lookup(word):
        idx_str = unbase(int(word, 10) if word.isdigit() else int(word, base), 10)
        try:
            idx = int(word, base)
            if idx < len(keys) and keys[idx]:
                return keys[idx]
        except Exception:
            pass
        return word

    decoded = re.sub(r'\b(\w+)\b', lambda m2: lookup(m2.group(0)), payload)
    return decoded

def _rdx_decode_atob(script_content):
    """Decode eval(atob(...)) style encoding."""
    # Match eval(atob("...")) or eval(atob('...'))
    m = re.search(r'eval\s*\(\s*atob\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']\s*\)', script_content)
    if not m:
        return None
    try:
        return base64.b64decode(m.group(1)).decode('utf-8', errors='replace')
    except Exception:
        return None

def _rdx_decode_fromcharcode(script_content):
    """Decode String.fromCharCode(...) patterns."""
    m = re.search(r'String\.fromCharCode\s*\(([\d\s,]+)\)', script_content)
    if not m:
        return None
    try:
        codes = [int(x.strip()) for x in m.group(1).split(',') if x.strip().isdigit()]
        return ''.join(chr(c) for c in codes)
    except Exception:
        return None

def _rdx_decode_unescape(script_content):
    """Decode unescape(%xx%xx...) patterns."""
    m = re.search(r'unescape\s*\(\s*["\']([%0-9a-fA-F]+)["\']\s*\)', script_content)
    if not m:
        return None
    try:
        import urllib.parse
        return urllib.parse.unquote(m.group(1))
    except Exception:
        return None

def _rdx_decode_hex_eval(script_content):
    """Decode eval("\\xHH\\xHH...") hex escape patterns."""
    m = re.search(r'eval\s*\(\s*["\']((\\x[0-9a-fA-F]{2})+)["\']\s*\)', script_content)
    if not m:
        return None
    try:
        hex_str = m.group(1)
        result = re.sub(r'\\x([0-9a-fA-F]{2})', lambda h: chr(int(h.group(1), 16)), hex_str)
        return result
    except Exception:
        return None

def _rdx_decode_base64_var(html_content):
    """Decode large base64 variable assignment patterns."""
    m = re.search(
        r'(?:var|let|const)\s+[_$]?[0-9a-zA-Z]{1,8}\s*=\s*["\']([A-Za-z0-9+/]{50,}={0,2})["\']',
        html_content
    )
    if not m:
        return None
    try:
        decoded = base64.b64decode(m.group(1)).decode('utf-8', errors='replace')
        if len(decoded) > 50 and ('<' in decoded or 'document' in decoded or 'window' in decoded):
            return decoded
    except Exception:
        pass
    return None

def _rdx_inline_script_decode(html_content):
    """Extract and try all methods on inline scripts."""
    scripts = re.findall(r'<script[^>]*>([\s\S]*?)<\/script>', html_content, re.IGNORECASE)
    for sc in scripts:
        sc = sc.strip()
        if not sc:
            continue
        for decoder in [_rdx_decode_packer, _rdx_decode_atob, _rdx_decode_fromcharcode,
                        _rdx_decode_unescape, _rdx_decode_hex_eval]:
            try:
                result = decoder(sc)
                if result and len(result) > 30:
                    return result
            except Exception:
                continue
    return None

def decode_rdx(html_content):
    """
    RDX DECODER V7.1 — Multi-method auto decoder.
    Tries all known RDX encoding techniques in order.
    """
    # Method 1: Inline script decode (packer, atob, fromCharCode, unescape, hex)
    result = _rdx_inline_script_decode(html_content)
    if result:
        # If decoded result is itself HTML-like, return wrapped
        if result.strip().startswith('<'):
            return result
        # Otherwise embed decoded result into a minimal HTML page
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{html_module.unescape(result)}</body></html>"

    # Method 2: Large base64 variable
    result = _rdx_decode_base64_var(html_content)
    if result:
        if result.strip().startswith('<'):
            return result
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{html_module.unescape(result)}</body></html>"

    # Method 3: Try base64 decoding entire script content
    scripts = re.findall(r'<script[^>]*>([\s\S]*?)<\/script>', html_content, re.IGNORECASE)
    for sc in scripts:
        sc_stripped = sc.strip().strip('"\'')
        try:
            # Try pure base64
            padded = sc_stripped + '=' * (-len(sc_stripped) % 4)
            decoded = base64.b64decode(padded).decode('utf-8', errors='replace')
            if len(decoded) > 100 and ('<' in decoded or 'document' in decoded):
                return decoded
        except Exception:
            pass

    raise ValueError("RDX V7.1: No recognizable encoding pattern found in this file.")

# ══════════════════════════════════════════════════════
#   DECODE STEP 1 — READY
# ══════════════════════════════════════════════════════
async def _decode_start(update, context):
    msg = await update.message.reply_text("◌")
    for frame in [
        "◌  𝙸𝚗𝚒𝚝𝚒𝚊𝚕𝚒𝚣𝚒𝚗𝚐...",
        "◈  𝙻𝚘𝚊𝚍𝚒𝚗𝚐 𝚎𝚗𝚐𝚒𝚗𝚎𝚜...",
        "◉  𝙲𝚊𝚕𝚒𝚋𝚛𝚊𝚝𝚒𝚗𝚐 𝚙𝚒𝚙𝚎𝚕𝚒𝚗𝚎...",
        "⊛  𝚁𝚞𝚗𝚗𝚒𝚗𝚐 𝚍𝚒𝚊𝚐𝚗𝚘𝚜𝚝𝚒𝚌𝚜...",
        "⊕  𝙰𝚕𝚕 𝚜𝚢𝚜𝚝𝚎𝚖𝚜 𝚛𝚎𝚊𝚍𝚢...",
        "✦  𝚂𝚢𝚜𝚝𝚎𝚖 𝚁𝚎𝚊𝚍𝚢!",
    ]:
        await asyncio.sleep(0.5)
        try: await msg.edit_text(frame)
        except: pass
    await asyncio.sleep(0.6)
    try: await msg.delete()
    except: pass
    context.user_data["waiting_for_html"] = True
    await update.message.reply_html(
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "  🗂  <b>𝗦𝗲𝗻𝗱 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "𝚂𝚎𝚗𝚍 𝚢𝚘𝚞𝚛 𝚎𝚗𝚌𝚛𝚢𝚙𝚝𝚎𝚍 <b>.html</b> 𝚏𝚒𝚕𝚎 ↓\n\n"
        "🔸  <b>𝗦𝘂𝗽𝗽𝗼𝗿𝘁𝗲𝗱:</b>  .html  ╌  .htm"
    )

# ══════════════════════════════════════════════════════
#   PHPKOBO CHECKLIST ANIMATION
# ══════════════════════════════════════════════════════
_PK = [
    ("🔎", "𝙴𝚗𝚌𝚛𝚢𝚙𝚝𝚒𝚘𝚗 𝚝𝚢𝚙𝚎  ╌  𝗽𝗵𝗽𝗸𝗼𝗯𝗼"),
    ("🔑", "𝙵𝚞𝚗𝚌𝚝𝚒𝚘𝚗 𝚠𝚛𝚊𝚙𝚙𝚎𝚛 𝚕𝚘𝚌𝚊𝚝𝚎𝚍"),
    ("📦", "𝙿𝚊𝚢𝚕𝚘𝚊𝚍 𝚎𝚡𝚝𝚛𝚊𝚌𝚝𝚎𝚍"),
    ("🧩", "𝙱-𝙼𝚊𝚛𝚔𝚎𝚛 𝚏𝚘𝚞𝚗𝚍"),
    ("📐", "𝙲𝚒𝚙𝚑𝚎𝚛 𝚑𝚎𝚊𝚍𝚎𝚛 𝚊𝚗𝚊𝚕𝚢𝚣𝚎𝚍"),
    ("🔓", "𝙱𝚢𝚝𝚎𝚜 𝚍𝚎𝚌𝚛𝚢𝚙𝚝𝚎𝚍"),
    ("💾", "𝙾𝚞𝚝𝚙𝚞𝚝 𝚜𝚊𝚟𝚎𝚍"),
]

def _pk_msg(cur):
    h = "⚡  <b>𝗣𝗛𝗣𝗞𝗢𝗕𝗢  𝗗𝗲𝗰𝗿𝘆𝗽𝘁𝗶𝗼𝗻  𝗘𝗻𝗴𝗶𝗻𝗲</b>\n\n"
    lines = []
    for i,(icon,label) in enumerate(_PK):
        if i < cur:   lines.append(f"  ✦  {icon}  {label}")
        elif i == cur: lines.append(f"  ⟳  {icon}  {label}...")
        else:          lines.append(f"  ◌  {icon}  {label}")
    return h + "\n".join(lines)

# ══════════════════════════════════════════════════════
#   RDX CHECKLIST ANIMATION
# ══════════════════════════════════════════════════════
_RDX = [
    ("🔎", "𝙴𝚗𝚌𝚛𝚢𝚙𝚝𝚒𝚘𝚗 𝚝𝚢𝚙𝚎  ╌  𝗥𝗗𝗫 𝗩𝟳.𝟭"),
    ("🔬", "𝚂𝚌𝚊𝚗𝚗𝚒𝚗𝚐 𝚜𝚌𝚛𝚒𝚙𝚝 𝚕𝚊𝚢𝚎𝚛𝚜"),
    ("🧩", "𝙴𝚗𝚌𝚘𝚍𝚒𝚗𝚐 𝚙𝚊𝚝𝚝𝚎𝚛𝚗 𝚒𝚍𝚎𝚗𝚝𝚒𝚏𝚒𝚎𝚍"),
    ("📦", "𝙿𝚊𝚢𝚕𝚘𝚊𝚍 𝚎𝚡𝚝𝚛𝚊𝚌𝚝𝚎𝚍"),
    ("🔑", "𝙳𝚎𝚌𝚘𝚍𝚎 𝚔𝚎𝚢 𝚛𝚎𝚜𝚘𝚕𝚟𝚎𝚍"),
    ("🔓", "𝙻𝚊𝚢𝚎𝚛𝚜 𝚍𝚎𝚌𝚛𝚢𝚙𝚝𝚎𝚍"),
    ("💾", "𝙾𝚞𝚝𝚙𝚞𝚝 𝚜𝚊𝚟𝚎𝚍"),
]

def _rdx_msg(cur):
    h = "🔴  <b>𝗥𝗗𝗫  𝗗𝗘𝗖𝗢𝗗𝗘𝗥  𝗩𝟳.𝟭  𝗘𝗻𝗴𝗶𝗻𝗲</b>\n\n"
    lines = []
    for i,(icon,label) in enumerate(_RDX):
        if i < cur:    lines.append(f"  ✦  {icon}  {label}")
        elif i == cur: lines.append(f"  ⟳  {icon}  {label}...")
        else:          lines.append(f"  ◌  {icon}  {label}")
    return h + "\n".join(lines)

# ══════════════════════════════════════════════════════
#   BROWSER PROGRESS BAR ANIMATION
# ══════════════════════════════════════════════════════
_BR = [
    (0,  "𝙴𝚗𝚌𝚛𝚢𝚙𝚝𝚒𝚘𝚗 𝚝𝚢𝚙𝚎  ╌  𝗦𝘁𝗮𝗻𝗱𝗮𝗿𝗱"),
    (15, "𝙻𝚊𝚞𝚗𝚌𝚑𝚒𝚗𝚐 𝚂𝚎𝚛𝚟𝚎𝚛..."),
    (30, "𝙻𝚘𝚊𝚍𝚒𝚗𝚐 𝚂𝚎𝚛𝚟𝚎𝚛..."),
    (45, "𝚂𝚎𝚛𝚟𝚎𝚛 𝚛𝚞𝚗𝚗𝚒𝚗𝚐..."),
    (60, "𝚂𝚌𝚊𝚗𝚗𝚒𝚗𝚐 𝙷𝚃𝙼𝙻..."),
    (75, "𝚁𝚎𝚗𝚍𝚎𝚛𝚒𝚗𝚐 𝙷𝚝𝚖𝚕..."),
    (88, "𝙱𝚞𝚒𝚕𝚍𝚒𝚗𝚐 𝚘𝚞𝚝𝚙𝚞𝚝..."),
    (95, "𝙵𝚒𝚗𝚊𝚕𝚒𝚣𝚒𝚗𝚐..."),
]

def _br_msg(idx):
    pct, label = _BR[idx % len(_BR)]
    bar = "█"*int(pct/10) + "░"*(10-int(pct/10))
    return (
        f"🖥️  <b>𝗦𝗲𝗿𝘃𝗲𝗿  𝗙𝗲𝗰𝗵  𝗘𝗻𝗴𝗶𝗻𝗲</b>\n\n"
        f"  [{bar}]  {pct}%\n\n"
        f"  🔹  {label}"
    )

# ══════════════════════════════════════════════════════
#   DECODE STEP 2 — PROCESS
# ══════════════════════════════════════════════════════
async def _do_decode(update, context, doc, fname):
    msg = await update.message.reply_text("🛰️  𝙴𝚜𝚝𝚊𝚋𝚕𝚒𝚜𝚑𝚒𝚗𝚐 𝚌𝚘𝚗𝚗𝚎𝚌𝚝𝚒𝚘𝚗...")
    for s in ["📥  𝙳𝚘𝚠𝚗𝚕𝚘𝚊𝚍𝚒𝚗𝚐 𝚏𝚒𝚕𝚎...", "🔬  𝙸𝚗𝚜𝚙𝚎𝚌𝚝𝚒𝚗𝚐 𝚜𝚝𝚛𝚞𝚌𝚝𝚞𝚛𝚎...", "🧪  𝙰𝚗𝚊𝚕𝚢𝚣𝚒𝚗𝚐 𝚎𝚗𝚌𝚛𝚢𝚙𝚝𝚒𝚘𝚗..."]:
        await asyncio.sleep(0.8)
        try: await msg.edit_text(s)
        except: pass
    try:
        file_obj = await context.bot.get_file(doc.file_id)
        with tempfile.TemporaryDirectory() as tmp:
            in_path  = os.path.join(tmp, fname)
            await file_obj.download_to_drive(in_path)
            base     = fname.rsplit(".", 1)
            out_name = f"{base[0]}_decoded.{base[1]}" if len(base)==2 else f"{fname}_decoded"
            out_path = os.path.join(tmp, out_name)
            with open(in_path, "r", encoding="utf-8", errors="replace") as f: raw = f.read()

            if detect_phpkobo(raw):
                # ── PhpKobo engine ──────────────────────────────────────
                for step in range(len(_PK)):
                    try: await msg.edit_text(_pk_msg(step), parse_mode=ParseMode.HTML)
                    except: pass
                    await asyncio.sleep(0.55)
                decoded = decode_phpkobo(raw)
                method  = "⚡  𝗽𝗵𝗽𝗸𝗼𝗯𝗼 𝚎𝚗𝚐𝚒𝚗𝚎"
                with open(out_path, "w", encoding="utf-8") as f: f.write(decoded)
                try: await msg.edit_text("📸  𝙲𝚊𝚙𝚝𝚞𝚛𝚒𝚗𝚐 𝚜𝚌𝚛𝚎𝚎𝚗𝚜𝚑𝚘𝚝...")
                except: pass
                screenshot = await take_screenshot(out_path)

            elif detect_rdx(raw):
                # ── RDX DECODER V7.1 engine ─────────────────────────────
                for step in range(len(_RDX)):
                    try: await msg.edit_text(_rdx_msg(step), parse_mode=ParseMode.HTML)
                    except: pass
                    await asyncio.sleep(0.55)
                decoded = decode_rdx(raw)
                method  = "🔴  𝗥𝗗𝗫 𝗩𝟳.𝟭 𝚎𝚗𝚐𝚒𝚗𝚎"
                with open(out_path, "w", encoding="utf-8") as f: f.write(decoded)
                try: await msg.edit_text("📸  𝙲𝚊𝚙𝚝𝚞𝚛𝚒𝚗𝚐 𝚜𝚌𝚛𝚎𝚎𝚗𝚜𝚑𝚘𝚝...")
                except: pass
                screenshot = await take_screenshot(out_path)

            else:
                # ── Server / Browser engine ─────────────────────────────
                task = asyncio.create_task(render_html(in_path))
                i = 0
                while not task.done():
                    try: await msg.edit_text(_br_msg(i), parse_mode=ParseMode.HTML)
                    except: pass
                    i += 1; await asyncio.sleep(1.4)
                decoded, screenshot = await task
                method  = "🖥️  𝗦𝗲𝗿𝘃𝗲𝗿 𝙵𝚎𝚌𝚑"
                with open(out_path, "w", encoding="utf-8") as f: f.write(decoded)

            db["stats"]["total_decodes"] = db["stats"].get("total_decodes",0)+1; save_db(db)

            # ── Send screenshot first ──────────────────────────────────
            try: await msg.edit_text("✦  𝙳𝚘𝚗𝚎!  𝚂𝚎𝚗𝚍𝚒𝚗𝚐 𝚛𝚎𝚜𝚞𝚕𝚝𝚜...")
            except: pass
            await asyncio.sleep(0.5)

            import io
            await update.message.reply_photo(
                photo=io.BytesIO(screenshot),
                caption=(
                    f"🖼  <b>𝗣𝗮𝗴𝗲 𝗦𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁</b>\n\n⚙️  <b>𝗠𝗲𝘁𝗵𝗼𝗱</b>  ╌  {method}\n"
                    "📎  𝙵𝚒𝚕𝚎 𝚜𝚎𝚗𝚍𝚒𝚗𝚐 𝚋𝚎𝚕𝚘𝚠 ↓"
                ),
                parse_mode=ParseMode.HTML,
            )

            # ── Send decoded file ──────────────────────────────────────
            with open(out_path, "rb") as f:
                await update.message.reply_document(
                    document=f, filename=out_name,
                    caption=(
                        "╭━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                        "  ✅  <b>𝗗𝗲𝗰𝗼𝗱𝗲 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹!</b>\n"
                        "╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                        f"🗂  <b>𝗙𝗶𝗹𝗲</b>    ╌  <code>{out_name}</code>\n"
                        f"⚙️  <b>𝗠𝗲𝘁𝗵𝗼𝗱</b>  ╌  {method}"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            try: await msg.delete()
            except: pass
    except Exception as e:
        logger.error(f"Decode error: {e}")
        try:
            await msg.edit_text(
                "╭━━━━━━━━━━━━━━━━━━╮\n"
                "  ❌  <b>𝗗𝗲𝗰𝗼𝗱𝗲 𝗙𝗮𝗶𝗹𝗲𝗱</b>\n"
                "╰━━━━━━━━━━━━━━━━━━╯\n\n"
                f"<code>{e}</code>", parse_mode=ParseMode.HTML)
        except: pass

# ══════════════════════════════════════════════════════
#   DEVELOPER INFO
# ══════════════════════════════════════════════════════
async def _dev_info(update, context):
    txt = (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "  🧑‍💻  <b>𝗗𝗲𝘃𝗲𝗹𝗼𝗽𝗲𝗿 𝗣𝗿𝗼𝗳𝗶𝗹𝗲</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "🏷  <b>𝗡𝗮𝗺𝗲</b>   ╌  𝘽𝘿 𝘼𝙇𝘼𝙈𝙄𝙉\n\n"
        "🎯  <b>𝗗𝗿𝗲𝗮𝗺</b>  ╌  𝙃𝙖𝙘𝙠𝙞𝙣𝙜  ♦  𝙏𝙧𝙖𝙙𝙞𝙣𝙜  ♦  𝙈𝙤𝙣𝙚𝙮\n\n"
        "💡  <b>𝗪𝗼𝗿𝗸</b>   ╌  𝙉𝙤𝙩 𝘼𝙣𝙮𝙩𝙝𝙞𝙣𝙜\n\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "𝚃𝚑𝚊𝚗𝚔𝚜 𝚏𝚘𝚛 𝚟𝚒𝚜𝚒𝚝𝚒𝚗𝚐!  𝙸𝚏 𝚢𝚘𝚞 𝚗𝚎𝚎𝚍\n"
        "𝚑𝚎𝚕𝚙, 𝚑𝚒𝚝 𝚝𝚑𝚎 𝚋𝚞𝚝𝚝𝚘𝚗 𝚋𝚎𝚕𝚘𝚠 ↓"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬  𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗗𝗲𝘃𝗲𝗹𝗼𝗽𝗲𝗿", url=f"https://t.me/{OWNER_USERNAME}")]])
    await update.message.reply_html(txt, reply_markup=kb)

# ══════════════════════════════════════════════════════
#   ADMIN PANEL
# ══════════════════════════════════════════════════════
def _panel_text():
    pub  = sum(1 for c in db["channels"] if c.get("type","public")=="public")
    priv = sum(1 for c in db["channels"] if c.get("type")=="private")
    st   = "🟢  𝙾𝚗𝚕𝚒𝚗𝚎" if bot_active() else "🔴  𝙾𝚏𝚏𝚕𝚒𝚗𝚎"
    return (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "  👑  <b>𝗔𝗱𝗺𝗶𝗻  𝗣𝗮𝗻𝗲𝗹</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🤖  <b>𝗦𝘁𝗮𝘁𝘂𝘀</b>    ╌  {st}\n"
        f"👥  <b>𝗨𝘀𝗲𝗿𝘀</b>     ╌  <b>{len(db['users'])}</b>\n"
        f"📡  <b>𝗣𝘂𝗯 𝗖𝗵</b>   ╌  <b>{pub}</b>\n"
        f"🔐  <b>𝗣𝗿𝗶𝘃 𝗖𝗵</b>  ╌  <b>{priv}</b>\n"
        f"🛡  <b>𝗔𝗱𝗺𝗶𝗻𝘀</b>   ╌  <b>{len(db['admins'])}</b>\n"
        f"⚡  <b>𝗗𝗲𝗰𝗼𝗱𝗲𝘀</b>  ╌  <b>{db['stats'].get('total_decodes',0)}</b>"
    )

def _panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡  𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀",  callback_data="admin_channels"),
         InlineKeyboardButton("🛡  𝗔𝗱𝗺𝗶𝗻𝘀",    callback_data="admin_admins")],
        [InlineKeyboardButton("🚷  𝗕𝗮𝗻",         callback_data="admin_ban"),
         InlineKeyboardButton("✅  𝗨𝗻𝗯𝗮𝗻",       callback_data="admin_unban")],
        [InlineKeyboardButton("📣  𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁",  callback_data="admin_broadcast"),
         InlineKeyboardButton("🗄  𝗗𝗕 𝗘𝘅𝗽𝗼𝗿𝘁", callback_data="admin_export")],
        [InlineKeyboardButton("🔴  𝗧𝘂𝗿𝗻 𝗕𝗼𝘁 𝗢𝗙𝗙" if bot_active() else "🟢  𝗧𝘂𝗿𝗻 𝗕𝗼𝘁 𝗢𝗡",
                              callback_data="admin_toggle_bot")],
    ])

async def _show_admin_panel(update, context):
    await update.message.reply_html(_panel_text(), reply_markup=_panel_kb())

# ══════════════════════════════════════════════════════
#   COMMAND HANDLERS
# ══════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    if not bot_active() and not is_admin(user.id):
        await update.message.reply_text("🔴  𝗕𝗼𝘁 𝗶𝘀 𝗼𝗳𝗳𝗹𝗶𝗻𝗲.  𝙿𝚕𝚎𝚊𝚜𝚎 𝚝𝚛𝚢 𝚊𝚐𝚊𝚒𝚗 𝚕𝚊𝚝𝚎𝚛."); return
    if is_banned(user.id):
        await update.message.reply_html(ban_text(user.id)); return
    joined, missing = await check_channels(context.bot, user.id)
    if not joined:
        n = len(missing)
        await update.message.reply_html(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "  📡  <b>𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝗩𝗲𝗿𝗶𝗳𝗶𝗰𝗮𝘁𝗶𝗼𝗻</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"𝙹𝚘𝚒𝚗 <b>{n}</b> 𝚌𝚑𝚊𝚗𝚗𝚎𝚕{'𝚜' if n>1 else ''} 𝚝𝚘 𝚞𝚜𝚎 𝚝𝚑𝚒𝚜 𝚋𝚘𝚝.\n\n"
            "𝚃𝚊𝚙 𝚋𝚎𝚕𝚘𝚠 𝚝𝚘 𝚓𝚘𝚒𝚗, 𝚝𝚑𝚎𝚗 𝚙𝚛𝚎𝚜𝚜 𝚝𝚑𝚎 𝚋𝚞𝚝𝚝𝚘𝚗 ↓",
            reply_markup=joined_reply_kb(),
        )
        await update.message.reply_text("🗂  𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀 𝘁𝗼 𝗝𝗼𝗶𝗻:", reply_markup=channels_inline_kb(missing))
        return
    await send_welcome(context.bot, user.id, user.first_name)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data.startswith("admin_"):
        if not is_admin(q.from_user.id):
            await q.answer("❌  𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱!", show_alert=True); return
        await _admin_cb(update, context, q.data)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not bot_active() and not is_admin(user.id): return
    if is_banned(user.id): return
    if not context.user_data.get("waiting_for_html"):
        await update.message.reply_html(
            "⚠️  𝙿𝚛𝚎𝚜𝚜  <b>⚡ 𝗛𝗧𝗠𝗟 𝗗𝗲𝗰𝗼𝗱𝗲𝗿</b>  𝚏𝚒𝚛𝚜𝚝.", reply_markup=main_kb()); return
    doc   = update.message.document
    fname = doc.file_name or "file.html"
    if not (fname.lower().endswith(".html") or fname.lower().endswith(".htm")):
        await update.message.reply_html("⚠️  𝙾𝚗𝚕𝚢 <b>.html</b> / <b>.htm</b> 𝚏𝚒𝚕𝚎𝚜 𝚜𝚞𝚙𝚙𝚘𝚛𝚝𝚎𝚍."); return
    context.user_data["waiting_for_html"] = False
    await _do_decode(update, context, doc, fname)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""

    if text == "#000000":
        if is_admin(user.id): await _show_admin_panel(update, context)
        else: await update.message.reply_text("❌  𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱.")
        return

    action = context.user_data.get("admin_action")
    if action and is_admin(user.id):
        await _process_admin_input(update, context, action, text); return

    if not bot_active() and not is_admin(user.id):
        await update.message.reply_text("🔴  𝗕𝗼𝘁 𝗶𝘀 𝗼𝗳𝗳𝗹𝚒𝚗𝚎."); return
    if is_banned(user.id): return
    if context.user_data.get("waiting_for_html"):
        await update.message.reply_text("🗂  𝙿𝚕𝚎𝚊𝚜𝚎 𝚜𝚎𝚗𝚍 𝚊 .𝚑𝚝𝚖𝚕 𝚏𝚒𝚕𝚎."); return

    if "𝗜'𝘃𝗲 𝗝𝗼𝗶𝗻𝗲𝗱" in text or "Joined" in text:
        rec = db["users"].setdefault(user.id, {"username":"","name":"","joined":"","banned":False,"private_acked":[]})
        if "private_acked" not in rec: rec["private_acked"] = []
        for ch in db["channels"]:
            if ch.get("type")=="private" and ch["id"] not in rec["private_acked"]: rec["private_acked"].append(ch["id"])
        save_db(db)
        joined, missing = await check_channels(context.bot, user.id)
        if not joined:
            n = len(missing)
            await update.message.reply_html(
                f"⚠️  <b>𝗡𝗼𝘁 𝗬𝗲𝘁!</b>  𝚂𝚝𝚒𝚕𝚕 <b>{n}</b> 𝚌𝚑𝚊𝚗𝚗𝚎𝚕{'𝚜' if n>1 else ''} 𝚙𝚎𝚗𝚍𝚒𝚗𝚐 ↓",
                reply_markup=joined_reply_kb())
            await update.message.reply_text("🗂  𝗣𝗲𝗻𝗱𝗶𝚗𝚐 𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀:", reply_markup=channels_inline_kb(missing))
            return
        if is_banned(user.id): await update.message.reply_html(ban_text(user.id)); return
        await send_welcome(context.bot, user.id, user.first_name); return

    if "𝗛𝗧𝗠𝗟 𝗗𝗲𝗰𝗼𝗱𝗲𝗿" in text or "Decode" in text:
        joined, missing = await check_channels(context.bot, user.id)
        if not joined:
            n = len(missing)
            await update.message.reply_html(
                f"📡  <b>𝗝𝗼𝗶𝗻 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱</b>  ╌  𝙹𝚘𝚒𝚗 <b>{n}</b> 𝚌𝚑𝚊𝚗𝚗𝚎𝚕{'𝚜' if n>1 else ''} 𝚏𝚒𝚛𝚜𝚝 ↓",
                reply_markup=joined_reply_kb())
            await update.message.reply_text("🗂  𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀:", reply_markup=channels_inline_kb(missing)); return
        await _decode_start(update, context)

    elif "𝗗𝗲𝘃𝗲𝗹𝗼𝗽𝗲𝗿" in text or "Developer" in text:
        joined, missing = await check_channels(context.bot, user.id)
        if not joined:
            n = len(missing)
            await update.message.reply_html(
                f"📡  <b>𝗝𝗼𝗶𝗻 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱</b>  ╌  𝙹𝚘𝚒𝚗 <b>{n}</b> 𝚌𝚑𝚊𝚗𝚗𝚎𝚕{'𝚜' if n>1 else ''} 𝚏𝚒𝚛𝚜𝚝 ↓",
                reply_markup=joined_reply_kb())
            await update.message.reply_text("🗂  𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀:", reply_markup=channels_inline_kb(missing)); return
        await _dev_info(update, context)
    # else: ignore silently

# ══════════════════════════════════════════════════════
#   ADMIN CALLBACK ROUTER
# ══════════════════════════════════════════════════════
async def _admin_cb(update, context, data):
    q = update.callback_query
    async def edit(txt, kb=None):
        try: await q.message.edit_text(txt, parse_mode=ParseMode.HTML, reply_markup=kb)
        except: pass

    if data == "admin_back": await edit(_panel_text(), _panel_kb())

    elif data == "admin_toggle_bot":
        db["settings"]["bot_active"] = not bot_active(); save_db(db)
        await q.answer(f"Bot is now {'Online' if bot_active() else 'Offline'}!", show_alert=True)
        await edit(_panel_text(), _panel_kb())

    elif data == "admin_export":
        try:
            with open(DB_FILE,"rb") as f:
                await context.bot.send_document(q.from_user.id, f, filename="database.pkl",
                                                caption="🗄  𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝚎𝚡𝚙𝚘𝚛𝚝𝚎𝚍!")
            await q.answer("✅  Sent!", show_alert=True)
        except Exception as e: await q.answer(f"❌ {e}", show_alert=True)

    elif data == "admin_channels":
        txt = "╭━━━━━━━━━━━━━━━━━━━━╮\n  📡  <b>𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝗟𝗶𝘀𝘁</b>\n╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        for i,ch in enumerate(db["channels"],1):
            icon = "📡" if ch.get("type","public")=="public" else "🔐"
            lbl  = "𝗣𝘂𝗯𝗹𝗶𝗰" if ch.get("type","public")=="public" else "𝗣𝗿𝗶𝘃𝗮𝘁𝗲"
            txt += f"  {i}.  {icon}  <b>{ch.get('name','?')}</b>  ╌  {lbl}\n"
        if not db["channels"]: txt += "  𝙽𝚘 𝚌𝚑𝚊𝚗𝚗𝚎𝚕𝚜 𝚊𝚍𝚍𝚎𝚍 𝚢𝚎𝚝."
        await edit(txt, InlineKeyboardMarkup([
            [InlineKeyboardButton("➕  𝗔𝗱𝗱 𝗣𝘂𝗯𝗹𝗶𝗰",  callback_data="admin_add_public_channel"),
             InlineKeyboardButton("➕  𝗔𝗱𝗱 𝗣𝗿𝗶𝘃𝗮𝘁𝗲", callback_data="admin_add_private_channel")],
            [InlineKeyboardButton("🗑  𝗥𝗲𝗺𝗼𝘃𝗲",      callback_data="admin_remove_channel")],
            [InlineKeyboardButton("🔙  𝗕𝗮𝗰𝗸",         callback_data="admin_back")],
        ]))

    elif data == "admin_add_public_channel":
        context.user_data["admin_action"] = "add_public_channel"
        await edit(
            "📡  <b>𝗔𝗱𝗱 𝗣𝘂𝗯𝗹𝗶𝗰 𝗖𝗵𝗮𝗻𝗻𝗲𝗹</b>\n\n"
            "𝚂𝚎𝚗𝚍 𝚒𝚗 𝚝𝚑𝚒𝚜 𝚏𝚘𝚛𝚖𝚊𝚝:\n\n"
            "<code>CHANNEL_ID | CHANNEL_LINK</code>\n\n"
            "𝙾𝚛 𝚓𝚞𝚜𝚝: <code>@username</code>\n\n"
            "⚠️  𝙱𝚘𝚝 𝚖𝚞𝚜𝚝 𝚋𝚎 𝚊𝚗 <b>𝗔𝗱𝗺𝗶𝗻</b> 𝚘𝚏 𝚝𝚑𝚎 𝚌𝚑𝚊𝚗𝚗𝚎𝚕."
        )

    elif data == "admin_add_private_channel":
        context.user_data["admin_action"] = "add_private_channel"
        await edit(
            "🔐  <b>𝗔𝗱𝗱 𝗣𝗿𝗶𝘃𝗮𝘁𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹</b>\n\n"
            "𝚂𝚎𝚗𝚍 𝚒𝚗 𝚝𝚑𝚒𝚜 𝚏𝚘𝚛𝚖𝚊𝚝:\n\n"
            "<code>CHANNEL_ID | INVITATION_LINK</code>\n\n"
            "𝙴𝚡: <code>-1001234567890 | https://t.me/+aBcD</code>\n\n"
            "📌  𝙻𝚒𝚗𝚔 𝚖𝚞𝚜𝚝 𝚜𝚝𝚊𝚛𝚝 𝚠𝚒𝚝𝚑 <b>https://t.me/+</b>"
        )

    elif data == "admin_remove_channel":
        if not db["channels"]: await q.answer("No channels!", show_alert=True); return
        rows = [[InlineKeyboardButton(
            f"🗑  {'📡' if ch.get('type','public')=='public' else '🔐'}  {ch.get('name','?')}",
            callback_data=f"admin_del_ch_{i}")] for i,ch in enumerate(db["channels"])]
        rows.append([InlineKeyboardButton("🔙  𝗕𝗮𝗰𝗸", callback_data="admin_channels")])
        await edit("🗑  <b>𝗦𝗲𝗹𝗲𝗰𝘁 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝘁𝗼 𝗥𝗲𝗺𝗼𝘃𝗲:</b>", InlineKeyboardMarkup(rows))

    elif data.startswith("admin_del_ch_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(db["channels"]):
            name = db["channels"].pop(idx).get("name","?"); save_db(db)
            await q.answer(f"✅ {name} removed!", show_alert=True)
            await _admin_cb(update, context, "admin_channels")

    elif data == "admin_admins":
        txt = "╭━━━━━━━━━━━━━━━━━━━━╮\n  🛡  <b>𝗔𝗱𝗺𝗶𝗻 𝗟𝗶𝘀𝘁</b>\n╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        for aid in db["admins"]:
            ud = db["users"].get(aid,{}); txt += f"  ◈  {ud.get('name','Unknown')}  ╌  <code>{aid}</code>\n"
        if not db["admins"]: txt += "  𝙽𝚘 𝚊𝚍𝚖𝚒𝚗𝚜 𝚊𝚍𝚍𝚎𝚍."
        await edit(txt, InlineKeyboardMarkup([
            [InlineKeyboardButton("➕  𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻",    callback_data="admin_add_admin"),
             InlineKeyboardButton("🗑  𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_remove_admin")],
            [InlineKeyboardButton("🔙  𝗕𝗮𝗰𝗸",          callback_data="admin_back")],
        ]))

    elif data == "admin_add_admin":
        context.user_data["admin_action"] = "add_admin"
        await edit("🛡  𝚂𝚎𝚗𝚍 𝚝𝚑𝚎 𝚄𝚜𝚎𝚛 𝙸𝙳 𝚘𝚏 𝚝𝚑𝚎 𝚗𝚎𝚠 𝚊𝚍𝚖𝚒𝚗:")

    elif data == "admin_remove_admin":
        if not db["admins"]: await q.answer("No admins!", show_alert=True); return
        rows = [[InlineKeyboardButton(
            f"🗑  {db['users'].get(aid,{}).get('name','Unknown')}  ({aid})",
            callback_data=f"admin_del_adm_{aid}")] for aid in db["admins"]]
        rows.append([InlineKeyboardButton("🔙  𝗕𝗮𝗰𝗸", callback_data="admin_admins")])
        await edit("🗑  <b>𝗦𝗲𝗹𝗲𝗰𝘁 𝗔𝗱𝗺𝗶𝗻 𝘁𝗼 𝗥𝗲𝗺𝗼𝘃𝗲:</b>", InlineKeyboardMarkup(rows))

    elif data.startswith("admin_del_adm_"):
        aid = int(data.split("_")[-1])
        if aid in db["admins"]:
            db["admins"].remove(aid); save_db(db)
            await q.answer("✅ Admin removed!", show_alert=True)
            await _admin_cb(update, context, "admin_admins")

    elif data == "admin_ban":
        context.user_data["admin_action"] = "ban_user"
        await edit("🚷  𝚂𝚎𝚗𝚍 𝚝𝚑𝚎 𝚄𝚜𝚎𝚛 𝙸𝙳 𝚝𝚘 𝚋𝚊𝚗:")

    elif data == "admin_unban":
        context.user_data["admin_action"] = "unban_user"
        await edit("✅  𝚂𝚎𝚗𝚍 𝚝𝚑𝚎 𝚄𝚜𝚎𝚛 𝙸𝙳 𝚝𝚘 𝚞𝚗𝚋𝚊𝚗:")

    elif data == "admin_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await edit(
            "📣  <b>𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁</b>\n\n"
            "𝚃𝚢𝚙𝚎 𝚢𝚘𝚞𝚛 𝚖𝚎𝚜𝚜𝚊𝚐𝚎. 𝚃𝚘 𝚊𝚍𝚍 𝚋𝚞𝚝𝚝𝚘𝚗𝚜:\n\n"
            "<code>Message text\nButton Label|https://link.com</code>"
        )

# ══════════════════════════════════════════════════════
#   ADMIN INPUT PROCESSOR
# ══════════════════════════════════════════════════════
async def _process_admin_input(update, context, action, text):
    context.user_data.pop("admin_action", None)

    if action == "add_public_channel":
        raw = text.strip()
        if raw.startswith("@"):
            try:
                chat = await context.bot.get_chat(raw)
                link = f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id).lstrip('-100')}"
                ch   = {"id":chat.id,"name":chat.title or str(chat.id),"type":"public","link":link,"username":f"@{chat.username}" if chat.username else ""}
                if chat.id in [c["id"] for c in db["channels"]]:
                    await update.message.reply_text("⚠️  𝙲𝚑𝚊𝚗𝚗𝚎𝚕 𝚊𝚕𝚛𝚎𝚊𝚍𝚢 𝚒𝚗 𝚕𝚒𝚜𝚝!")
                else:
                    db["channels"].append(ch); save_db(db)
                    await update.message.reply_html(f"✅  <b>{chat.title}</b> 𝚊𝚍𝚍𝚎𝚍!\n📋  𝗜𝗗  ╌  <code>{chat.id}</code>\n🔗  {link}")
            except: await update.message.reply_html("❌  𝙲𝚑𝚊𝚗𝚗𝚎𝚕 𝚗𝚘𝚝 𝚏𝚘𝚞𝚗𝚍. 𝙼𝚊𝚔𝚎 𝚜𝚞𝚛𝚎 𝚋𝚘𝚝 𝚒𝚜 𝚊𝚗 𝙰𝚍𝚖𝚒𝚗.")
        elif "|" in raw:
            p = [x.strip() for x in raw.split("|",1)]
            try:
                ch_id=int(p[0]); lnk=p[1]
                if not lnk.startswith("https://t.me/"): await update.message.reply_text("❌  𝙸𝚗𝚟𝚊𝚕𝚒𝚍 𝚕𝚒𝚗𝚔 𝚏𝚘𝚛𝚖𝚊𝚝."); return
                name=str(ch_id)
                try:
                    chat=await context.bot.get_chat(ch_id); name=chat.title or name
                except: pass
                if ch_id in [c["id"] for c in db["channels"]]: await update.message.reply_text("⚠️  𝙰𝚕𝚛𝚎𝚊𝚍𝚢 𝚒𝚗 𝚕𝚒𝚜𝚝!")
                else:
                    db["channels"].append({"id":ch_id,"name":name,"type":"public","link":lnk,"username":""}); save_db(db)
                    await update.message.reply_html(f"✅  <b>{name}</b> 𝚊𝚍𝚍𝚎𝚍!\n📋  𝗜𝗗  ╌  <code>{ch_id}</code>\n🔗  {lnk}")
            except ValueError: await update.message.reply_text("❌  𝙸𝚗𝚟𝚊𝚕𝚒𝚍 𝙲𝚑𝚊𝚗𝚗𝚎𝚕 𝙸𝙳.")
        else: await update.message.reply_html("❌  𝚄𝚜𝚎: <code>@username</code>  𝚘𝚛  <code>ID | LINK</code>")

    elif action == "add_private_channel":
        raw = text.strip()
        if "|" not in raw: await update.message.reply_html("❌  𝚄𝚜𝚎: <code>CHANNEL_ID | INVITATION_LINK</code>"); return
        p = [x.strip() for x in raw.split("|",1)]
        try:
            ch_id=int(p[0]); inv=p[1]
            if not (inv.startswith("https://t.me/+") or inv.startswith("https://t.me/joinchat/")):
                await update.message.reply_text("❌  𝙻𝚒𝚗𝚔 𝚖𝚞𝚜𝚝 𝚜𝚝𝚊𝚛𝚝 𝚠𝚒𝚝𝚑 https://t.me/+"); return
            name=str(ch_id)
            try:
                chat=await context.bot.get_chat(ch_id); name=chat.title or name
            except: pass
            if ch_id in [c["id"] for c in db["channels"]]: await update.message.reply_text("⚠️  𝙰𝚕𝚛𝚎𝚊𝚍𝚢 𝚒𝚗 𝚕𝚒𝚜𝚝!")
            else:
                db["channels"].append({"id":ch_id,"name":name,"type":"private","link":inv,"username":""}); save_db(db)
                await update.message.reply_html(f"✅  <b>{name}</b> 𝚊𝚍𝚍𝚎𝚍!\n📋  𝗜𝗗  ╌  <code>{ch_id}</code>\n🔗  {inv}")
        except ValueError: await update.message.reply_text("❌  𝙸𝚗𝚟𝚊𝚕𝚒𝚍 𝙲𝚑𝚊𝚗𝚗𝚎𝚕 𝙸𝙳.")

    elif action == "add_admin":
        try:
            aid=int(text.strip())
            if aid==OWNER_ID: await update.message.reply_text("⚠️  𝙾𝚠𝚗𝚎𝚛 𝚊𝚕𝚛𝚎𝚊𝚍𝚢 𝚑𝚊𝚜 𝚑𝚒𝚐𝚑𝚎𝚜𝚝 𝚊𝚞𝚝𝚑𝚘𝚛𝚒𝚝𝚢!")
            elif aid in db["admins"]: await update.message.reply_text("⚠️  𝙰𝚕𝚛𝚎𝚊𝚍𝚢 𝚊𝚗 𝚊𝚍𝚖𝚒𝚗!")
            else:
                db["admins"].append(aid); save_db(db)
                await update.message.reply_html(f"✅  𝙸𝙳 <code>{aid}</code> 𝚒𝚜 𝚗𝚘𝚠 𝚊𝚗 𝚊𝚍𝚖𝚒𝚗!")
        except ValueError: await update.message.reply_text("❌  𝚂𝚎𝚗𝚍 𝚊 𝚟𝚊𝚕𝚒𝚍 𝚄𝚜𝚎𝚛 𝙸𝙳.")

    elif action == "ban_user":
        try:
            bid=int(text.strip())
            if bid==OWNER_ID: await update.message.reply_text("❌  𝙾𝚠𝚗𝚎𝚛 𝚌𝚊𝚗𝚗𝚘𝚝 𝚋𝚎 𝚋𝚊𝚗𝚗𝚎𝚍!")
            else:
                if bid not in db["users"]: db["users"][bid]={"username":"","name":"Unknown","joined":"","banned":True,"private_acked":[]}
                else: db["users"][bid]["banned"]=True
                save_db(db); await update.message.reply_html(f"✅  𝙸𝙳 <code>{bid}</code> 𝚋𝚊𝚗𝚗𝚎𝚍!")
        except ValueError: await update.message.reply_text("❌  𝚂𝚎𝚗𝚍 𝚊 𝚟𝚊𝚕𝚒𝚍 𝚄𝚜𝚎𝚛 𝙸𝙳.")

    elif action == "unban_user":
        try:
            uid=int(text.strip())
            if uid in db["users"]:
                db["users"][uid]["banned"]=False; save_db(db)
                await update.message.reply_html(f"✅  𝙸𝙳 <code>{uid}</code> 𝚞𝚗𝚋𝚊𝚗𝚗𝚎𝚍!")
            else: await update.message.reply_text("⚠️  𝙸𝙳 𝚗𝚘𝚝 𝚒𝚗 𝚍𝚊𝚝𝚊𝚋𝚊𝚜𝚎.")
        except ValueError: await update.message.reply_text("❌  𝚂𝚎𝚗𝚍 𝚊 𝚟𝚊𝚕𝚒𝚍 𝚄𝚜𝚎𝚛 𝙸𝙳.")

    elif action == "broadcast":
        lines=text.strip().split("\n"); msg_lines=[]; btn_rows=[]
        for line in lines:
            if "|" in line:
                p=line.split("|",1)
                if p[1].strip().startswith("http"): btn_rows.append([InlineKeyboardButton(p[0].strip(), url=p[1].strip())]); continue
            msg_lines.append(line)
        btxt="\n".join(msg_lines).strip(); markup=InlineKeyboardMarkup(btn_rows) if btn_rows else None
        total=len(db["users"]); ok=fail=0
        prog=await update.message.reply_text(f"📣  𝙱𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝𝚒𝚗𝚐...  0/{total}")
        for uid in list(db["users"].keys()):
            try: await context.bot.send_message(uid,btxt,reply_markup=markup); ok+=1
            except: fail+=1
            if (ok+fail)%20==0 or (ok+fail)==total:
                try: await prog.edit_text(f"📣  𝙱𝚛𝚘𝚊𝚍𝚌𝚊𝚜𝚝𝚒𝚗𝚐...\n✅ {ok}  ❌ {fail}  /  {total}")
                except: pass
        try:
            await prog.edit_text(
                "╭━━━━━━━━━━━━━━━━━━━━╮\n  📣  <b>𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲!</b>\n╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"✅  𝚂𝚎𝚗𝚝    ╌  <b>{ok}</b>\n❌  𝙵𝚊𝚒𝚕𝚎𝚍  ╌  <b>{fail}</b>\n👥  𝚃𝚘𝚝𝚊𝚕   ╌  <b>{total}</b>",
                parse_mode=ParseMode.HTML)
        except: pass

# ══════════════════════════════════════════════════════
#   MAIN
# ══════════════════════════════════════════════════════
def main():
    Thread(target=run_flask, daemon=True).start()
    logger.info("Flask keep-alive started.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot polling started.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
