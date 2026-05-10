import asyncio
import json
import os
import io
import re
import time
import random
import logging
import tempfile
import subprocess
import threading
from datetime import datetime

import aiohttp
import requests
import edge_tts
from flask import Flask, jsonify

import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from telegram.constants import ChatType
from telegram.error import RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.request import HTTPXRequest

# ===========================================================
# BOT TOKENS
# ===========================================================
TOKENS = [
    '8566925246:AAG9LPNWtNwVE782zZ4N7Gxvw22OcrZcvEM',
    '8286490366:AAGywCbSvYTUgv8CbyUK8ZlSyX-bKMMozyA',
    '8764205101:AAFjh3SjX4yzJ-5ruYp6UsPbnOajnNTHsJk',
    '8785471426:AAFERaHhpHSvgcutmQHiVQ_pk0PXPv1FZc4',
    '8703025836:AAE36Ig7uK61mTlz5ZQgHelBG8_V5bS3AfI',
    '8772817834:AAHmKc2BR83dtD1zhAxFPgWkC0tQiNTbWlU',
    '7698767175:AAFz3mrJfnKdbrfDuiyPgvAUY5A6TK1zZD8',
    '8615477577:AAEzaNqjLiZ7UFZ6Cz6xWgbqYtwb5_MdD7A',
    '8621740525:AAFTthKQ99SfDRJgpNkkfvWrXC6-N6g_RsY',
    '8656318015:AAHOEWUAHc21mkmmgL7qPmG34PGEJFJDWkg',
    '8754198996:AAEElftCbzwhzF4UVSzyQPn2zUSB65NaPAU',
    '8718139063:AAEDy4upbj7du647kPkeFzQznDCx711x2wk',
    '8408085582:AAEgHKdRr78gHjEGUutA0Ls0DVsS9_G9BiI',
    '8695833406:AAGA_H-CTS3m3yawUZLCqqyq-n-G86MYGJo',
    '8664978086:AAGI4q9yXNpGQoNw8Oqdx9jSqkk8HoMIVWo',
    '8615297803:AAEKsn53k177PipmQwIofjjvPJD8qPQJKWM',
    '8424691219:AAE2kTmyK-h3rth_ZFhKiZttnaV-JlEcqac',
    '8754264848:AAEJgcwqBjjyi4ggIT71tiV54MBtdgdZZBU',
    '8687833724:AAGaqCR7HZNW-ZDKQOfPcl26C329P3cBAXY',
]

if os.path.exists('extra_bots.txt'):
    with open('extra_bots.txt') as _f:
        for _line in _f:
            _t = _line.strip()
            if _t and _t not in TOKENS:
                TOKENS.append(_t)

if not TOKENS:
    raise SystemExit('ERROR: No bot tokens found!')

# ===========================================================
# GEMINI AI CONFIG
# ===========================================================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyAXBsL3eAhht-DLz_EjcvnUcLywfd-jZ3g')
GEMINI_MODEL = 'gemini-2.0-flash'
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
AI_SYSTEM_PROMPT = (
    "You are a smart, friendly and helpful AI assistant running inside a Telegram bot. "
    "You reply in the same language the user speaks (Hindi, English, or mix). "
    "Keep your replies concise and natural. "
    "You can use Telegram-friendly formatting (bold with *, italics with _) but don't overdo it."
)
AI_HISTORY = {}

# ===========================================================
# OWNER & SUDO CONFIG
# ===========================================================
OWNER_ID = int(os.getenv('OWNER_ID', '6327241714'))
SUDO_FILE = "sudo_users.json"

if os.path.exists(SUDO_FILE):
    with open(SUDO_FILE) as f:
        SUDO_USERS = set(json.load(f))
else:
    SUDO_USERS = set()

def save_sudo():
    with open(SUDO_FILE, "w") as f:
        json.dump(list(SUDO_USERS), f)

# ===========================================================
# GLOBAL STATE
# ===========================================================
apps = []
bots = []
nc_tasks = {}
spam_tasks = {}
slider_tasks = {}
photo_tasks = {}
gc_tasks = {}
chat_photos = {}
raid_tasks = {}
delete_tasks = {}
deluser_tasks = {}
auto_delete_users = {}
blocknc_active = {}
warn_counts = {}
warn_limits = {}
reply_tasks = {}
reply_targets = {}
pending_replies_map = {}
GLOBAL_DELAY = 0.05

NON_SUDO_MSG = "Bᴇᴛᴀ Gᴀʟᴀᴛ Jᴀᴡᴀʙ Aʙ Tᴇʀɪ Mᴀ Kɪ Cʜᴜᴅᴀʏɪ Hᴏɢɪ 😁🙌🏻🔥 "
UNAUTHORIZED_MESSAGE = 'Sᴜᴅᴏ Lᴇᴋᴇ Aᴀ Tᴍᴋᴄ तेरी मां रंगबेरंगी 🍂😫'

logging.basicConfig(level=logging.INFO)

# ===========================================================
# PERMISSION HELPERS
# ===========================================================
def is_owner_or_sudo(uid):
    return uid == OWNER_ID or uid in SUDO_USERS

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id == OWNER_ID:
            return await func(update, context)
        await update.message.reply_text("Only srvr owner can use this command!")
    return wrapper

def sudo_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if is_owner_or_sudo(update.effective_user.id):
            return await func(update, context)
        await update.message.reply_text(NON_SUDO_MSG)
    return wrapper

# ===========================================================
# NC PATTERNS — from abbu (file 1)
# ===========================================================
HINDINC_PATTERNS = [
    "{text} चुडाकड़ ⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
    "{text} रैंडी ˖ ࣪ ꉂ🗯˙🫐⃟.꩜‹—",
    "{text} गरीब ⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
    "{text} चमार˖ ࣪ ꉂ🗯˙🫐⃟.꩜‹—",
    "{text} भेंगे⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
    "{text} रैंडी के बच्चे˖ ࣪ ꉂ🗯˙🫐⃟.꩜‹—",
    "{text} गुलाम⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
    "{text} गुलामी कर˖ ࣪ ꉂ🗯˙🫐⃟.꩜‹—",
    "{text} चुदाई केंद्र⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
    "{text} नांगा नाच कर˖ ࣪ ꉂ🗯˙🫐⃟.꩜‹—",
    "{text} पापा बोल 𝑋EN को⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
    "{text} तेरी मां नंगी करू˖ ࣪ ꉂ🗯˙🫐⃟.꩜‹—",
    "{text} छक्के⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
    "{text} भोसड़ी के˖ ࣪ ꉂ🗯˙🫐⃟.꩜‹—",
]

URDU_PATTERNS = [
    "{text} ٹی ایم کے بی࣪ ִֶָ☾.ִ ࣪𖤐࣪ ִֶָ☾.ִ ࣪𖤐",
    "{text} ٹی ایم کے سی𓍢ִႋ🥀͙֒ᰔᩚ",
    "{text} تیری ماں رندی࣪ ִֶָ☾.ִ ࣪𖤐࣪ ִֶָ☾.ִ ࣪𖤐",
    "{text} چوداکڑ 𓍢ִႋ🥀͙֒ᰔᩚ",
    "{text} گلام ࣪ ִֶָ☾.ִ ࣪𖤐࣪ ִֶָ☾.ִ ࣪𖤐",
    "{text} رنڈی𓍢ִႋ🥀֒ᰔᩚ",
    "{text} تیری ماں چھوڑ کر فیک دو ࣪ ִֶָ☾.ִ ࣪𖤐࣪ ִֶָ☾.ִ ࣪𖤐",
    "{text} گلامی کے آر𓍢ִႋ🥀͙֒ᰔᩚ",
    "{text} عجیب کو باپ بول࣪ ִֶָ☾.ִ ࣪𖤐࣪ ִֶָ☾.ִ ࣪𖤐",
    "{text} رنڈی پوترا 𓍢ִႋ🥀͙֒ᰔᩚ",
    "{text} چکے ִ ࣪𖤐࣪ ִֶָ☾.ִ ࣪𖤐࣪ ִֶָ☾.",
    "{text} بی ٹی ایس کے لنڈ 𓍢ִႋ🥀͙֒ᰔᩚ",
]

BENGALI_PATTERNS = [
    "{text} শালা °❀.ೃ࿔*ꫂ❁ 🤪🤍",
    "{text} এলোমেলো ꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} গরিবꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} ককার ꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} প্রজাতিꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} এক এলোমেলোর সন্তানꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} দাসꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} শালা কেন্দ্রꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} নগ্নꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} বাবা, আমাকে বল, আমি ꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} তোর মাকে বিবস্ত্র করব।ꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} সিক্সার্সꫂ❁°❀.ೃ࿔*🤪🤍",
    "{text} তুই হারামজাদাꫂ❁°❀.ೃ࿔*🤪🤍",
]

BIHARI_PATTERNS = [
    "{text} भोसड़ी के बा⋆꙳^̩̩͙❅*̩̩͙‧͙ ‧͙*̩̩͙❆ ͙͛ ˚₊⋆",
    "{text} सतमेरवनी₊˚ʚ ᗢ₊˚✧ ﾟ.",
    "{text} गरीब⋆꙳^̩̩͙❅*̩̩͙‧͙ ‧͙*̩̩͙❆ ͙͛ ˚₊⋆",
    "{text} कॉकर के ह₊˚ʚ ᗢ₊˚✧ ﾟ.",
    "{text} नसल⋆꙳^̩̩͙❅*̩̩͙‧͙ ‧͙*̩̩͙❆ ͙͛ ˚₊⋆",
    "{text} एगो बेतरतीब के लइका₊˚ʚ ᗢ₊˚✧ ﾟ.",
    "{text} गुलाम⋆꙳^̩̩͙❅*̩̩͙‧͙ ‧͙*̩̩͙❆ ͙͛ ˚₊⋆",
    "{text} कमबख्त सेंटर के बा₊˚ʚ ᗢ₊˚✧ ﾟ.",
    "{text} नंगा हो गइल बा⋆꙳^̩̩͙❅*̩̩͙‧͙ ‧͙*̩̩͙❆ ͙͛ ˚₊⋆",
    "{text} पापा बताव हम तोहार माई के {text} उतार देब।₊˚ʚ ᗢ₊˚✧ ﾟ.",
    "{text} छक्का के लोग⋆꙳^̩̩͙❅*̩̩͙‧͙ ‧͙*̩̩͙❆ ͙͛ ˚₊⋆",
    "{text} रे हरामी₊˚ʚ ᗢ₊˚✧ ﾟ.",
]

ENGLISH_PATTERNS = [
    "{text} 🅱🅻🅾🅾🅳🆈 🅷🅴🅻🅻.𖥔 ݁ ˖ִ🛸༄˖°.",
    "{text} 🅼🅾🆃🅷🅴🆁🅵🆄🅲🅺🅴🆁🌊⋆｡ 𖦹°.🐚⋆❀˖°🫧",
    "{text} 🅱🅸🆃🅲🅷 🆂🅾🅽.𖥔 ݁ ˖ִ🛸༄˖°.",
    "{text} 🆂🅻🅰🆅🅴🌊⋆｡ 𖦹°.🐚⋆❀˖°🫧",
    "{text} 🆂🅾🅽 🅾🅵 🅼🅸🅰 🅺🅷🅰🅻🅸🅵🅰 .𖥔 ݁ ˖ִ🛸༄˖°.",
    "{text} 🆂🅰🆈 🅵🆁🅴🅰🅺🆈 🅳🅰🅳🅳🆈🌊⋆｡ 𖦹°.🐚⋆❀˖°🫧",
    "{text} 🅵🆄🅲🅺🄽🄶 🅲🅴🅽🆃🆁🅴.𖥔 ݁ ˖ִ🛸༄˖°.",
    "{text} 🆂🅾🅽 🅵🆄🅲🅺🅴🅳 🅼🅾🅼🌊⋆｡ 𖦹°.🐚⋆❀˖°🫧",
]

EMOJI_NC_EMOJIS = ["🚀","♨️","👑","♻️","🚨","🎪","🎃","🎄","🧨","✨","🎈","🎉","🎯","🎀","🎁","🎗️","🎟️","🏆","🧧","⚽","🔱","⚜️","⚛️","🕉️","✡️","☸️","☯️","✝️","☦️","☪️","☮️","🕎","🔯","♈","♉","❗","❕","‼️","⁉️","❕","〽️","🔰","⭕","📛","♻️","⚰️","🪓","💠"]
EMOJI_NC_PATTERN = "'ठीक है अलविदा मैं जल्द ही {text} की माँ का भोसड़ा चोदने आऊँगा <⋆.ೃ࿔*:･{emoji}⋆.ೃ࿔*:･>"

NC1_EMOJIS = ["👹᭄","👺᭄","😈᭄","💀᭄","☠️᭄","🔱᭄","🩸᭄","🕷᭄","🕸᭄","🦇᭄","🌑᭄","🖤᭄","🔮᭄","⚰️᭄","🪦᭄","🗡️᭄","⚔️᭄","🔥᭄","💥᭄","😱᭄","🤬᭄","👻᭄","🎃᭄","🦴᭄","💣᭄","🧿᭄","🌚᭄","🕯️᭄","🪄᭄","🧙","🧛᭄"]
NC1_PATTERN = "˚⊱{emoji}⊰˚{text} ᥴᥙᦔꪖɪ ᴋʜꪖꪀꪖ 😫👌🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀✨🎀 <˚⊱⊰˚{emoji}˚⊱⊰˚>"

NC2_EMOJIS = ["🌋","🔥","💥","🫨","♨️","🟠","🟡","🔴","☄️","⚡","💢","😤","🥵","🧱","🪨","💣","🧨","🌪️","🌡️","🦴","🐉","🔶","🔸","🔺","🔻","🌊","💨","🌫️","🏔️","⛰️","🗻","🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘","🪐","💫","✨","🌠","🎇","🎆","🔮","🫀","🧠","👁️","🦷","🦴","🐊","🦎"]
NC2_PATTERN = "{text} ♡Ᏼᴀᴛᴍᴀɴ يخاف -/-  ꪖʙʙꪊ ᴏᴘ ʙᴏʟ Nyto ⌯⌲ कुत्तिया ᴄᴜᴅᴀɪ ᴋʜᴀ╰┈➤ 🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥✅🔥✅🔥✅🔥✅🔥✅🔥✅🔥🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍🔥🤍 <{emoji}>"

NC3_EMOJIS = ["🌋","🔥","💥","🫨","♨️","🟠","🟡","🔴","☄️","⚡","💢","😤","🥵","🧱","🪨","💣","🧨","🌪️","🌡️","🦴","🐉","🔶","🔸","🔺","🔻","🌊","💨","🌫️","🏔️","⛰️","🗻","🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘","🪐","💫","✨","🌠","🎇","🎆","🔮","🫀","🧠","👁️","🦷","🦴","🐊","🦎"]
NC3_PATTERN = "{text} I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ --->🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃🧃💢🧃💢🧃💢🧃💢🧃💢🧃🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃💢🧃 <{emoji}>"

NC4_EMOJIS = ["🏔️","🌋","☃️","🏝️","🏖️","🌊","🌬️","❄️","🌀","🌪️","⚡","☔","💧","☁️","🌨️","🌧️","🌩️","⛈️","🌦️","🌥️","⛅","🌤️","☀️","🌞","🌝","🌚","🌜","🌛","🌙","⭐","🌟","✨","🪐","🌍","🌠","🌌","☄️","🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
NC4_PATTERN = "{text} ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/-  <{emoji}>"

NC5_EMOJIS = ["🧙","🧙\u200d♂️","🧙\u200d♀️","🪄","✨","🌟","⭐","💫","☄️","🌠","🔮","🎩","🐉","🐲","🦄","🧚","🧚\u200d♂️","🧚\u200d♀️","🧜","🧜\u200d♂️","🧜\u200d♀️","🧞","🧞\u200d♂️","🧞\u200d♀️","🧝","🧝\u200d♂️","🧝\u200d♀️","🗡️","🛡️","⚔️","🏹","🪓","🔱","⚜️","🎭","🎪"]
NC5_PATTERN = "🩷 {text} ♡Ᏼᴀᴛᴍᴀɴيخاف -/-  ꪖʙʙꪊ ᴏᴘ ʙᴏʟ Nyto aaj try maa confirm chudegi 🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕 {emoji} "

KNC_EMOJIS = ["👶","👧","🧒","👦","👩","🧑","👨","👩‍🦱","🧑‍🦱","👨‍🦱","👩‍🦰","🧑‍🦰","👨‍🦰","👱‍♀️","👱","👱‍♂️","👩‍🦳","🧑‍🦳","👨‍🦳","👩‍🦲","🧑‍🦲","👨‍🦲","🧔‍♀️","🧔","🧔‍♂️","👵","🧓","👴","👲","👳‍♀️","👳","👳‍♂️","🧕","👮‍♀️","👮","👮‍♂️","👷‍♀️","👷","👷‍♂️","💂‍♀️","💂","💂‍♂️"]
KNC_PATTERN = "{text} <{emoji}>⌯⌲ कुत्तिया ᴄᴜᴅᴀɪ ᴋʜᴀ╰┈➤🌀💦🌀💦🌀💦🌀💦🌀💦🌀💦🌀💦🌀💦🌀💦🌀💦🌀💦🌀💦🌀🌀💦🌀💦🌀💦🌀💦🌀💦💦🌀💦🌀💦🌀💦🌀💦🌀"

ANC_EMOJIS = ["🌈","☔","⚡","🌪️","🌀","🏖️","🏝️","🌊","🌬️","❄️","💧","🌨️","☁️"]
ANC_PATTERN = "{text} _✍🏻 𝐘ᴇ 𝐃ᴇᴋʜ ˢᶜʳⁱᵖᵗ ˡⁱᵏʰ ʳᵃʰᵃ ʰᵘ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐁ʜᴏsᴅᴇ 𝐌ᴇɪɴ <{emoji}> 🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕🍂🐕"

FNC_EMOJIS = ["❤️","🧡","💛","💚","🩵","💙","💜","🤎","🖤","🩶","🤍","🩷"]
FNC_PATTERN = "{text} रंगबेरंगी रण्डी तेरी 𝘾𝙃𝙐𝘿𝘼𝙄 𝘼𝙍𝘾 <{emoji}> જ⁀➴❤️‍🔥જ⁀➴🎀જ⁀➴🤍જ⁀➴💓જ⁀➴❣️જ⁀➴🩵જ⁀➴💚જ⁀➴❤️"

# ===========================================================
# SLIDE MESSAGES — from abbu
# ===========================================================
SLIDE1_MESSAGES = [
    "𝐓ᴍᴋʙ 𝐑ɴᴅʏ ᴋᴇ 𝐋ᴀᴅᴋᴇ 😈🖕🏻😈🖕🏻😈",
    "𝐓ᴇʀɪ ᴍᴀᴀ ᴍᴀʀ ɢʏɪ ¿😆😆😆",
    "𝐀ᴀʀ ꜱᴀᴍᴀɴᴅᴀʀ ᴘᴀᴀʀ ꜱᴀᴍᴀɴᴅᴀʀ ʙᴇᴇᴄʜ ᴍɪᴇ ʜᴀɪ ɴᴀɪʏᴀ ᴘʜʟᴇ ᴛᴇʀɪ ʙʜᴇɴ चोदू ʙᴀᴀᴅ ᴍɪᴇ चोदू ᴍᴀɪʏᴀ ¡! 🥰🖕🏻🥰🖕🏻🥰🖕🏻",
    "𝐓ᴇʀɪ 𝐌ᴀᴀ ʜᴜᴍᴇꜱʜᴀ ᴍᴜᴊʜꜱᴇ ʜɪ ᴋʏᴜ चुडती है ¡! 😡🤬😡🤬😡",
    "𝐃ᴇᴋʜ ᴀᴀᴊ ᴛᴇʀɪ 𝐌ᴀᴀ ᴋᴀ ɴᴀɴɢᴀ ᴅᴀɴᴄᴇ ᴅɪᴋʜᴀᴜ ! 🩰🧑🏻‍🩰",
]

SLIDE2_MESSAGES = [
    "𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ɪ 𝐆ᴜʟᴀʙɪ 𝐂ʜᴜᴛ ᴍɪᴇ 𝐌ᴜᴛ ᴋʀ ʙʜᴀɢ ᴊᴀᴜɢᴀ 𝐁ꜱᴅᴋ ! 😆",
    "𝐓ᴇʀɪ 𝐌ᴀᴀ ᴄʜᴏᴅɴᴇ ᴀʀʜᴀ ʜᴜ ʀᴜᴋ ᴡʜɪ ɢᴜʟᴀᴍ ! 😾",
    "𝐓ᴇʀɪ ʙʜᴇɴ ᴋᴇ ʙᴏᴏʙɪᴇꜱ ᴋᴇ ʙᴇᴇᴄʜ ᴍɪᴇ ʟɴᴅ ꜰᴀꜱᴀ ᴋʀ ᴍᴜᴛʜ ᴍᴀᴀʀ ᴅᴜɢᴀ ʙꜱᴅᴋ 😆",
    "𝐓ᴇʀɪ ᴍᴀᴀ ᴋɪ ᴄʜᴜᴛ ᴍɪᴇ ᴍᴀɢɢɪᴇ ʙɴᴀ ᴋʀ ᴍᴜᴛʜ ʙʜᴀʀ ᴅᴜɢᴀ ! 😆",
    "𝐓ᴇʀɪ ᴍᴀᴀ ʙʜᴛ ʀᴏᴛɪ ᴇʏ ʙɪʟᴋᴜʟ 𝐓ᴇʀɪ ᴛʀʜ ᴅᴏɴᴏ ʀɴᴅʏ ʀᴏɴᴀ ᴋʀᴛᴇ ʜᴏ ᴇᴡᴡ ! 😆",
    "𝐓ᴇʀɪ ʙʜᴇɴ ᴋɪ ɢᴜʟᴀʙɪ ᴄʜᴛ ᴋᴀᴀᴛ ᴅᴜɢᴀ ɢᴜʟᴀᴍ ! 😆",
    "𝐂ʜʟ ɢᴜʟᴀᴍ ɢᴜʟᴀᴍɪ ᴋʀ ! 😾",
]

SLIDE3_PATTERN = "{text} Bᴇᴛᴀ Gᴀʟᴀᴛ Jᴀᴡᴀʙ Aʙ Tᴇʀɪ Mᴀ Kɪ Cʜᴜᴅᴀʏɪ Hᴏɢɪ 😁🙌🏻🔥"

# ===========================================================
# SPAM PATTERNS — from abbu
# ===========================================================
SPAM1_PATTERN = "🎐𓍼ֶ˖ܓ  ( < {text} > )  की अम्मी-जान का रेपिस्ट बाप हू ˚.🥀>"
SPAM2_SINGLE_PATTERN = "{text} - 𝐑ᴀɴᴅᴏ𝐌 𝐒ᴀʟ𝐄 𝐂ʜᴜᴅᴛ𝐀 𝐑ᴇ𝐇 𝐓ᴜ 🚸🤍🙇🏻𓍼ִֶָ𓂃 ࣪˖ ִֶָ"
SPAM2_PATTERN = (SPAM2_SINGLE_PATTERN + "\n") * 10
SPAM3_SINGLE_PATTERN = "--->>🤍➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳➳{text} 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 🍂😫"
SPAM3_PATTERN = (SPAM3_SINGLE_PATTERN + "\n") * 10
SPAM4_SINGLE_PATTERN = "𓆩{text}𓆪 𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🪄"
SPAM4_PATTERN = (SPAM4_SINGLE_PATTERN + "\n\n") * 10

# ===========================================================
# EXTRA DATA FROM GAWD (file 2)
# ===========================================================
NC_heart_MESSAGES = [
    'रंगबेरंगी रण्डी ❤️🧡💛💚',
    'रंगबेरंगी रण्डी 🧡💛💚🩵',
    'रंगबेरंगी रण्डी 💛💚🩵💙',
    'रंगबेरंगी रण्डी 💚🩵💙💜',
    'रंगबेरंगी रण्डी 🩵💙💜🤎',
    'रंगबेरंगी रण्डी 💙💜🤎🖤',
    'रंगबेरंगी रण्डी 💜🤎🖤🩶',
    'रंगबेरंगी रण्डी 🤎🖤🩶🤍',
    'रंगबेरंगी रण्डी 🖤🩶🤍🩷',
    'रंगबेरंगी रण्डी 🩶🤍🩷❤️‍🩹',
    'रंगबेरंगी रण्डी 🤍🩷❤️‍🩹💔',
    'रंगबेरंगी रण्डी 🩷❤️‍🩹💔❤️‍🔥',
]

NC_FLAG_MESSAGES = [
    '{target} I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ ✩‧⁀➷्र 🍓🎀\U0001fa75💋🇰🇪𓍼ֶָ֢',
    '{target} I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ ✩‧⁀➷्र 🍓🎀\U0001fa75💋🇱🇨𓍼ֶָ֢',
    '{target} I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ ✩‧⁀➷्रˑ 🍓🎀\U0001fa75💋🇦🇫𓍼ֶָ֢',
    '{target} I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ ✩‧⁀➷्रˑ 🍓🎀\U0001fa75💋🇧🇧𓍼ֶָ֢',
    '{target} I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ ✩‧⁀➷्रˑ 🍓🎀\U0001fa75💋🇪🇺𓍼ֶָ֢',
    '{target} I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ ✩‧⁀➷्रˑ 🍓🎀\U0001fa75💋🇦🇺𓍼ֶָ֢',
]

TIME_NC_MESSAGES = [
    '𓂃˖˳·˖ ִֶָ ⋆❤️͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚❤️ ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆🧡͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚🧡 ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆💛͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚💛 ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆💚͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚💚 ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆💙͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚💙 ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆💜͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚💜 ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆🖤͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚🖤 ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆🤍͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚🤍 ݁˖⭑.',
    '𓂃˖˳·˖ ִֶָ ⋆🤎͙⋆ ִֶָ˖·˳˖𓂃 ִֶָ⁀➴༯ sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ⋆˚🤎 ݁˖⭑.',
]

NC_WEB_MESSAGES = [
    '{target} 𝑇𝑀𝐾𝐿℘✩₊˚.⋆🕸️🐇',
    '{target} 𝑇𝐵𝐾𝐿℘✩₊˚.⋆🕸️🐇',
    '{target} 𝐺𝐴𝑌℘✩₊˚.⋆🕸️🐇',
    '{target} 𝐶𝐻𝑈𝐷℘✩₊˚.⋆🕸️🐇',
    '{target} 𝐶𝐻𝐴𝑃𝑅𝐼℘✩₊˚.⋆🕸️🐇',
]

DOTZKENG_MESSAGES = [
    "{target}🤍 ⭅╡𝗧𝗠𝗞𝗖╞⭆🧡",
    "{target}🤍⭅╡माधरचोद╞⭆❤️",
    "{target}🤍⭅╡माधरचोद╞⭆💙",
    "{target}🤍⭅╡माधरचोद╞⭆🩵",
    "{target}🤍⭅╡माधरचोद╞⭆💚",
    "{target}🤍⭅╡माधरचोद╞⭆💛",
    "{target}🤍⭅╡माधरचोद╞⭆❤️‍🩹",
    "{target}🤍⭅╡माधरचोद╞⭆💔",
    "{target}🤍⭅╡माधरचोद╞⭆❤️‍🔥",
    "{target}🤍⭅╡माधरचोद╞⭆🩷",
    "{target}🤍⭅╡माधरचोद╞⭆🩶",
    "{target}🤍⭅╡माधरचोद╞⭆🖤",
    "{target}🤍⭅╡माधरचोद╞⭆🤎",
    "{target}🤍⭅╡माधरचोद╞⭆💜",
]

FLOWER_NC_MESSAGES = [
    '⋆₊🍁˚{target} Sʟᴜᴛ Mᴀ ᴋ Lᴅᴋᴇy ',
    '⋆₊🌱˚{target} Sʟᴜᴛ Mᴀ ᴋ Lᴅᴋᴇy ',
    '⋆₊🌿˚{target} Sʟᴜᴛ Mᴀ ᴋ Lᴅᴋᴇy ',
    '⋆₊🍃˚{target} Sʟᴜᴛ Mᴀ ᴋ Lᴅᴋᴇy ',
    '⋆₊☘️˚{target} Sʟᴜᴛ Mᴀ ᴋ Lᴅᴋᴇy ',
    '⋆₊🍀˚{target} Sʟᴜᴛ Mᴀ ᴋ Lᴅᴋᴇy ',
]

NAME_CHANGE_MESSAGES = [
    '{target} 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 ➥\U0001fa76₊𓍼ֶָ֢',
    '{target} 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 ➥\U0001fa75₊𓍼ֶָ֢',
    '{target} 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 ➥\U0001fa77₊𓍼ֶָ֢',
    '{target} 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 ➥🤍₊𓍼ֶָ֢',
    '{target} 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 ➥🖤₊𓍼ֶָ֢',
    '{target} 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 ➥💜₊𓍼ֶָ֢',
]

REPLY_MESSAGES = [
    '{target} - 𝐌ᴜᴊᴇʏ 𝐊ʏᴀ 𝐌ᴇʏ 𝐓ᴏ 𝐓ʀɪ 𝐌ᴀ चोदूंगा ➥🦁🥀',
    '{target} - 𝐁ʜᴀɢᴀ 𝐓ᴏ 𝐓ᴇʀʏ 𝐌ᴀᴀ 𝐊ɪʏ 𝐋ᴀꜱʜ 𝐂ʜᴜᴅ जाएगी ➥🌸🐮🦓',
    '{target} - 𝐊ᴏ 𝐏ᴇʟᴛᴇʏ 𝐇ᴜᴇ 𝐁ᴀᴛᴍᴀɴ 𝐏ᴀᴩᴀ 𝐊ɪ 𝐄ɴᴛʀʏ ➥🧦🚸',
    '{target} - 𝐓ᴇʀʏ 𝐌ᴀᴀ 𝐊ɪ 𝐂ʜᴜᴛ 𝐌ᴇʏ 𝐋ᴀᴜᴅᴀ ➥🤣🙏🏿🥀',
]

SPAM_MESSAGE_TEMPLATE = '{target}✩‧⁀➷🩷✧.* 𝐑ᴀɴᴅᴏ𝐌 𝐒ᴀʟ𝐄 𝐂ʜᴜᴅᴛ𝐀 𝐑ᴇ𝐇 𝐓ᴜ ✩‧⁀➷🩷✧.* 🩵💙💜🤎'
SPAM_MESSAGE_2 = '{target} 🤢\U0001fabd 𝐀ᴊ 𝐊ʜᴀᴋᴇ 𝐁ᴜʀɢᴇʀ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐂ᴜᴅᴇɢɪ 𝐆ʜᴀʀ 𝐆ʜᴀʀ 🤪🤘🏿🔥'
SPAM_MESSAGE_3 = '{target} ᴛᴇʀɪ ᴍᴀᴀ ᴋɪ ᴄ ʜ ᴜ ᴛ ᴋᴀ ᴘᴀᴀɴɪ ɴɪᴋᴀʟᴜ ʀᴀɴᴅɪ ᴋᴇ ¿🛸🌎°🌓•🚀✯★'
RAID_TEXTS = [
    '✩‧⁀➷🩷✧.* 𝐑ᴀɴᴅᴏ𝐌 𝐒ᴀʟ𝐄 𝐂ʜᴜᴅᴛ𝐀 𝐑ᴇ𝐇 𝐓ᴜ ✩‧⁀➷🩷✧.*',
    '✩‧⁀➷🩵✧.* 𝐓ᴇʀ𝐈 𝐁ᴇʜᴇ𝐍 𝐑ᴀɴᴅ𝐈 𝐁ᴇᴛ𝐀 ✩‧⁀➷🩵✧.*',
    '✩‧⁀➷🩶✧.* 𝐓ᴇʀ𝐈 𝐌ᴀ𝐀 𝐊ɪ 𝐂ʜᴜ𝐓 𝐏ɪʟʟ𝐄 ✩‧⁀➷🩶✧.*',
    '✩‧⁀➷🤍✧.* 𝐁ʜᴀɢɴ𝐀 𝐍ᴀʜ𝐈 𝐁ᴇᴛ𝐀 ✩‧⁀➷🤍✧.*',
    '✩‧⁀➷❤️✧.* 𝐀ᴜᴋᴀ𝐓 𝐁ʜᴜ𝐋 𝐆ᴀʏ𝐀 𝐊ʏ𝐀 𝐑ɴᴅʏ𝐊 ✩‧⁀➷❤️✧.*',
    '✩‧⁀➷🧡✧.* 𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 ✩‧⁀➷🧡✧.*',
    '✩‧⁀➷💙✧.* I ᴄʀᴀᴠᴇ Fᴏʀ Yᴏᴜʀ Mᴏᴍs Pᴜssʏ ✩‧⁀➷💙✧.*',
    '✩‧⁀➷❤️‍🔥✧.* 𝐓ᴇʀ𝐈 𝐁ᴇʜᴇ𝐍 𝐊ᴀʟ𝐈 𝐂ʜᴜ𝐓 𝐊ɪ 𝐃ᴇᴠ𝐈 ✩‧⁀➷❤️‍🔥✧.*',
    '✩‧⁀➷💚✧.* 𝐓ᴇʀ𝐈 𝐃ᴀᴅ𝐈 𝐑ᴀɴᴅ𝐈 ✩‧⁀➷💚✧.*',
    '✩‧⁀➷🤎✧.* 𝐓ᴇʀ𝐈 𝐁ᴜ𝐀 𝐏ᴇ𝐋 𝐃ɪ𝐀 𝐁ᴇᴛ𝐀 ✩‧⁀➷🤎✧.*',
    'Bᴇᴛᴀ Gᴀʟᴀᴛ Jᴀᴡᴀʙ Aʙ Tᴇʀɪ Mᴀ Kɪ Cʜᴜᴅᴀʏɪ Hᴏɢɪ 😁🙌🏻🔥',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा',
    '𝐓ᴇʀ𝐈 𝐌ᴀ𝐀 𝐑ᴀɴᴅ𝐈 \U0001fa75\U0001fa77\U0001fa76',
]

ANIME_CHARACTERS = {
    1: ('Gojo Satoru','🔵','en-US-DavisNeural','+20%','+8Hz','Throughout Heaven and Earth, I alone am the honored one.'),
    2: ('Naruto','🍥','en-US-RyanNeural','+35%','+10Hz',"Believe it! I'm gonna be Hokage someday!"),
    3: ('Itachi','🌙','en-US-AndrewNeural','-25%','-6Hz',"You don't have enough hatred."),
    4: ('Luffy','⚓','en-US-TonyNeural','+40%','+12Hz',"I'm gonna be King of the Pirates!"),
    5: ('Zoro','⚔️','en-GB-RyanNeural','-10%','-8Hz','Nothing happened.'),
    6: ('Kakashi','📚','en-AU-WilliamNeural','-5%','0Hz','In this world, those who break the rules are scum.'),
    7: ('Vegeta','👑','en-US-GuyNeural','+5%','-4Hz','I am the Prince of all Saiyans! You are nothing!'),
    8: ('Light Yagami','📓','en-GB-ThomasNeural','-15%','+2Hz','I am Justice.'),
    9: ('Levi','🗡️','en-US-AndrewNeural','-30%','-10Hz','Give up on your dreams and die.'),
    10: ('Sasuke','🔴','en-US-DavisNeural','-35%','-8Hz','I have long since closed my eyes.'),
}

REACT_EMOJIS_ALL = ['👍','👎','❤','🔥','🥰','👏','😁','🤔','🤯','😱','🤬','😢','🎉','🤩','🤮','💩','🙏','👌','🕊','🤡','🥱','🥴','😍','🐳','❤\u200d🔥','🌚','🌭','💯','🤣','⚡','🍌','🏆','💔','🤨','😐','🍓','🍾','💋','🖕','😈','😴','😭','🤓','👻','👨\u200d💻','👀','🎃','🙈','😇','😨','🤝','✍','🤗','🫡','🎅','🎄','☃','💅','🤪','🗿','🆒','💘','🙉','🦄','😘','💊','🙊','😎','👾','🤙']
BOT_SELF_REACT_EMOJIS = ['🔥','⚡','🏆','😈','🎉','💯','🌚','🤩','👌','💋']

HEART_EMOJIS = [
    'Batman  么 𝐁ᴀᴘ 𝐁ᴏʟ → 🧍🏻','Batman  么 𝐁ᴀᴘ 𝐁ᴏʟ →🤸🏻',
    'Batman  么 𝐁ᴀᴘ 𝐁ᴏʟ →🧎🏻','Batman  么 𝐁ᴀᴘ 𝐁ᴏʟ →🏃🏻',
    'Batman  么 𝐁ᴀᴘ 𝐁ᴏʟ →🚶🏻','Batman  么 𝐁ᴀᴘ 𝐁ᴏʟ →🏊🏻',
]

WHITE_EMOJIS = [
    '𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 🤍','𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 👻',
    '𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 👀','𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 💀',
    '𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 🥼','𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ ⚪',
    '𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ ☃️','𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 🦢',
    '𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 🥼','𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ ⚪',
    '𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ ☃️','𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 🦢',
    '𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ ⬜','𝑳𝒖𝒏𝒅 𝑪𝒉𝒖𝒔 -/- ¿ 🐑',
]

BLACK_EMOJIS = [
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा👱🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा🤙🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा🤦🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा🙅🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा🙆🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा👸🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा👦🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा🤰🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा🏃🏿',
    'ठीक है अलविदा मैं जल्द ही तुम्हारी माँ का भोसड़ा चोदने आऊँगा🚶🏿',
]

FLAG_EMOJIS = [
    'ོ༘₊⁺🇮🇳 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐈ɴᴅɪᴀ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇮🇳 ₊⁺⋆.˚',
    'ོ༘₊⁺🇯🇵 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐉ᴀᴘᴀɴ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇯🇵 ₊⁺⋆.˚',
    'ོ༘₊⁺🇺🇸 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐔𝐒𝐀 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇺🇸 ₊⁺⋆.˚',
    'ོ༘₊⁺🇬🇧 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐔𝐊 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇬🇧 ₊⁺⋆.˚',
    'ོ༘₊⁺🇰🇷 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐊ᴏʀᴇᴀ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇰🇷 ₊⁺⋆.˚',
    'ོ༘₊⁺🇩🇪 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐆ᴇʀᴍᴀɴʏ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇩🇪 ₊⁺⋆.˚',
    'ོ༘₊⁺🇫🇷 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐅ʀᴀɴᴄᴇ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇫🇷 ₊⁺⋆.˚',
    'ོ༘₊⁺🇮🇹 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐈ᴛᴀʟʏ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇮🇹 ₊⁺⋆.˚',
    'ོ༘₊⁺🇧🇷 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐁ʀᴀᴢɪʟ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇧🇷 ₊⁺⋆.˚',
    'ོ༘₊⁺🇨🇦 ₊⁺⋆.˚ 𝐓ᴇʀɪ 𝐌ᴀᴀ 𝐊ᴇ 𝐒ᴀᴛʜ 𝐘ᴏʀɪᴄʜɪ 𝐁ᴀᴀᴘ 𝐀ᴜʀ 𝐂ᴀɴᴀᴅᴀ 𝐖ᴀʟᴇ 𝐁ʜɪ 𝐂ʜɪʟʟ 𝐊ᴀʀ 𝐑ʜᴇ ོ༘₊⁺🇨🇦 ₊⁺⋆.˚',
]

WIZARD_EMOJIS = [
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🧙','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🧙\u200d♂️',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🧙\u200d♀️','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🪄',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- ✨','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🌟',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- ⭐','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 💫',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- ☄️','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🌠',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🔮','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🎩',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🐉','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🦄',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🧚','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🗡️',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- ⚔️','𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🔱',
    '𝗧ᴍᴋ𝗕 pe ♡Ᏼᴀᴛᴍᴀɴيخاف -/- 🎭',
]

FIRE_EMOJIS = [
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🔥","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🌋",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 💥","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 ⚡",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 ☄️","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🌪️",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🌶️","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 ♨️",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🧨","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 💣",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 ⚔️","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 💢",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 ❤️\u200d🔥","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🥵",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 😤","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 👹",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 👺","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🔴",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🟠","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🐉",
    "𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🦁","𝐀ʙᴇ𝐘 𝐔ɴᴋɴᴏᴡ𝐍 𝐓ᴀᴛᴛ𝐄 🐯",
]

WATER_EMOJIS = [
    "⊱🩵⊰{text}⊱🩵⊰💧","⊱🩵⊰{text}⊱🩵⊰🌊","⊱🩵⊰{text}⊱🩵⊰🐋",
    "⊱🩵⊰{text}⊱🩵⊰🐬","⊱🩵⊰{text}⊱🩵⊰🐟","⊱🩵⊰{text}⊱🩵⊰🦈",
    "⊱🩵⊰{text}⊱🩵⊰🐙","⊱🩵⊰{text}⊱🩵⊰🦑","⊱🩵⊰{text}⊱🩵⊰🌸",
    "⊱🩵⊰{text}⊱🩵⊰💦","⊱🩵⊰{text}⊱🩵⊰🫧","⊱🩵⊰{text}⊱🩵⊰🌀",
    "⊱🩵⊰{text}⊱🩵⊰⛵","⊱🩵⊰{text}⊱🩵⊰🏊","⊱🩵⊰{text}⊱🩵⊰🌧️",
    "⊱🩵⊰{text}⊱🩵⊰☔","⊱🩵⊰{text}⊱🩵⊰🏄","⊱🩵⊰{text}⊱🩵⊰🧊",
    "⊱🩵⊰{text}⊱🩵⊰❄️","⊱🩵⊰{text}⊱🩵⊰🌈","⊱🩵⊰{text}⊱🩵⊰💙",
    "⊱🩵⊰{text}⊱🩵⊰🩵","⊱🩵⊰{text}⊱🩵⊰🔵","⊱🩵⊰{text}⊱🩵⊰🟦",
]

LAVA_EMOJIS = [
    "𝑇𝑀𝐾𝐵℘✩  🌋","𝑇𝑀𝐾𝐵℘✩  🔥","𝑇𝑀𝐾𝐵℘✩  💥",
    "𝑇𝑀𝐾𝐵℘✩  🫨","𝑇𝑀𝐾𝐵℘✩  ♨️","𝑇𝑀𝐾𝐵℘✩  🟠",
    "𝑇𝑀𝐾𝐵℘✩  🟡","𝑇𝑀𝐾𝐵℘✩  🔴","𝑇𝑀𝐾𝐵℘✩  ☄️",
    "𝑇𝑀𝐾𝐵℘✩  ⚡","𝑇𝑀𝐾𝐵℘✩  💢","𝑇𝑀𝐾𝐵℘✩  😤",
    "𝑇𝑀𝐾𝐵℘✩  🥵","𝑇𝑀𝐾𝐵℘✩  🧱","𝑇𝑀𝐾𝐵℘✩  🪨",
    "𝑇𝑀𝐾𝐵℘✩  💣","𝑇𝑀𝐾𝐵℘✩  🐉","𝑇𝑀𝐾𝐵℘✩  🔶",
    "𝑇𝑀𝐾𝐵℘✩  🔸","𝑇𝑀𝐾𝐵℘✩  🔺","𝑇𝑀𝐾𝐵℘✩  🌊",
]

HELL_EMOJIS = [
    "👹᭄","👺᭄","😈᭄","💀᭄","☠️᭄","🔱᭄","🩸᭄","🕷᭄","🕸᭄",
    "🦇᭄","🌑᭄","🖤᭄","🔮᭄","⚰️᭄","🪦᭄","🗡️᭄","⚔️᭄","🔥᭄",
    "💥᭄","😱᭄","🤬᭄","👻᭄","🎃᭄","🦴᭄","💣᭄","🧿᭄","🌚᭄",
    "🕯️᭄","🪄᭄","🧙","🧛᭄","🧟᭄","🐺᭄","🦉᭄","🐍᭄","🦂᭄",
]

SYMBOL_LIST = [
    "×","~","•","★","☆","▲","▼","◆","◇","■","□","●","○",
    "✦","✧","⚡","✨","💫","🔱","⚜️","❋","✿","❀","✾","❃",
    "❂","❁","꧁","꧂","༺","༻","《","》","【","】","∞","Ω","Δ",
    "Σ","Ψ","Φ","Λ","Θ","©","®","™","⁂","※","✰","✯","✮",
]

FLAG_NC_EMOJIS = [
    "⊱🩵⊰{text}⊱🩵⊰","⊱🌹⊰{text}⊱🌹⊰","𐙚🧸ྀི{text}𐙚🧸ྀི",
    "⊱⚡⊰{text}⊱⚡⊰","⊱🪷⊰{text}⊱🪷⊰","𓍢ִ໋🌷͙֒{text}𓍢ִ໋🌷͙֒",
    "💋ྀིྀི{text}💋ྀིྀི","˚.🎀༘⋆{text}˚.🎀༘⋆","⊱🕶️⊰{text}⊱🕶️⊰",
    "⊱💮⊰{text}⊱💮⊰","⊱🌸⊰{text}⊱🌸⊰",
]

GAME_EMOJIS = ["🎮","🕹","🎰","🎲","♟","🎯","🎳","👾","🧩","🎬","🎨","🎭","🎪","🎤","🎧","🎼","🎹","🥁","🎸","🎻","🪕"]
TOOL_EMOJIS = ["🔧","🔨","⚒","🛠","⛏","🔩","⚙️","🧱","⛓","🧰","🗜","⚖️","🦯","🔗","🧲","🔫","💣","🧨","🪓","🔪","🗡","⚔️","🛡"]
LOOP_EMOJIS = ["🔄","🔁","🔂","🔃","♻️","➰","➿","♾","🌀"]
CAR_EMOJIS = ["🚗","🚕","🚙","🚌","🚎","🏎","🚓","🚑","🚒","🚐","🛻","🚚","🚛","🚜","🦽","🛴","🚲","🛵","🏍","🛺","🚁","✈️","🛩","🚀","🛸"]
HAND_EMOJIS = ["👋","🤚","🖐","✋","🖖","👌","🤌","🤏","✌️","🤞","🤟","🤘","🤙","👈","👉","👆","🖕","👇","☝️","👍","👎","✊","👊","🤛","🤜","👏","🙌","👐","🤲","🤝","🙏"]
HUMAN_EMOJIS = ["👶","👧","🧒","👦","👩","🧑","👨","👩‍🦱","🧑‍🦱","👨‍🦱","👩‍🦰","🧑‍🦰","👨‍🦰","👱‍♀️","👱","👱‍♂️","👩‍🦳","🧑‍🦳","👨‍🦳","👩‍🦲","🧑‍🦲","👨‍🦲","🧔‍♀️","🧔","🧔‍♂️","👵","🧓","👴","👲","👳‍♀️","👳","👳‍♂️","🧕","👮‍♀️","👮","👮‍♂️"]
MOON_EMOJIS = ["🌕","🌖","🌗","🌘","🌑","🌒","🌓","🌔","🌙","🌛","🌜","🌚","🌝","🌞","⭐","🌟","✨","⚡","☄️","💫","🔥"]
KISS_EMOJIS = ["😗","😙","😚","😘","🥰","😍","🤩","💋","💌","💘","💝","💖","💗","💓","💞","💕","❣️","💔","❤️‍🔥","❤️‍🩹","❤️","🧡","💛","💚","💙","💜","🤎","🖤","🤍"]
FOOD_EMOJIS = ["🍏","🍎","🍐","🍊","🍋","🍌","🍉","🍇","🍓","🫐","🍒","🍑","🥭","🍍","🥥","🥝","🍅","🍆","🥑","🥦","🥬","🥒","🌶","🧄","🧅","🥔","🥐","🥯","🍞","🧀","🥚","🍳","🧈","🥞","🧇","🥓","🥩","🍗","🍖","🌭","🍔","🍟","🍕","🥪","🌮","🌯","🥗","🥘","🍝","🍜","🍲","🍛","🍣","🍱","🥟","🍤","🍙","🍚","🍦","🥧","🧁","🍰","🎂","🍩","🍪"]
ANIMAL_EMOJIS = ["🐶","🐱","🐭","🐹","🐰","🦊","🐻","🐼","🐨","🐯","🦁","🐮","🐷","🐸","🐵","🐔","🐧","🐦","🐤","🐣","🦅","🦆","🦢","🦉","🐴","🦄","🐝","🦋","🐌","🐞","🐜","🕷","🕸","🦂","🐢","🐍","🦎","🐙","🦑","🐡","🐠","🐟","🐬","🐳","🐋","🦈","🐊","🐅","🐆","🦓","🦍"]

# ===========================================================
# AI / VOICE HELPERS
# ===========================================================
_AIOHTTP_SESSION = None

async def _get_session():
    global _AIOHTTP_SESSION
    if _AIOHTTP_SESSION is None or _AIOHTTP_SESSION.closed:
        connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
        _AIOHTTP_SESSION = aiohttp.ClientSession(connector=connector)
    return _AIOHTTP_SESSION

async def gemini_ask(history):
    if not GEMINI_API_KEY:
        return '👀🖤'
    payload = {
        'system_instruction': {'parts': [{'text': AI_SYSTEM_PROMPT}]},
        'contents': history,
        'generationConfig': {'temperature': 0.85, 'maxOutputTokens': 1024},
    }
    try:
        session = await _get_session()
        async with session.post(GEMINI_URL, params={'key': GEMINI_API_KEY}, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                text = await resp.text()
                return f"❌ Gemini HTTP {resp.status}: {text[:200]}"
            data = await resp.json()
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except asyncio.TimeoutError:
        return '❌ Gemini timeout — try again.'
    except Exception as e:
        return f"❌ AI error: {e}"

async def generate_voice_ogg(text, char_num):
    char = ANIME_CHARACTERS.get(char_num)
    if not char:
        return None
    _, _, voice, rate, pitch, _ = char
    tmp_mp3 = tempfile.mktemp(suffix='.mp3')
    tmp_ogg = tempfile.mktemp(suffix='.ogg')
    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(tmp_mp3)
        result = subprocess.run(['ffmpeg', '-y', '-i', tmp_mp3, '-c:a', 'libopus', '-b:a', '64k', tmp_ogg], capture_output=True)
        if result.returncode != 0:
            return None
        with open(tmp_ogg, 'rb') as f:
            return f.read()
    except Exception:
        return None
    finally:
        for p in (tmp_mp3, tmp_ogg):
            try:
                os.remove(p)
            except Exception:
                pass

def extract_retry_after(error_str):
    m = re.search(r'retry after (\d+)', error_str.lower())
    return int(m.group(1)) if m else None

# ===========================================================
# FLASK HEALTH SERVER
# ===========================================================
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return jsonify({'status': 'ok', 'bots': len(TOKENS), 'message': 'Batman Multi-Bot is running!'})

@flask_app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'bots_running': len(apps)})

def run_flask():
    flask_app.run(host='0.0.0.0', port=9000, debug=False, use_reloader=False)

# ===========================================================
# NC LOOP FUNCTIONS — from abbu (original flat style)
# ===========================================================
async def hindinc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            new_title = HINDINC_PATTERNS[i % len(HINDINC_PATTERNS)].format(text=text)
            await bot.set_chat_title(chat_id, new_title)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def urdunc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            new_title = URDU_PATTERNS[i % len(URDU_PATTERNS)].format(text=text)
            await bot.set_chat_title(chat_id, new_title)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def bengalnc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            new_title = BENGALI_PATTERNS[i % len(BENGALI_PATTERNS)].format(text=text)
            await bot.set_chat_title(chat_id, new_title)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def biharinc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            new_title = BIHARI_PATTERNS[i % len(BIHARI_PATTERNS)].format(text=text)
            await bot.set_chat_title(chat_id, new_title)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def engnc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            new_title = ENGLISH_PATTERNS[i % len(ENGLISH_PATTERNS)].format(text=text)
            await bot.set_chat_title(chat_id, new_title)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def emonc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = EMOJI_NC_EMOJIS[i % len(EMOJI_NC_EMOJIS)]
            new_title = EMOJI_NC_PATTERN.format(text=text, emoji=emoji)
            await bot.set_chat_title(chat_id, new_title)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def nc1_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = NC1_EMOJIS[i % len(NC1_EMOJIS)]
            await bot.set_chat_title(chat_id, NC1_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def nc2_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = NC2_EMOJIS[i % len(NC2_EMOJIS)]
            await bot.set_chat_title(chat_id, NC2_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def nc3_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = NC3_EMOJIS[i % len(NC3_EMOJIS)]
            await bot.set_chat_title(chat_id, NC3_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def nc4_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = NC4_EMOJIS[i % len(NC4_EMOJIS)]
            await bot.set_chat_title(chat_id, NC4_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def nc5_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = NC5_EMOJIS[i % len(NC5_EMOJIS)]
            await bot.set_chat_title(chat_id, NC5_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def knc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = KNC_EMOJIS[i % len(KNC_EMOJIS)]
            await bot.set_chat_title(chat_id, KNC_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def anc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = ANC_EMOJIS[i % len(ANC_EMOJIS)]
            await bot.set_chat_title(chat_id, ANC_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def fnc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            emoji = FNC_EMOJIS[i % len(FNC_EMOJIS)]
            await bot.set_chat_title(chat_id, FNC_PATTERN.format(text=text, emoji=emoji))
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

# ===========================================================
# NEW NC LOOP FUNCTIONS — from gawd (extra NC types)
# ===========================================================
def _nc_format(template, text):
    if '{target}' in template:
        return template.format(target=text)
    elif '{text}' in template:
        return template.format(text=text)
    return f"{template} {text} {template}"

async def _generic_nc_loop(bot, chat_id, text, items):
    i = 0
    while True:
        try:
            title = _nc_format(items[i % len(items)], text)
            await bot.set_chat_title(chat_id, title)
            i += 1
            await asyncio.sleep(max(GLOBAL_DELAY, 3.0))
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1.0)
        except (TimedOut, NetworkError):
            await asyncio.sleep(0.5)
        except Exception:
            i += 1
            await asyncio.sleep(0.5)

async def ncheart_loop(bot, chat_id, text):
    await _generic_nc_loop(bot, chat_id, text, NC_heart_MESSAGES)

async def ncflag_loop(bot, chat_id, text):
    await _generic_nc_loop(bot, chat_id, text, NC_FLAG_MESSAGES)

async def dotzkeng_loop(bot, chat_id, text):
    await _generic_nc_loop(bot, chat_id, text, DOTZKENG_MESSAGES)

async def nccurly_loop(bot, chat_id, text):
    await _generic_nc_loop(bot, chat_id, text, NC_WEB_MESSAGES)

async def timenc_loop(bot, chat_id, text):
    await _generic_nc_loop(bot, chat_id, text, TIME_NC_MESSAGES)

async def flowernc_loop(bot, chat_id, text):
    await _generic_nc_loop(bot, chat_id, text, FLOWER_NC_MESSAGES)

async def namenc_loop(bot, chat_id, text):
    await _generic_nc_loop(bot, chat_id, text, NAME_CHANGE_MESSAGES)

async def wizard_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            e1, e2 = random.sample(WIZARD_EMOJIS, 2)
            await bot.set_chat_title(chat_id, f"{e1} {text} {e2}")
            i += 1
            await asyncio.sleep(max(GLOBAL_DELAY, 3.0))
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1.0)
        except Exception:
            await asyncio.sleep(0.5)

async def whitenc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            e = WHITE_EMOJIS[i % len(WHITE_EMOJIS)]
            await bot.set_chat_title(chat_id, f"{e} {text} {e}")
            i += 1
            await asyncio.sleep(max(GLOBAL_DELAY, 3.0))
        except asyncio.CancelledError:
            break
        except RetryAfter as e2:
            await asyncio.sleep(e2.retry_after + 1.0)
        except Exception:
            await asyncio.sleep(0.5)

async def blacknc_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            e = BLACK_EMOJIS[i % len(BLACK_EMOJIS)]
            await bot.set_chat_title(chat_id, f"{e} {text} {e}")
            i += 1
            await asyncio.sleep(max(GLOBAL_DELAY, 3.0))
        except asyncio.CancelledError:
            break
        except RetryAfter as e2:
            await asyncio.sleep(e2.retry_after + 1.0)
        except Exception:
            await asyncio.sleep(0.5)

async def flagemo_loop(bot, chat_id, text):
    i = 0
    while True:
        try:
            e = FLAG_EMOJIS[i % len(FLAG_EMOJIS)]
            await bot.set_chat_title(chat_id, f"{e} {text} {e}")
            i += 1
            await asyncio.sleep(max(GLOBAL_DELAY, 3.0))
        except asyncio.CancelledError:
            break
        except RetryAfter as e2:
            await asyncio.sleep(e2.retry_after + 1.0)
        except Exception:
            await asyncio.sleep(0.5)

async def _emoji_nc_loop(bot, chat_id, text, emoji_list):
    i = 0
    while True:
        try:
            e = emoji_list[i % len(emoji_list)]
            title = _nc_format(e, text) if ('{target}' in e or '{text}' in e) else f"{e} {text} {e}"
            await bot.set_chat_title(chat_id, title)
            i += 1
            await asyncio.sleep(max(GLOBAL_DELAY, 3.0))
        except asyncio.CancelledError:
            break
        except RetryAfter as e2:
            await asyncio.sleep(e2.retry_after + 1.0)
        except Exception:
            await asyncio.sleep(0.5)

async def firenc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, FIRE_EMOJIS)

async def hotnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, FIRE_EMOJIS)

async def waternc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, WATER_EMOJIS)

async def lavanc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, LAVA_EMOJIS)

async def hellnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, HELL_EMOJIS)

async def symbolnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, SYMBOL_LIST)

async def flagncnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, FLAG_NC_EMOJIS)

async def gamenc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, GAME_EMOJIS)

async def toolnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, TOOL_EMOJIS)

async def loopnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, LOOP_EMOJIS)

async def carnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, CAR_EMOJIS)

async def handnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, HAND_EMOJIS)

async def humannc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, HUMAN_EMOJIS)

async def moonnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, MOON_EMOJIS)

async def kissnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, KISS_EMOJIS)

async def foodnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, FOOD_EMOJIS)

async def animalnc_loop(bot, chat_id, text):
    await _emoji_nc_loop(bot, chat_id, text, ANIMAL_EMOJIS)

# ===========================================================
# SLIDE LOOP FUNCTIONS
# ===========================================================
async def slide1_loop(bot, chat_id, target_msg_id):
    i = 0
    while True:
        try:
            await bot.send_message(chat_id, SLIDE1_MESSAGES[i % len(SLIDE1_MESSAGES)], reply_to_message_id=target_msg_id)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def slide2_loop(bot, chat_id, target_msg_id):
    i = 0
    while True:
        try:
            await bot.send_message(chat_id, SLIDE2_MESSAGES[i % len(SLIDE2_MESSAGES)], reply_to_message_id=target_msg_id)
            i += 1
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def slide3_loop(bot, chat_id, target_msg_id, text):
    while True:
        try:
            await bot.send_message(chat_id, SLIDE3_PATTERN.format(text=text), reply_to_message_id=target_msg_id)
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

# ===========================================================
# SPAM LOOP FUNCTIONS — from abbu
# ===========================================================
async def spam1_loop(bot, chat_id, text):
    while True:
        try:
            await bot.send_message(chat_id, SPAM1_PATTERN.format(text=text))
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def spam2_loop(bot, chat_id, text):
    while True:
        try:
            await bot.send_message(chat_id, SPAM2_PATTERN.format(text=text))
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def spam3_loop(bot, chat_id, text):
    while True:
        try:
            await bot.send_message(chat_id, SPAM3_PATTERN.format(text=text))
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

async def spam4_loop(bot, chat_id, text):
    while True:
        try:
            await bot.send_message(chat_id, SPAM4_PATTERN.format(text=text))
            await asyncio.sleep(GLOBAL_DELAY)
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            await asyncio.sleep(1)

# ===========================================================
# RAID SPAM LOOP FUNCTION — from gawd
# ===========================================================
async def raid_spam_loop_fn(bot, chat_id, text):
    i = 0
    while True:
        try:
            msg = RAID_TEXTS[i % len(RAID_TEXTS)]
            if '{target}' in msg:
                msg = msg.format(target=text)
            elif '{text}' in msg:
                msg = msg.format(text=text)
            await bot.send_message(chat_id, msg)
            i += 1
            await asyncio.sleep(max(GLOBAL_DELAY, random.uniform(0.1, 0.4)))
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1.0)
        except (TimedOut, NetworkError):
            await asyncio.sleep(1.0)
        except Exception:
            await asyncio.sleep(1.0)

# ===========================================================
# PHOTO LOOP FUNCTION — from abbu
# ===========================================================
async def photo_loop(bot, chat_id):
    while True:
        try:
            if chat_id not in chat_photos or not chat_photos[chat_id]:
                await asyncio.sleep(5.0)
                continue
            file_id = random.choice(chat_photos[chat_id])
            photo_file = await bot.get_file(file_id)
            buf = io.BytesIO()
            await photo_file.download_to_memory(buf)
            buf.seek(0)
            await bot.set_chat_photo(chat_id=chat_id, photo=buf)
            await asyncio.sleep(0.5)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Photo change error: {e}")
            await asyncio.sleep(5.0)

# ===========================================================
# GC PHOTO LOOP FUNCTION — from gawd
# ===========================================================
async def gc_photo_loop(bot, chat_id):
    gc_image_slots = [f"gc_image_{i}.png" for i in range(1, 11) if os.path.exists(f"gc_image_{i}.png")]
    idx = 0
    while True:
        try:
            gc_image_slots = [f"gc_image_{i}.png" for i in range(1, 11) if os.path.exists(f"gc_image_{i}.png")]
            if not gc_image_slots:
                await asyncio.sleep(5.0)
                continue
            path = gc_image_slots[idx % len(gc_image_slots)]
            if not os.path.exists(path):
                idx += 1
                await asyncio.sleep(1.0)
                continue
            with open(path, 'rb') as f:
                photo_bytes = f.read()
            await bot.set_chat_photo(chat_id=chat_id, photo=io.BytesIO(photo_bytes))
            idx += 1
            await asyncio.sleep(max(GLOBAL_DELAY, 2.0))
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1.0)
        except (TimedOut, NetworkError):
            await asyncio.sleep(3.0)
        except Exception:
            await asyncio.sleep(10.0)

# ===========================================================
# DELETE ALL HISTORY LOOP — from gawd
# ===========================================================
async def delete_history_loop(bot, chat_id, start_msg_id):
    msg_id = start_msg_id
    while True:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            msg_id -= 1
            await asyncio.sleep(max(GLOBAL_DELAY, 0.05))
        except asyncio.CancelledError:
            break
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1.0)
        except (TimedOut, NetworkError):
            await asyncio.sleep(0.5)
        except Exception:
            msg_id -= 1
            await asyncio.sleep(0.05)

# ===========================================================
# HELPER: cancel nc tasks for a chat
# ===========================================================
def _cancel_tasks(task_dict, chat_id):
    if chat_id in task_dict:
        item = task_dict.pop(chat_id)
        items = item if isinstance(item, list) else [item]
        for t in items:
            try:
                t.cancel()
            except Exception:
                pass

def _start_multi_nc(bots_list, loop_fn, chat_id, text):
    return [asyncio.create_task(loop_fn(b, chat_id, text)) for b in bots_list]

# ===========================================================
# NC COMMAND HANDLERS — from abbu (original)
# ===========================================================
@sudo_only
async def hindinc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /hindinc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, hindinc_loop, chat_id, text)
    await update.message.reply_text(f"✅ Hindi NC started!\n📝 Text: {text}")

@sudo_only
async def urdunc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /urdunc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, urdunc_loop, chat_id, text)
    await update.message.reply_text(f"✅ Urdu NC started!\n📝 Text: {text}")

@sudo_only
async def bengalnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /bengalnc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, bengalnc_loop, chat_id, text)
    await update.message.reply_text(f"✅ Bengali NC started!\n📝 Text: {text}")

@sudo_only
async def biharinc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /biharinc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, biharinc_loop, chat_id, text)
    await update.message.reply_text(f"✅ Bihari NC started!\n📝 Text: {text}")

@sudo_only
async def chinesenc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Chinese NC is coming soon!")

@sudo_only
async def engnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /engnc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, engnc_loop, chat_id, text)
    await update.message.reply_text(f"✅ English NC started!\n📝 Text: {text}")

@sudo_only
async def emonc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /emonc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, emonc_loop, chat_id, text)
    await update.message.reply_text(f"✅ Emoji NC started!\n📝 Text: {text}")

@sudo_only
async def nc1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /nc1 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, nc1_loop, chat_id, text)
    await update.message.reply_text(f"✅ NC1 started!\n📝 Text: {text}")

@sudo_only
async def nc2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /nc2 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, nc2_loop, chat_id, text)
    await update.message.reply_text(f"✅ NC2 started!\n📝 Text: {text}")

@sudo_only
async def nc3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /nc3 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, nc3_loop, chat_id, text)
    await update.message.reply_text(f"✅ NC3 started!\n📝 Text: {text}")

@sudo_only
async def nc4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /nc4 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, nc4_loop, chat_id, text)
    await update.message.reply_text(f"✅ NC4 started!\n📝 Text: {text}")

@sudo_only
async def nc5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /nc5 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, nc5_loop, chat_id, text)
    await update.message.reply_text(f"✅ NC5 started!\n📝 Text: {text}")

@sudo_only
async def knc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /knc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, knc_loop, chat_id, text)
    await update.message.reply_text(f"✅ KNC started!\n📝 Text: {text}")

@sudo_only
async def anc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /anc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, anc_loop, chat_id, text)
    await update.message.reply_text(f"✅ ANC started!\n📝 Text: {text}")

@sudo_only
async def fnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /fnc <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    nc_tasks[chat_id] = _start_multi_nc(bots, fnc_loop, chat_id, text)
    await update.message.reply_text(f"✅ FNC started!\n📝 Text: {text}")

# ===========================================================
# NEW NC COMMAND HANDLERS — from gawd
# ===========================================================
def _nc_cmd_handler(loop_fn, label):
    @sudo_only
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            return await update.message.reply_text(f"❌ Usage: /{label} <text>")
        text = " ".join(context.args)
        chat_id = update.message.chat_id
        _cancel_tasks(nc_tasks, chat_id)
        nc_tasks[chat_id] = _start_multi_nc(bots, loop_fn, chat_id, text)
        await update.message.reply_text(f"✅ {label.upper()} started!\n📝 Text: {text}")
    handler.__name__ = label
    return handler

ncheart = _nc_cmd_handler(ncheart_loop, 'ncheart')
ncflag = _nc_cmd_handler(ncflag_loop, 'ncflag')
dotzkeng = _nc_cmd_handler(dotzkeng_loop, 'dotzkeng')
nccurly = _nc_cmd_handler(nccurly_loop, 'nccurly')
timenc = _nc_cmd_handler(timenc_loop, 'timenc')
flowernc = _nc_cmd_handler(flowernc_loop, 'flowernc')
namenc = _nc_cmd_handler(namenc_loop, 'namenc')
wizard = _nc_cmd_handler(wizard_loop, 'wizard')
whitenc = _nc_cmd_handler(whitenc_loop, 'whitenc')
blacknc_cmd = _nc_cmd_handler(blacknc_loop, 'blacknc')
flagemo = _nc_cmd_handler(flagemo_loop, 'flagemo')
firenc = _nc_cmd_handler(firenc_loop, 'firenc')
hotnc = _nc_cmd_handler(hotnc_loop, 'hotnc')
waternc = _nc_cmd_handler(waternc_loop, 'waternc')
lavanc = _nc_cmd_handler(lavanc_loop, 'lavanc')
hellnc = _nc_cmd_handler(hellnc_loop, 'hellnc')
symbolnc = _nc_cmd_handler(symbolnc_loop, 'symbolnc')
flagncnc = _nc_cmd_handler(flagncnc_loop, 'flagncnc')
gamenc = _nc_cmd_handler(gamenc_loop, 'gamenc')
toolnc = _nc_cmd_handler(toolnc_loop, 'toolnc')
loopnc = _nc_cmd_handler(loopnc_loop, 'loopnc')
carnc = _nc_cmd_handler(carnc_loop, 'carnc')
handnc = _nc_cmd_handler(handnc_loop, 'handnc')
humannc = _nc_cmd_handler(humannc_loop, 'humannc')
moonnc = _nc_cmd_handler(moonnc_loop, 'moonnc')
kissnc = _nc_cmd_handler(kissnc_loop, 'kissnc')
foodnc = _nc_cmd_handler(foodnc_loop, 'foodnc')
animalnc = _nc_cmd_handler(animalnc_loop, 'animalnc')

# ===========================================================
# SLIDE COMMAND HANDLERS
# ===========================================================
@sudo_only
async def slide1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to a message to start slide1!")
    chat_id = update.message.chat_id
    target_msg_id = update.message.reply_to_message.message_id
    _cancel_tasks(slider_tasks, chat_id)
    slider_tasks[chat_id] = [asyncio.create_task(slide1_loop(b, chat_id, target_msg_id)) for b in bots]
    await update.message.reply_text("✅ Slide1 started!")

@sudo_only
async def slide2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to a message to start slide2!")
    chat_id = update.message.chat_id
    target_msg_id = update.message.reply_to_message.message_id
    _cancel_tasks(slider_tasks, chat_id)
    slider_tasks[chat_id] = [asyncio.create_task(slide2_loop(b, chat_id, target_msg_id)) for b in bots]
    await update.message.reply_text("✅ Slide2 started!")

@sudo_only
async def slide3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /slide3 <text> (reply to a message)")
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to a message to start slide3!")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    target_msg_id = update.message.reply_to_message.message_id
    _cancel_tasks(slider_tasks, chat_id)
    slider_tasks[chat_id] = [asyncio.create_task(slide3_loop(b, chat_id, target_msg_id, text)) for b in bots]
    await update.message.reply_text(f"✅ Slide3 started!\n📝 Text: {text}")

# ===========================================================
# SPAM COMMAND HANDLERS — from abbu
# ===========================================================
@sudo_only
async def spam1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /spam1 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(spam_tasks, chat_id)
    spam_tasks[chat_id] = [asyncio.create_task(spam1_loop(b, chat_id, text)) for b in bots]
    await update.message.reply_text(f"✅ Spam1 started!\n📝 Text: {text}")

@sudo_only
async def spam2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /spam2 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(spam_tasks, chat_id)
    spam_tasks[chat_id] = [asyncio.create_task(spam2_loop(b, chat_id, text)) for b in bots]
    await update.message.reply_text(f"✅ Spam2 started!\n📝 Text: {text}")

@sudo_only
async def spam3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /spam3 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(spam_tasks, chat_id)
    spam_tasks[chat_id] = [asyncio.create_task(spam3_loop(b, chat_id, text)) for b in bots]
    await update.message.reply_text(f"✅ Spam3 started!\n📝 Text: {text}")

@sudo_only
async def spam4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /spam4 <text>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(spam_tasks, chat_id)
    spam_tasks[chat_id] = [asyncio.create_task(spam4_loop(b, chat_id, text)) for b in bots]
    await update.message.reply_text(f"✅ Spam4 started!\n📝 Text: {text}")

# ===========================================================
# RAID SPAM — from gawd
# ===========================================================
@sudo_only
async def raidspam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /raidspam <target>")
    text = " ".join(context.args)
    chat_id = update.message.chat_id
    _cancel_tasks(raid_tasks, chat_id)
    raid_tasks[chat_id] = [asyncio.create_task(raid_spam_loop_fn(b, chat_id, text)) for b in bots]
    await update.message.reply_text(f"💣 Raid spam started on: {text}")

@sudo_only
async def stopraidspam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _cancel_tasks(raid_tasks, chat_id)
    await update.message.reply_text("🛑 Raid spam stopped!")

# ===========================================================
# PHOTO COMMAND HANDLERS — from abbu
# ===========================================================
@sudo_only
async def savephoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        return await update.message.reply_text("⚠️ Reply to a photo to save it!")
    chat_id = update.message.chat_id
    file_id = update.message.reply_to_message.photo[-1].file_id
    if chat_id not in chat_photos:
        chat_photos[chat_id] = []
    chat_photos[chat_id].append(file_id)
    await update.message.reply_text(f"✅ Photo saved! Total: {len(chat_photos[chat_id])}")

@sudo_only
async def startphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id not in chat_photos or len(chat_photos[chat_id]) < 1:
        return await update.message.reply_text("⚠️ Save at least 1 photo first using /savephoto!")
    _cancel_tasks(photo_tasks, chat_id)
    photo_tasks[chat_id] = [asyncio.create_task(photo_loop(b, chat_id)) for b in bots]
    await update.message.reply_text(f"🔄 Photo loop started for {len(bots)} bots!")

@sudo_only
async def stopphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in photo_tasks:
        _cancel_tasks(photo_tasks, chat_id)
        await update.message.reply_text("⏹ Photo loop stopped!")
    else:
        await update.message.reply_text("❌ No active photo loop")

@sudo_only
async def clearphotos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in chat_photos:
        del chat_photos[chat_id]
        await update.message.reply_text("🗑 Saved photos cleared!")
    else:
        await update.message.reply_text("❌ No saved photos to clear")

@sudo_only
async def listphotos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id not in chat_photos or not chat_photos[chat_id]:
        return await update.message.reply_text("📭 No photos saved yet!")
    await update.message.reply_text(f"📸 Total saved photos: {len(chat_photos[chat_id])}")

# ===========================================================
# GC PHOTO LOOP COMMAND — from gawd
# ===========================================================
@sudo_only
async def gc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    gc_slots = [f"gc_image_{i}.png" for i in range(1, 11) if os.path.exists(f"gc_image_{i}.png")]
    if not gc_slots:
        return await update.message.reply_text("❌ No GC images found!\nPlace gc_image_1.png … gc_image_10.png in the same folder.")
    _cancel_tasks(gc_tasks, chat_id)
    gc_tasks[chat_id] = [asyncio.create_task(gc_photo_loop(b, chat_id)) for b in bots]
    await update.message.reply_text(f"🖼 GC photo loop started ({len(gc_slots)} image(s) found)!")

@sudo_only
async def stopgc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _cancel_tasks(gc_tasks, chat_id)
    await update.message.reply_text("🛑 GC photo loop stopped!")

# ===========================================================
# STOP COMMAND HANDLERS — from abbu
# ===========================================================
@sudo_only
async def stopnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _cancel_tasks(nc_tasks, chat_id)
    await update.message.reply_text("🛑 NC stopped!")

@sudo_only
async def stopspam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _cancel_tasks(spam_tasks, chat_id)
    await update.message.reply_text("🛑 Spam stopped!")

@sudo_only
async def stopslide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _cancel_tasks(slider_tasks, chat_id)
    await update.message.reply_text("🛑 Slide stopped!")

@sudo_only
async def stopall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    stopped = []
    for d, label in [(nc_tasks, 'NC'), (spam_tasks, 'Spam'), (slider_tasks, 'Slide'),
                     (photo_tasks, 'Photo'), (gc_tasks, 'GC'), (raid_tasks, 'Raid'),
                     (delete_tasks, 'Delete'), (deluser_tasks, 'DelUser')]:
        if chat_id in d:
            _cancel_tasks(d, chat_id)
            stopped.append(label)
    if stopped:
        await update.message.reply_text(f"🛑 Stopped: {', '.join(stopped)}!")
    else:
        await update.message.reply_text("❌ No active activities to stop.")

# ===========================================================
# DELETE ALL HISTORY COMMANDS — from gawd
# ===========================================================
@sudo_only
async def deleteallhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    chat_id = chat.id
    start_msg_id = update.message.message_id
    _cancel_tasks(delete_tasks, chat_id)
    delete_tasks[chat_id] = [asyncio.create_task(delete_history_loop(b, chat_id, start_msg_id - (i * 100))) for i, b in enumerate(bots)]
    await update.message.reply_text("🗑️ Delete all history loop started! Bot must be admin with Delete Messages permission.")

@sudo_only
async def stopdeleteallhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cancel_tasks(delete_tasks, update.effective_chat.id)
    await update.message.reply_text("🛑 Delete all history stopped!")

# ===========================================================
# DELUSER — from gawd
# ===========================================================
@sudo_only
async def deluser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    user_id = None
    user_name = 'Unknown'
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        u = update.message.reply_to_message.from_user
        user_id, user_name = u.id, u.first_name or str(u.id)
    elif context.args:
        try:
            user_id = int(context.args[0])
            user_name = str(user_id)
        except ValueError:
            return await update.message.reply_text("Usage: /deluser (reply) or /deluser <user_id>")
    if not user_id:
        return await update.message.reply_text("Usage: /deluser (reply) or /deluser <user_id>")
    cid = chat.id
    start_msg_id = update.message.message_id
    _cancel_tasks(deluser_tasks, cid)
    deluser_tasks[cid] = [asyncio.create_task(delete_history_loop(b, cid, start_msg_id - (i * 100))) for i, b in enumerate(bots)]
    auto_delete_users.setdefault(cid, set()).add(user_id)
    await update.message.reply_text(f"🎯 DelUser STARTED on {user_name}!\n🗑️ Looping through ALL past messages!\n⚡ Also auto-deleting every NEW message!")

@sudo_only
async def stopdeluser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    _cancel_tasks(deluser_tasks, cid)
    user_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            user_id = int(context.args[0])
        except Exception:
            pass
    if user_id and cid in auto_delete_users:
        auto_delete_users[cid].discard(user_id)
        if not auto_delete_users[cid]:
            del auto_delete_users[cid]
    await update.message.reply_text("🛑 DelUser stopped!")

# ===========================================================
# DELALL — from gawd
# ===========================================================
@sudo_only
async def delall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    if not context.args:
        return await update.message.reply_text("Usage: /delall <target name>")
    text = " ".join(context.args)
    chat_id = chat.id
    start_msg_id = update.message.message_id
    _cancel_tasks(delete_tasks, chat_id)
    _cancel_tasks(nc_tasks, chat_id)
    delete_tasks[chat_id] = [asyncio.create_task(delete_history_loop(b, chat_id, start_msg_id - (i * 100))) for i, b in enumerate(bots)]
    nc_tasks[chat_id] = _start_multi_nc(bots, namenc_loop, chat_id, text)
    await update.message.reply_text(f"🔥 DELALL started!\n🗑️ Delete loop + ⚡ NC loop running!\n🎯 Target: {text}")

@sudo_only
async def stopdelall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _cancel_tasks(delete_tasks, chat_id)
    _cancel_tasks(nc_tasks, chat_id)
    await update.message.reply_text("🛑 DELALL stopped!")

# ===========================================================
# BLOCKNC — from gawd
# ===========================================================
@sudo_only
async def blocknc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    if not context.args:
        return await update.message.reply_text("Usage: /blocknc <protected group name>")
    name = " ".join(context.args)
    cid = chat.id
    blocknc_active[cid] = name
    try:
        await context.bot.set_chat_title(chat_id=cid, title=name)
        await update.message.reply_text(f"🔒 BlockNC ENABLED!\n📛 Group name locked to: *{name}*\n\nAnyone who changes the name will be instantly BANNED and name restored!", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"🔒 BlockNC ENABLED — name locked to: {name}\n⚠️ Could not set title right now: {e}")

@sudo_only
async def stopblocknc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if cid in blocknc_active:
        del blocknc_active[cid]
        await update.message.reply_text("🔓 BlockNC DISABLED — group name is now free to change!")
    else:
        await update.message.reply_text("BlockNC is not active in this chat.")

# ===========================================================
# MODERATION: BAN/UNBAN/MUTE/UNMUTE — from gawd
# ===========================================================
@sudo_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    user_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            user_id = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("Usage: /ban (reply) or /ban <user_id>")
    if not user_id:
        return await update.message.reply_text("Usage: /ban (reply) or /ban <user_id>")
    try:
        await context.bot.ban_chat_member(chat_id=chat.id, user_id=user_id)
        await update.message.reply_text(f"🔨 User {user_id} banned!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to ban: {e}")

@sudo_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    user_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            user_id = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("Usage: /unban (reply) or /unban <user_id>")
    if not user_id:
        return await update.message.reply_text("Usage: /unban (reply) or /unban <user_id>")
    try:
        await context.bot.unban_chat_member(chat_id=chat.id, user_id=user_id, only_if_banned=True)
        await update.message.reply_text(f"✅ User {user_id} unbanned!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to unban: {e}")

@sudo_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    user_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            user_id = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("Usage: /mute (reply) or /mute <user_id>")
    if not user_id:
        return await update.message.reply_text("Usage: /mute (reply) or /mute <user_id>")
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id, user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False, can_send_audios=False, can_send_documents=False,
                can_send_photos=False, can_send_videos=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False
            )
        )
        await update.message.reply_text(f"🔇 User {user_id} muted!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to mute: {e}")

@sudo_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    user_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            user_id = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("Usage: /unmute (reply) or /unmute <user_id>")
    if not user_id:
        return await update.message.reply_text("Usage: /unmute (reply) or /unmute <user_id>")
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id, user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True
            )
        )
        await update.message.reply_text(f"🔊 User {user_id} unmuted!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to unmute: {e}")

# ===========================================================
# MODERATION: WARN SYSTEM — from gawd
# ===========================================================
@sudo_only
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    user_id = None
    user_name = 'Unknown'
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        u = update.message.reply_to_message.from_user
        user_id, user_name = u.id, u.first_name or str(u.id)
    elif context.args:
        try:
            user_id = int(context.args[0])
            user_name = str(user_id)
        except ValueError:
            return await update.message.reply_text("Usage: /warn (reply) or /warn <user_id>")
    if not user_id:
        return await update.message.reply_text("Usage: /warn (reply) or /warn <user_id>")
    cid = chat.id
    limit = warn_limits.get(cid, 3)
    warn_counts.setdefault(cid, {})[user_id] = warn_counts.get(cid, {}).get(user_id, 0) + 1
    count = warn_counts[cid][user_id]
    if count >= limit:
        try:
            await context.bot.ban_chat_member(chat_id=cid, user_id=user_id)
            warn_counts[cid].pop(user_id, None)
            await update.message.reply_text(f"⚠️ {user_name} reached {limit}/{limit} warnings — BANNED 🔨")
        except Exception as e:
            await update.message.reply_text(f"⚠️ {user_name} has {count}/{limit} warns but ban failed: {e}")
    else:
        await update.message.reply_text(f"⚠️ Warning {count}/{limit} issued to {user_name}!\n{'⚠️'*count}{'▪️'*(limit-count)}")

@sudo_only
async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    user_id = None
    user_name = 'Unknown'
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        u = update.message.reply_to_message.from_user
        user_id, user_name = u.id, u.first_name or str(u.id)
    elif context.args:
        try:
            user_id = int(context.args[0])
            user_name = str(user_id)
        except ValueError:
            return await update.message.reply_text("Usage: /warnings (reply) or /warnings <user_id>")
    if not user_id:
        return await update.message.reply_text("Usage: /warnings (reply) or /warnings <user_id>")
    cid = chat.id
    limit = warn_limits.get(cid, 3)
    count = warn_counts.get(cid, {}).get(user_id, 0)
    await update.message.reply_text(f"⚠️ {user_name} has {count}/{limit} warnings\n{'⚠️'*count}{'▪️'*(limit-count)}")

@sudo_only
async def clearwarns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    cid = chat.id
    user_id = None
    user_name = 'chat'
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        u = update.message.reply_to_message.from_user
        user_id, user_name = u.id, u.first_name or str(u.id)
    elif context.args:
        try:
            user_id = int(context.args[0])
            user_name = str(user_id)
        except Exception:
            pass
    if user_id:
        warn_counts.get(cid, {}).pop(user_id, None)
        await update.message.reply_text(f"✅ Warnings cleared for {user_name}!")
    else:
        warn_counts.pop(cid, None)
        await update.message.reply_text("✅ All warnings cleared in this chat!")

@sudo_only
async def setwarnlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    if not context.args:
        return await update.message.reply_text("Usage: /setwarnlimit <number>")
    try:
        limit = int(context.args[0])
        assert 1 <= limit <= 20
    except (ValueError, AssertionError):
        return await update.message.reply_text("Limit must be a number between 1 and 20.")
    warn_limits[chat.id] = limit
    await update.message.reply_text(f"✅ Warn limit set to {limit}.")

# ===========================================================
# DELETE / PURGE — from gawd
# ===========================================================
@sudo_only
async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message with /del to delete it!")
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
        try:
            await update.message.delete()
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to delete: {e}")

@sudo_only
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return await update.message.reply_text("Groups only!")
    try:
        count = int(context.args[0]) if context.args else 10
    except ValueError:
        count = 10
    count = min(max(count, 1), 500)
    start_id = update.message.message_id
    deleted = 0
    status = await update.message.reply_text(f"🗑️ Purging up to {count} messages...")
    for msg_id in range(start_id, start_id - count - 2, -1):
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=msg_id)
            deleted += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    try:
        await status.edit_text(f"✅ Purged {deleted} messages!")
    except Exception:
        pass

# ===========================================================
# AI COMMAND — from gawd
# ===========================================================
@sudo_only
async def ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args and not (update.message.reply_to_message and update.message.reply_to_message.text):
        return await update.message.reply_text("❌ Usage: /ai <question>")
    user_text = " ".join(context.args) if context.args else update.message.reply_to_message.text
    if uid not in AI_HISTORY:
        AI_HISTORY[uid] = []
    AI_HISTORY[uid].append({'role': 'user', 'parts': [{'text': user_text}]})
    if len(AI_HISTORY[uid]) > 20:
        AI_HISTORY[uid] = AI_HISTORY[uid][-20:]
    thinking = await update.message.reply_text("🤔 Thinking...")
    reply = await gemini_ask(AI_HISTORY[uid])
    AI_HISTORY[uid].append({'role': 'model', 'parts': [{'text': reply}]})
    try:
        await thinking.edit_text(reply)
    except Exception:
        await update.message.reply_text(reply)

@sudo_only
async def clearai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    AI_HISTORY.pop(uid, None)
    await update.message.reply_text("✅ AI chat history cleared!")

# ===========================================================
# VOICE COMMAND — from gawd
# ===========================================================
@sudo_only
async def voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        chars_list = "\n".join([f"{k}. {v[0]} {v[1]}" for k, v in ANIME_CHARACTERS.items()])
        return await update.message.reply_text(f"❌ Usage: /voice <char_num> <text>\n\nCharacters:\n{chars_list}")
    try:
        char_num = int(context.args[0])
        text = " ".join(context.args[1:])
    except (ValueError, IndexError):
        return await update.message.reply_text("Usage: /voice <1-10> <text>")
    if not text:
        return await update.message.reply_text("❌ Please provide text after the character number!")
    if char_num not in ANIME_CHARACTERS:
        return await update.message.reply_text(f"❌ Character {char_num} not found! Choose 1-{len(ANIME_CHARACTERS)}")
    char = ANIME_CHARACTERS[char_num]
    thinking = await update.message.reply_text(f"🎙️ Generating {char[0]} {char[1]} voice...")
    audio_data = await generate_voice_ogg(text, char_num)
    if not audio_data:
        return await thinking.edit_text("❌ Voice generation failed! Make sure ffmpeg is installed.")
    try:
        await update.message.reply_voice(voice=io.BytesIO(audio_data), caption=f"{char[0]} {char[1]}: {text[:50]}{'...' if len(text) > 50 else ''}")
        await thinking.delete()
    except Exception as e:
        await thinking.edit_text(f"❌ Failed to send voice: {e}")

# ===========================================================
# CONTROL COMMANDS
# ===========================================================
@sudo_only
async def delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_DELAY
    if not context.args:
        await update.message.reply_text(f"⏱ Current delay: {GLOBAL_DELAY:.3f}s\nUsage: /delay <0.005-0.05>")
        return
    try:
        new_delay = float(context.args[0])
        if new_delay < 0.005 or new_delay > 0.05:
            await update.message.reply_text("❌ Delay must be between 0.005 and 0.05 seconds.")
            return
        GLOBAL_DELAY = new_delay
        await update.message.reply_text(f"✅ Delay set to {GLOBAL_DELAY:.3f}s")
    except ValueError:
        await update.message.reply_text("❌ Invalid number.")

@sudo_only
async def hi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🐍 Batman Multi-Bot is alive!")

# ===========================================================
# SUDO MANAGEMENT
# ===========================================================
@owner_only
async def addsudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to a user's message to add them as sudo!")
    target_user = update.message.reply_to_message.from_user
    uid = target_user.id
    username = target_user.username or target_user.first_name
    SUDO_USERS.add(uid)
    save_sudo()
    await update.message.reply_text(f"✅ Added sudo user: {username} (ID: {uid})")

@owner_only
async def delsudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to a user's message to remove them from sudo!")
    target_user = update.message.reply_to_message.from_user
    uid = target_user.id
    username = target_user.username or target_user.first_name
    if uid == OWNER_ID:
        return await update.message.reply_text("❌ Cannot remove the owner from sudo list!")
    if uid in SUDO_USERS:
        SUDO_USERS.remove(uid)
        save_sudo()
        await update.message.reply_text(f"✅ Removed sudo user: {username} (ID: {uid})")
    else:
        await update.message.reply_text(f"❌ {username} is not in the sudo list!")

@owner_only
async def sudos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SUDO_USERS:
        return await update.message.reply_text("📋 No sudo users added yet.")
    lines = [f"👑 **{uid}** (Owner)" if uid == OWNER_ID else f"🛡️ `{uid}`" for uid in SUDO_USERS]
    await update.message.reply_text(f"**📋 SUDO USERS LIST**\n\n" + "\n".join(lines) + f"\n\n**Total:** {len(SUDO_USERS)}", parse_mode="Markdown")

# ===========================================================
# ADMIN MANAGEMENT
# ===========================================================
@sudo_only
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    promoter_bot = context.bot
    promoter_id = promoter_bot.id
    other_bots = [b for b in bots if b.id != promoter_id]
    if not other_bots:
        return await update.message.reply_text("❌ No other bots found to promote!")
    permissions = {
        'can_change_info': True, 'can_post_messages': True, 'can_edit_messages': True,
        'can_delete_messages': True, 'can_invite_users': True, 'can_restrict_members': True,
        'can_pin_messages': True, 'can_promote_members': True, 'can_manage_video_chats': True,
        'can_manage_chat': True
    }
    promoted_count = 0
    status_msg = await update.message.reply_text("🔄 Promoting bots to admin...")
    for bot in other_bots:
        try:
            await promoter_bot.promote_chat_member(chat_id=chat_id, user_id=bot.id, **permissions)
            promoted_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.warning(f"Failed to promote bot {bot.id}: {e}")
    if promoted_count > 0:
        await status_msg.edit_text(f"✅ Successfully promoted {promoted_count} bot(s) to admin!")
    else:
        await status_msg.edit_text("❌ Failed to promote any bots!\n\nMake sure the issuing bot has 'Add New Admins' permission.")

@sudo_only
async def checkadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    status_msg = await update.message.reply_text("🔄 Checking bot admin status...")
    admin_bots = []
    non_admin_bots = []
    for bot in bots:
        try:
            chat_member = await bot.get_chat_member(chat_id, bot.id)
            if chat_member.status in ['administrator', 'creator']:
                admin_bots.append(f"✅ {str(bot.id)[:10]}... - {chat_member.status}")
            else:
                non_admin_bots.append(f"❌ {str(bot.id)[:10]}... - {chat_member.status}")
        except Exception:
            non_admin_bots.append(f"⚠️ {str(bot.id)[:10]}... - Can't check")
    result = f"**📊 BOT ADMIN STATUS**\n\n"
    result += f"**Admins ({len(admin_bots)}):**\n" + "\n".join(admin_bots) if admin_bots else "No admin bots found"
    result += f"\n\n**Non-Admins ({len(non_admin_bots)}):**\n" + "\n".join(non_admin_bots[:10])
    await status_msg.edit_text(result, parse_mode="Markdown")

# ===========================================================
# BYE
# ===========================================================
@sudo_only
async def bye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    try:
        await update.message.delete()
    except Exception:
        pass
    for bot in bots:
        try:
            await bot.leave_chat(chat_id)
            await asyncio.sleep(0.1)
        except Exception as e:
            logging.warning(f"Bot could not leave: {e}")

# ===========================================================
# HELP
# ===========================================================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_owner_or_sudo(update.effective_user.id):
        help_text = """
  BATMAN MERGED BOT 🦇

═══════════════════════════════════
─────────── 𝑳𝒂𝒏𝒈𝒖𝒂𝒈𝒆 𝑵𝒄 ─────────
/hindinc  /urdunc  /bengalnc
/biharinc  /chinesenc  /engnc

─────────── 𝑵𝒄 𝑺𝒆𝒄𝒕𝒊𝒐𝒏 ─────────
/emonc  /nc1  /nc2  /nc3  /nc4  /nc5
/knc  /anc  /fnc

─────────── 𝑵𝒆𝒘 𝑵𝑪 𝑻𝒚𝒑𝒆𝒔 ─────────
/ncheart  /ncflag  /dotzkeng  /nccurly
/timenc  /flowernc  /namenc  /wizard
/whitenc  /blacknc  /flagemo
/firenc  /hotnc  /waternc  /lavanc
/hellnc  /symbolnc  /flagncnc
/gamenc  /toolnc  /loopnc  /carnc
/handnc  /humannc  /moonnc  /kissnc
/foodnc  /animalnc

─────────── 𝑺𝒍𝒊𝒅𝒆 ─────────
/slide1  /slide2  /slide3 <text>

─────────── 𝑺𝒑𝒂𝒎 ─────────
/spam1  /spam2  /spam3  /spam4
/raidspam <target>  /stopraidspam

─────────── 𝑷𝒉𝒐𝒕𝒐 𝑳𝒐𝒐𝒑 ─────────
/savephoto  /startphoto  /stopphoto
/clearphotos  /listphotos
/gc  /stopgc  (GC photo loop)

─────────── 𝑴𝒐𝒅𝒆𝒓𝒂𝒕𝒊𝒐𝒏 ─────────
/ban  /unban  /mute  /unmute
/warn  /warnings  /clearwarns  /setwarnlimit
/del  /purge [n]
/deleteallhistory  /stopdeleteallhistory
/deluser  /stopdeluser
/delall <name>  /stopdelall
/blocknc <name>  /stopblocknc

─────────── 𝑨𝑰 & 𝑽𝒐𝒊𝒄𝒆 ─────────
/ai <question>  /clearai
/voice <1-10> <text>

─────────── 𝑶𝒘𝒏𝒆𝒓 ─────────
/addsudo  /delsudo  /sudos
/admin  /checkadmin  /bye

─────────── 𝑪𝒐𝒏𝒕𝒓𝒐𝒍𝒔 ─────────
/stopall  /stopnc  /stopspam  /stopslide
/delay  /hi

═══════════════════════════════════
𝐄𝐧𝐣𝐨𝐲 ᯓᡣ𐭭
"""
        await update.message.reply_text(help_text)
    else:
        await update.message.reply_text("sꪶꪖꪜꫀ ִֶָ. ..𓂃 ࣪ ִֶָ🌈་༘࿐ 𝗟𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 -/- ")

# ===========================================================
# AUTO-DELETE MESSAGE HANDLER — from gawd
# ===========================================================
async def auto_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    cid = msg.chat_id
    uid = msg.from_user.id
    if cid in auto_delete_users and uid in auto_delete_users[cid]:
        try:
            await context.bot.delete_message(chat_id=cid, message_id=msg.message_id)
        except Exception:
            pass

# ===========================================================
# BOT SETUP
# ===========================================================
def build_app(token):
    app = Application.builder().token(token).build()

    # ── Language NC ──
    app.add_handler(CommandHandler("hindinc", hindinc))
    app.add_handler(CommandHandler("urdunc", urdunc))
    app.add_handler(CommandHandler("bengalnc", bengalnc))
    app.add_handler(CommandHandler("biharinc", biharinc))
    app.add_handler(CommandHandler("chinesenc", chinesenc))
    app.add_handler(CommandHandler("engnc", engnc))

    # ── NC Section (abbu) ──
    app.add_handler(CommandHandler("emonc", emonc))
    app.add_handler(CommandHandler("nc1", nc1))
    app.add_handler(CommandHandler("nc2", nc2))
    app.add_handler(CommandHandler("nc3", nc3))
    app.add_handler(CommandHandler("nc4", nc4))
    app.add_handler(CommandHandler("nc5", nc5))
    app.add_handler(CommandHandler("knc", knc))
    app.add_handler(CommandHandler("anc", anc))
    app.add_handler(CommandHandler("fnc", fnc))

    # ── New NC Types (gawd) ──
    app.add_handler(CommandHandler("ncheart", ncheart))
    app.add_handler(CommandHandler("ncflag", ncflag))
    app.add_handler(CommandHandler("dotzkeng", dotzkeng))
    app.add_handler(CommandHandler("nccurly", nccurly))
    app.add_handler(CommandHandler("timenc", timenc))
    app.add_handler(CommandHandler("flowernc", flowernc))
    app.add_handler(CommandHandler("namenc", namenc))
    app.add_handler(CommandHandler("wizard", wizard))
    app.add_handler(CommandHandler("whitenc", whitenc))
    app.add_handler(CommandHandler("blacknc", blacknc_cmd))
    app.add_handler(CommandHandler("flagemo", flagemo))
    app.add_handler(CommandHandler("firenc", firenc))
    app.add_handler(CommandHandler("hotnc", hotnc))
    app.add_handler(CommandHandler("waternc", waternc))
    app.add_handler(CommandHandler("lavanc", lavanc))
    app.add_handler(CommandHandler("hellnc", hellnc))
    app.add_handler(CommandHandler("symbolnc", symbolnc))
    app.add_handler(CommandHandler("flagncnc", flagncnc))
    app.add_handler(CommandHandler("gamenc", gamenc))
    app.add_handler(CommandHandler("toolnc", toolnc))
    app.add_handler(CommandHandler("loopnc", loopnc))
    app.add_handler(CommandHandler("carnc", carnc))
    app.add_handler(CommandHandler("handnc", handnc))
    app.add_handler(CommandHandler("humannc", humannc))
    app.add_handler(CommandHandler("moonnc", moonnc))
    app.add_handler(CommandHandler("kissnc", kissnc))
    app.add_handler(CommandHandler("foodnc", foodnc))
    app.add_handler(CommandHandler("animalnc", animalnc))

    # ── Slide ──
    app.add_handler(CommandHandler("slide1", slide1))
    app.add_handler(CommandHandler("slide2", slide2))
    app.add_handler(CommandHandler("slide3", slide3))

    # ── Spam ──
    app.add_handler(CommandHandler("spam1", spam1))
    app.add_handler(CommandHandler("spam2", spam2))
    app.add_handler(CommandHandler("spam3", spam3))
    app.add_handler(CommandHandler("spam4", spam4))
    app.add_handler(CommandHandler("raidspam", raidspam))
    app.add_handler(CommandHandler("stopraidspam", stopraidspam))

    # ── Photo / GC ──
    app.add_handler(CommandHandler("savephoto", savephoto))
    app.add_handler(CommandHandler("startphoto", startphoto))
    app.add_handler(CommandHandler("stopphoto", stopphoto))
    app.add_handler(CommandHandler("clearphotos", clearphotos))
    app.add_handler(CommandHandler("listphotos", listphotos))
    app.add_handler(CommandHandler("gc", gc))
    app.add_handler(CommandHandler("stopgc", stopgc))

    # ── Stop Commands ──
    app.add_handler(CommandHandler("stopnc", stopnc))
    app.add_handler(CommandHandler("stopspam", stopspam))
    app.add_handler(CommandHandler("stopslide", stopslide))
    app.add_handler(CommandHandler("stopall", stopall))

    # ── Moderation ──
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warnings", warnings))
    app.add_handler(CommandHandler("clearwarns", clearwarns))
    app.add_handler(CommandHandler("setwarnlimit", setwarnlimit))
    app.add_handler(CommandHandler("del", del_cmd))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(CommandHandler("deleteallhistory", deleteallhistory))
    app.add_handler(CommandHandler("stopdeleteallhistory", stopdeleteallhistory))
    app.add_handler(CommandHandler("deluser", deluser))
    app.add_handler(CommandHandler("stopdeluser", stopdeluser))
    app.add_handler(CommandHandler("delall", delall))
    app.add_handler(CommandHandler("stopdelall", stopdelall))
    app.add_handler(CommandHandler("blocknc", blocknc))
    app.add_handler(CommandHandler("stopblocknc", stopblocknc))

    # ── AI & Voice ──
    app.add_handler(CommandHandler("ai", ai))
    app.add_handler(CommandHandler("clearai", clearai))
    app.add_handler(CommandHandler("voice", voice))

    # ── Control ──
    app.add_handler(CommandHandler("delay", delay))
    app.add_handler(CommandHandler("hi", hi))

    # ── Sudo Management ──
    app.add_handler(CommandHandler("addsudo", addsudo))
    app.add_handler(CommandHandler("delsudo", delsudo))
    app.add_handler(CommandHandler("sudos", sudos))

    # ── Admin Management ──
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("checkadmin", checkadmin))

    # ── Leave ──
    app.add_handler(CommandHandler("bye", bye))

    # ── Help ──
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("start", help_cmd))

    # ── Auto-delete message handler ──
    app.add_handler(MessageHandler(filters.ALL, auto_delete_handler))

    return app

# ===========================================================
# MAIN
# ===========================================================
async def run_all_bots():
    if not TOKENS:
        print("❌ No bot tokens added!")
        return

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🌐 Flask health server started on port 9000")

    for token in TOKENS:
        try:
            app = build_app(token)
            apps.append(app)
            bots.append(app.bot)
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            print(f"🚀 Bot started: {token[:10]}...")
        except Exception as e:
            print(f"❌ Failed to start bot {token[:10]}...: {e}")

    print(f"\n🦇 BATMAN'S BOT — {len(bots)} bots running!")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"⚡ Default delay: {GLOBAL_DELAY:.3f}s")
    print(f"🤖 Gemini AI: {'✅ Enabled' if GEMINI_API_KEY else '❌ No key'}")
    print("=" * 50)
    await asyncio.Event().wait()

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(" BATMAN MERGED MULTI BOT SYSTEM")
    print("=" * 50)
    try:
        asyncio.run(run_all_bots())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
    except Exception as e:
        print(f"❌ Error: {e}")
        
