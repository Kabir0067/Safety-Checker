from telebot.types import BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from functions.utils import AsyncCheckAnalysisContract
from functions.ai_processing import AsyncAiProcessing
from telebot.async_telebot import AsyncTeleBot
from aiohttp import ClientTimeout, BasicAuth
from email.message import EmailMessage
from database.queries import *
from typing import Optional, List, Dict, Any, Tuple
from telebot import types
from pathlib import Path
from bot.bot import *
import aiosmtplib
import datetime
import aiofiles
import aiohttp
import html
import json
import os
import re
import textwrap
import time
import uuid
import logging
import hashlib
import asyncio
from sqlalchemy import select, delete
from database.connection import AsyncSessionLocal
from PIL import Image
import io


# ----------------------------------commands----------------------------------
async def set_bot_commands(bot: AsyncTeleBot) -> None:
    commands = [
        BotCommand(command="start", description="Старт / Оғоз / Start 🚀"),
        BotCommand(command="help", description="Помощь / Ёрдам / Help 🆘"),
        BotCommand(command="about", description="О боте / Дар бораи бот / About ℹ️"),
        BotCommand(command="check", description="Проверить / Санҷ / Check 📄"),
        BotCommand(command="report", description="История / Таърих / History 📝"),
        BotCommand(command="language", description="Язык / Забон / Language 🌐"),
        BotCommand(command="feedback", description="Отзыв / Фикр / Feedback 💬"),
        BotCommand(command="buttons", description="Кнопки / Тугмаҳо / Buttons 🎛️")
    ]
    await bot.set_my_commands(commands)
# ----------------------------------------------------------------------------



# -----------------------------------start------------------------------------
@bot.message_handler(commands=['start'])
async def handle_start(message: types.Message) -> None:
    user_id = str(message.chat.id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    lang = await get_lang(user_id) or 'ru'

    await add_user(user_id, username, lang)

    if lang == 'ru':
        msg = (
            f"🌟 *Добро пожаловать, {first_name}!* \n\n"
            "🤖 *Contract Safety Checker* — ваш профессиональный цифровой помощник для проверки трудовых контрактов "
            "на безопасность и возможное мошенничество в Великобритании.\n\n"
            "📂 Мы:\n"
            "• Анализируем ваши документы 📄\n"
            "• Проверяем компании через *Companies House* 🏢\n"
            "• Выявляем подозрительные или рискованные признаки ⚠️\n\n"
            "🧭 *Главное меню:*\n"
            "🔍 /check — Проверить контракт\n"
            "🌐 /language — Изменить язык интерфейса\n"
            "📘 /help — Получить инструкцию\n\n"
            "💡 *Совет:* начните с команды /check, чтобы загрузить и проанализировать ваш документ!"
        )
    
    elif lang == 'tj':
        msg = (
            f"🌟 *Хуш омадед, {first_name}!* \n\n"
            "🤖 *Contract Safety Checker* — ёрдамчии касбии шумо барои санҷиши шартномаҳои корӣ "
            "аз ҷиҳати амният ва пешгирии қаллобӣ дар Британияи Кабир мебошад.\n\n"
            "📂 Мо:\n"
            "• Ҳуҷҷатҳои шуморо таҳлил мекунем 📄\n"
            "• Ширкатҳоро тавассути *Companies House* месанҷем 🏢\n"
            "• Аломатҳои шубҳанок ё хавфнокро муайян менамоем ⚠️\n\n"
            "🧭 *Фармонҳои асосӣ:*\n"
            "🔍 /check — Санҷидани шартнома\n"
            "🌐 /language — Иваз кардани забон\n"
            "📘 /help — Дастури пурра\n\n"
            "💡 *Маслиҳат:* аз фармони /check оғоз кунед, то шартномаи худро таҳлил намоед!"
        )
    
    else:
        msg = (
            f"🌟 *Welcome, {first_name}!* \n\n"
            "🤖 *Contract Safety Checker* — your smart digital assistant for verifying employment contracts "
            "and detecting potential fraud in the United Kingdom.\n\n"
            "📂 We:\n"
            "• Analyze your documents 📄\n"
            "• Verify companies via *Companies House* 🏢\n"
            "• Detect suspicious or risky indicators ⚠️\n\n"
            "🧭 *Main Commands:*\n"
            "🔍 /check — Verify a contract\n"
            "🌐 /language — Change language\n"
            "📘 /help — Get full instructions\n\n"
            "💡 *Tip:* Start with /check to upload and analyze your document!"
        )

    await bot.send_message(message.chat.id, msg, parse_mode='Markdown')
# ----------------------------------------------------------------------------



# -----------------------------------help-------------------------------------
@bot.message_handler(commands=['help'])
async def handle_help(message: types.Message) -> None:
    user_id = str(message.chat.id)
    lang = await get_lang(user_id) or 'ru'

    if lang == 'ru':
        help_text = (
            "✨ *Справка — Contract Safety Checker*\n\n"
            "🤖 Этот бот помогает безопасно проверять трудовые контракты в Великобритании — "
            "анализируя текст, проверяя компании и оценивая уровень риска.\n\n"

            "📄 *Что бот умеет:*\n"
            "🔹 Извлекает ключевые данные из документа (компания, номер, адрес, даты, ответственные лица)\n"
            "🔹 Проверяет компанию через *Companies House* 🏛️\n"
            "🔹 Выполняет интеллектуальный анализ текста и вычисляет рейтинг безопасности 🛡️\n"
            "🔹 Создаёт историю ваших проверок и позволяет вернуться к ним\n"
            "🔹 Принимает документы разных форматов: .PDF, .DOCX, .XLSX, .CSV, .JPG, .PNG, .TXT\n\n"

            "🗂️ *Команды:*\n"
            "🔸 /start — Обзор функций и приветствие\n"
            "🔸 /check — Отправьте файл или текст для анализа контракта\n"
            "🔸 /report — Посмотреть историю проверок и подробные отчёты\n"
            "🔸 /language — Сменить язык интерфейса (RU/TJ/EN)\n"
            "🔸 /about — Информация о принципах работы и технологиях\n"
            "🔸 /feedback — Сообщить об ошибке, предложении или оставить отзыв\n\n"

            "⚙️ *Как работает анализ:*\n"
            "1️⃣ Из документа извлекаются основные данные с помощью ИИ \n"
            "2️⃣ Проверяются данные в *Companies House* и локальной базе\n"
            "3️⃣ Оцениваются риск-факторы (подозрительные фразы, стиль текста, достоверность данных)\n"
            "4️⃣ Итог: ✅ Безопасно | ⚠️ Нужна проверка | 🚨 Рисковано\n\n"

            "📦 *Технические особенности:*\n"
            "• OCR-распознавание для изображений (EasyOCR, OpenCV)\n"
            "• Поддержка до 10 MB на файл\n"
            "• Поддержка .pdf, .docx, .xls/.xlsx, .csv, .jpg/.jpeg/.png/.bmp/.tiff/.webp, .txt\n"
            "• Хранение истории в PostgreSQL\n"
            "• Безопасное хранение данных пользователей\n\n"

            "💬 *Советы:*\n"
            "• Текстовые документы (.PDF/.DOCX) обрабатываются быстрее и точней, чем изображения\n"
            "• Если компания не найдена, проверьте правильность названия или номера\n"
            "• При желании можно сменить язык через /language\n\n"

            "🚀 Начните с /check, чтобы загрузить контракт и получить отчёт!"
        )

    elif lang == 'tj':
        help_text = (
            "✨ *Қисмати ёрӣ — Contract Safety Checker*\n\n"
            "🤖 Ин бот барои санҷидани шартномаҳои меҳнатӣ дар Британияи Кабир кӯмак мекунад — "
            "матнро таҳлил мекунад, ширкатро месанҷад ва сатҳи хавфро муайян месозад.\n\n"

            "📄 *Имкониятҳои бот:*\n"
            "🔹 Маълумоти асосиро аз ҳуҷҷат мебарорад (номи ширкат, рақам, суроға, сана, шахси масъул)\n"
            "🔹 Маълумотро тавассути *Companies House* 🏛️ месанҷад\n"
            "🔹 Бо истифодаи зеҳни сунъӣ (AI) хавфро баҳогузорӣ мекунад 🛡️\n"
            "🔹 Таърихи санҷишҳоро нигоҳ медорад\n"
            "🔹 Файлҳои гуногунро қабул мекунад: .PDF, .DOCX, .XLSX, .CSV, .JPG, .PNG, .TXT\n\n"

            "🗂️ *Фармонҳои асосӣ:*\n"
            "🔸 /start — Оғоз ва тавзеҳи умумӣ\n"
            "🔸 /check — Файл ё матнро бор кунед барои таҳлил\n"
            "🔸 /report — Дидани таърихи санҷишҳо ва ҳисоботҳои муфассал\n"
            "🔸 /language — Иваз кардани забони интерфейс (RU/TJ/EN)\n"
            "🔸 /about — Маълумоти бештар дар бораи бот ва технологияи он\n"
            "🔸 /feedback — Ирсоли назар, пешниҳод ё гузориши мушкилот\n\n"

            "⚙️ *Чӣ тавр таҳлил мешавад:*\n"
            "1️⃣ AI маълумоти муҳимро аз шартнома мегирад\n"
            "2️⃣ Маълумоти ширкат бо Companies House месанҷад\n"
            "3️⃣ Матн барои ибораҳои шубҳанок ва далелҳои ноқис таҳлил мешавад\n"
            "4️⃣ Натиҷа: ✅ Бехатар | ⚠️ Бо эҳтиёт | 🚨 Хатарнок\n\n"

            "📦 *Маълумоти техникӣ:*\n"
            "• OCR барои тасвирҳо (EasyOCR, OpenCV)\n"
            "• Андозаи максималии файл — 10 MB\n"
            "• Форматҳои дастгиришаванда: .pdf, .docx, .xls/.xlsx, .csv, .jpg/.png/.bmp/.tiff/.webp, .txt\n"
            "• Маълумоти корбар боэътимод нигоҳ дошта мешавад\n\n"

            "💬 *Маслиҳатҳо:*\n"
            "• Файлҳои матнӣ зудтар ва дақиқтар коркард мешаванд\n"
            "• Агар ширкат ёфт нашавад — номи онро бодиққат санҷед\n"
            "• Барои иваз кардани забон фармони /language-ро истифода баред\n\n"

            "🚀 Аз /check оғоз кунед, то шартномаи худро таҳлил кунед ва ҳисобот гиред!"
        )

    else:
        help_text = (
            "✨ *Help — Contract Safety Checker*\n\n"
            "🤖 This bot helps verify employment contracts in the UK — "
            "analyzing text, checking company records, and assessing risk level.\n\n"

            "📄 *Bot Capabilities:*\n"
            "🔹 Extracts key information (company name, number, address, contact details, dates)\n"
            "🔹 Verifies company data via *Companies House* 🏛️\n"
            "🔹 Uses AI (Gemini API) to score safety and detect red flags 🛡️\n"
            "🔹 Stores your check history for later reference\n"
            "🔹 Accepts multiple file formats: .PDF, .DOCX, .XLSX, .CSV, .JPG, .PNG, .TXT\n\n"

            "🗂️ *Main Commands:*\n"
            "🔸 /start — Introduction and overview\n"
            "🔸 /check — Upload a contract file or paste text for analysis\n"
            "🔸 /report — View your check history and detailed results\n"
            "🔸 /language — Switch interface language (EN/RU/TJ)\n"
            "🔸 /about — Learn about bot technology and safety model\n"
            "🔸 /feedback — Send feedback or report an issue\n\n"

            "⚙️ *How Analysis Works:*\n"
            "1️⃣ AI extracts structured data from your document\n"
            "2️⃣ The company is verified through Companies House\n"
            "3️⃣ Risk is assessed based on style, data validity, and suspicious wording\n"
            "4️⃣ Result: ✅ SAFE | ⚠️ WARNING | 🚨 RISKY\n\n"

            "📦 *Technical Info:*\n"
            "• OCR for image files (EasyOCR, OpenCV)\n"
            "• Max file size: 10 MB\n"
            "• Supported formats: .pdf, .docx, .xls/.xlsx, .csv, .jpg/.jpeg/.png/.bmp/.tiff/.webp, .txt\n"
            "• Secure data handling — PostgreSQL backend\n\n"

            "💬 *Tips:*\n"
            "• Text-based files (.PDF/.DOCX) process faster than images\n"
            "• If no company found, check spelling or registration number\n"
            "• You can change language anytime with /language\n\n"

            "🚀 Start with /check to upload your contract and get a report!"
        )

    await bot.send_message(user_id, help_text, parse_mode='Markdown')
# ----------------------------------------------------------------------------



# -----------------------------------about------------------------------------
@bot.message_handler(commands=['about'])
async def handle_about(message: types.Message) -> None:
    user_id = str(message.chat.id)
    lang = await get_lang(user_id) or 'ru'

    if lang == 'ru':
        about_text = (
            "✨ *О нас — Contract Safety Checker*\n\n"
            "🤖 *Contract Safety Checker* — ваш надёжный цифровой партнёр для проверки трудовых контрактов "
            "и выявления возможных рисков в Великобритании.\n\n"
            "🎯 Наша цель — обеспечить вашу уверенность и безопасность при работе с трудовыми документами.\n\n"
            "⚙️ *Основные возможности:*\n"
            "🔹 Поддержка форматов: `.PDF`, `.DOCX`, `.CSV`, `.JPG`, `.PNG`\n"
            "🔹 Возможность вставить текст контракта напрямую в чат 💬\n"
            "🔹 AI-анализ: извлечение ключевых данных, поиск подозрительных фраз и анализ структуры 🤖\n"
            "🔹 Проверка компании через *Companies House* — статус, адрес и достоверность 🏢\n"
            "🔹 Балльная система оценки: ✅ Безопасно | ⚠️ Требует внимания | 🚨 Рисковано\n"
            "🔹 История проверок доступна через /report 🗂️\n\n"
            "💡 *Совет:* текстовые файлы (.PDF, .DOCX) анализируются быстрее, чем изображения (.JPG, .PNG), "
            "так как для них не требуется OCR-распознавание.\n\n"
            "🛡️ Бот использует локальную базу данных для высокой скорости и надёжности без зависимости от внешних API.\n\n"
            "🚀 *Готовы начать?* Используйте /check, чтобы загрузить свой первый контракт!"
        )

    elif lang == 'tj':
        about_text = (
            "✨ *Дар бораи мо — Contract Safety Checker*\n\n"
            "🤖 *Contract Safety Checker* — ёрдамчии боэътимод ва рақамии шумо барои санҷиши шартномаҳои корӣ "
            "ва ошкор кардани хавфҳо дар Британияи Кабир мебошад.\n\n"
            "🎯 Мақсади мо — таъмини амният ва итминони шумо ҳангоми имзои шартномаҳои меҳнатӣ.\n\n"
            "⚙️ *Имкониятҳои асосӣ:*\n"
            "🔹 Дастгирии форматҳо: `.PDF`, `.DOCX`, `.CSV`, `.JPG`, `.PNG`\n"
            "🔹 Метавонед матни шартномаро мустақим дар чат ворид кунед 💬\n"
            "🔹 Таҳлили AI — ҷудо кардани маълумоти муҳим, муайян кардани ибораҳои шубҳанок ва таҳлили сохтор 🤖\n"
            "🔹 Санҷиш тавассути *Companies House* — ҳолат, суроға ва эътибори ширкат 🏢\n"
            "🔹 Системаи баҳогузорӣ: ✅ Бехатар | ⚠️ Бо эҳтиёт | 🚨 Хатарнок\n"
            "🔹 Таърихи санҷишҳо тавассути /report дастрас аст 🗂️\n\n"
            "💡 *Маслиҳат:* файлҳои матнӣ (.PDF, .DOCX) тезтар коркард мешаванд — барои тасвирҳо OCR лозим аст.\n\n"
            "🛡️ Бот пойгоҳи додаи маҳаллиро истифода мебарад, то зуд ва устувор фаъолият кунад.\n\n"
            "🚀 *Омодаед?* Аз /check оғоз намоед ва шартномаи худро таҳлил кунед!"
        )

    else:
        about_text = (
            "✨ *About — Contract Safety Checker*\n\n"
            "🤖 *Contract Safety Checker* — your trusted digital partner for employment contract verification "
            "and fraud detection in the United Kingdom.\n\n"
            "🎯 Our mission is to ensure your safety and confidence when handling professional documents.\n\n"
            "⚙️ *Key Features:*\n"
            "🔹 Supports file formats: `.PDF`, `.DOCX`, `.CSV`, `.JPG`, `.PNG`\n"
            "🔹 Paste contract text directly into the chat 💬\n"
            "🔹 AI-powered analysis — extracts key data, identifies suspicious wording, and evaluates structure 🤖\n"
            "🔹 Company verification via *Companies House* — validates status, address, and authenticity 🏢\n"
            "🔹 Risk Scoring System: ✅ Safe | ⚠️ Needs Attention | 🚨 Risky\n"
            "🔹 Access your check history with /report 🗂️\n\n"
            "💡 *Tip:* text-based files (.PDF, .DOCX) process faster; images require OCR.\n\n"
            "🛡️ The bot uses a local database for high speed and reliability, minimizing dependence on external APIs.\n\n"
            "🚀 *Ready to begin?* Use /check to start your first verification!"
        )

    await bot.send_message(user_id, about_text, parse_mode='Markdown')
# ----------------------------------------------------------------------------



# -----------------------------------language---------------------------------
def get_lang_keyboard_inline() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang_tj"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    )
    return kb

async def after_language_start(user_id: int, first_name: Optional[str]) -> None:
    lang = await get_lang(str(user_id))

    if lang == 'ru':
        msg = (
            f"👋 *Привет, {first_name or 'друг'}!* \n\n"
            "Добро пожаловать в *Contract Safety Checker*.\n"
            "Используйте команду /help, чтобы узнать, как безопасно проверять ваши контракты. 🔒"
        )

    elif lang == 'tj':
        msg = (
            f"👋 *Салом, {first_name or 'дӯст'}!* \n\n"
            "Хуш омадед ба *Contract Safety Checker*.\n"
            "Барои шиносоӣ бо тарзи санҷиши шартномаҳо фармони /help -ро истифода баред. 🔒"
        )

    else:
        msg = (
            f"👋 *Hello, {first_name or 'friend'}!* \n\n"
            "Welcome to *Contract Safety Checker*.\n"
            "Use /help to learn how to safely verify your contracts. 🔒"
        )

    await bot.send_message(user_id, msg, reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")

@bot.message_handler(commands=['language'])
async def handle_language(message: types.Message) -> None:
    lang = await get_lang(str(message.chat.id)) or 'ru'

    if lang == 'ru':
        prompt = "🌐 Пожалуйста, выберите язык интерфейса:"
    elif lang == 'tj':
        prompt = "🌐 Лутфан забони интерфейсро интихоб кунед:"
    else:
        prompt = "🌐 Please select your language:"

    await bot.send_message(message.chat.id, prompt, reply_markup=get_lang_keyboard_inline())

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("lang_"))
async def callback_set_language(call: types.CallbackQuery) -> None:
    data = call.data  
    user_id = str(call.from_user.id)

    if data == "lang_ru":
        lang_code = 'ru'
        confirm = "✅ Язык успешно установлен: *Русский* 🇷🇺"
    elif data == "lang_tj":
        lang_code = 'tj'
        confirm = "✅ Забон муваффақона танзим шуд: *Тоҷикӣ* 🇹🇯"
    else:
        lang_code = 'en'
        confirm = "✅ Language successfully set: *English* 🇬🇧"

    await change_language(user_id, lang_code)

    try:
        await bot.answer_callback_query(call.id)
    except Exception:
        pass

    try:
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    await bot.send_message(call.message.chat.id, confirm, parse_mode="Markdown")
    await after_language_start(call.message.chat.id, call.from_user.first_name)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text and (
    m.text.strip() in ["🇷🇺 Русский", "🇹🇯 Тоҷикӣ", "🇬🇧 English"] or
    m.text.strip().lower() in ["русский", "тоҷикӣ", "english", "ru", "tj", "en"]
))
async def set_user_language_text(message: types.Message) -> None:
    user_id = str(message.chat.id)
    normalized = message.text.strip().lower()

    if "рус" in normalized or "🇷🇺" in message.text:
        lang_code = 'ru'
    elif "тоҷ" in normalized or "🇹🇯" in message.text:
        lang_code = 'tj'
    else:
        lang_code = 'en'

    await change_language(user_id, lang_code)

    if lang_code == 'ru':
        confirm = "✅ Язык успешно установлен: *Русский* 🇷🇺"
    elif lang_code == 'tj':
        confirm = "✅ Забон муваффақона танзим шуд: *Тоҷикӣ* 🇹🇯"
    else:
        confirm = "✅ Language successfully set: *English* 🇬🇧"

    await bot.send_message(message.chat.id, confirm, parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())
    await after_language_start(message.chat.id, message.from_user.first_name)
# ----------------------------------------------------------------------------



# -----------------------------------feedback---------------------------------
@bot.message_handler(commands=['feedback'])
async def handle_feedback(message: types.Message) -> None:
    user_id = str(message.chat.id)
    pending_feedback.add(user_id)
    lang = await get_lang(user_id) or 'ru'

    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("❌ Отменить / Cancel")

    if lang == 'ru':
        msg = (
            "📝 *Мы ценим ваш отзыв.*\n\n"
            "Пожалуйста, опишите проблему или предложите улучшение — это поможет сделать бота лучше.\n\n"
            "Нажмите *❌ Отменить / Cancel* чтобы прервать операцию."
        )
    elif lang == 'tj':
        msg = (
            "📝 *Мо ба фикри шумо арзиш медиҳем.*\n\n"
            "Лутфан мушкилот ё пешниҳодҳои худро нависед — ин ба беҳтар кардани бот кӯмак мекунад.\n\n"
            "Барои бекор кардан тугмаи *❌ Отменить / Cancel*-ро пахш кунед."
        )
    else:  
        msg = (
            "📝 *We value your feedback.*\n\n"
            "Please describe the issue or suggest an improvement — this will help us improve the bot.\n\n"
            "Press *❌ Отменить / Cancel* to cancel the operation."
        )

    await bot.send_message(user_id, msg, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(func=lambda m: str(m.chat.id) in pending_feedback)
async def receive_feedback(message: types.Message) -> None:
    user_id = str(message.chat.id)
    text = (message.text or "").strip()
    lang = await get_lang(user_id) or 'ru'

    cancel_variants = {
        "❌ Отменить / Cancel",
        "❌ Отменить", "Отменить", "отменить",
        "Cancel", "cancel",
        "Бекор кардан", "бекор кардан", "Бекор"
    }

    if text in cancel_variants:
        pending_feedback.discard(user_id)
        if lang == 'ru':
            cancel_msg = "❌ *Отменено.* Ваш отзыв не был отправлен."
        elif lang == 'tj':
            cancel_msg = "❌ *Бекор шуд.* Фикри шумо фиристода нашуд."
        else:
            cancel_msg = "❌ *Cancelled.* Your feedback was not sent."

        await bot.send_message(user_id, cancel_msg, reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        return

    email_msg = EmailMessage()
    email_msg["From"] = os.getenv("SMTP_USER")
    email_msg["To"] = os.getenv("FEEDBACK_EMAIL")
    email_msg["Subject"] = f"Feedback from {user_id} ({lang}) - {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    email_body = (
        f"User ID: {user_id}\n"
        f"Username: {message.from_user.username or 'N/A'}\n"
        f"First Name: {message.from_user.first_name or 'N/A'}\n"
        f"Language: {lang}\n\n"
        f"Feedback:\n{text}\n\n"
        f"Time (UTC): {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    email_msg.set_content(email_body)

    try:
        await aiosmtplib.send(
            email_msg,
            hostname=os.getenv("SMTP_HOST"),
            port=int(os.getenv("SMTP_PORT", 587)),
            start_tls=True,
            username=os.getenv("SMTP_USER"),
            password=os.getenv("SMTP_PASSWORD")
        )

        if lang == 'ru':
            success_msg = "✅ *Спасибо!* Ваш отзыв успешно отправлен. Мы свяжемся при необходимости."
        elif lang == 'tj':
            success_msg = "✅ *Ташаккур!* Фикри шумо бо муваффақият ирсол гардид. Мо дар ҳолати зарурӣ бо шумо тамос мегирем."
        else:
            success_msg = "✅ *Thank you!* Your feedback has been sent successfully. We will contact you if needed."

        await bot.send_message(user_id, success_msg, reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')

    except Exception as e:
        if lang == 'ru':
            error_msg = "❌ *Ошибка:* не удалось отправить отзыв. Попробуйте позже."
        elif lang == 'tj':
            error_msg = "❌ *Хато:* фиристодани фикр муваффақ нашуд. Баъдтар такрор кунед."
        else:
            error_msg = "❌ *Error:* failed to send feedback. Please try again later."

        await bot.send_message(user_id, error_msg, reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')

    pending_feedback.discard(user_id)
# ----------------------------------------------------------------------------




# -----------------------------------check------------------------------------
def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("❌ Отменить / Cancel"))
    return markup

def cancel_check(user_id: str) -> None:
    if user_id in user_state and user_state[user_id].get('mode') == 'check_waiting':
        del user_state[user_id]

def is_check_active(user_id: str) -> bool:
    st = user_state.get(user_id)
    if not st or st.get('mode') != 'check_waiting':
        return False
    started_at = st.get('started_at')
    if not isinstance(started_at, datetime.datetime):
        return False
    if (datetime.datetime.now(UTC) - started_at).total_seconds() > CHECK_TIMEOUT_SECONDS:
        try:
            del user_state[user_id]
        except KeyError:
            pass
        return False
    return True


def _extract_text_payload(payload: Any) -> Tuple[Optional[str], Optional[str]]:
    if isinstance(payload, dict):
        if payload.get("status") == "error":
            err = payload.get("text") or payload.get("error") or "Conversion failed"
            return None, str(err)
        text_value = payload.get("text")
    else:
        text_value = payload

    normalized = str(text_value or "").replace('\r\n', '\n').replace('\r', '\n').strip()
    if not normalized:
        return None, "No readable text extracted"
    return normalized, None


def _normalize_input_format(file_type: Optional[str]) -> str:
    value = str(file_type or "text").strip().lower()
    if value.startswith('.'):
        value = value[1:]
    return value or "text"


def _normalize_status_category(status_raw: Any) -> str:
    value = str(status_raw or "").strip().lower()
    if any(k in value for k in ["unsafe", "risk", "риск", "подоз", "хатар"]):
        return "unsafe"
    if any(k in value for k in ["warn", "attention", "треб", "эҳтиёт", "огоҳ"]):
        return "warning"
    if any(k in value for k in ["safe", "безопас", "бехатар", "бовар"]):
        return "safe"
    return "unknown"


def _summary_value(value: Any, max_len: int = 110) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return "—"

    markers = ["employment agreement", "whereas", "position and duties", "term and termination"]
    lowered = text.lower()
    if len(text) > max_len or sum(1 for marker in markers if marker in lowered) >= 2:
        return "—"
    return html.escape(text)


def _build_pretty_summary(
    lang: str,
    file_type: str,
    total_score: int,
    status_raw: str,
    ai_result: Dict[str, Any],
) -> str:
    labels = {
        'ru': {
            'format': "📄 <b>Формат:</b>",
            'score': "⭐️ <b>Общий балл:</b>",
            'status': "🛡️ <b>Статус:</b>",
            'company': "🏢 <b>Компания:</b>",
            'company_number': "📇 <b>Номер компании:</b>",
            'domain': "🌐 <b>Домен:</b>",
        },
        'tj': {
            'format': "📄 <b>Формат:</b>",
            'score': "⭐️ <b>Холи умумӣ:</b>",
            'status': "🛡️ <b>Ҳолат:</b>",
            'company': "🏢 <b>Ширкат:</b>",
            'company_number': "📇 <b>Рақами ширкат:</b>",
            'domain': "🌐 <b>Домен:</b>",
        },
        'en': {
            'format': "📄 <b>Format:</b>",
            'score': "⭐️ <b>Total score:</b>",
            'status': "🛡️ <b>Status:</b>",
            'company': "🏢 <b>Company:</b>",
            'company_number': "📇 <b>Company number:</b>",
            'domain': "🌐 <b>Domain:</b>",
        },
    }

    status_icons = {'safe': "🟢", 'warning': "🟠", 'unsafe': "🔴", 'unknown': "⚪"}
    status_text = {'safe': "Safe", 'warning': "Warning", 'unsafe': "Unsafe", 'unknown': "Unknown"}

    L = labels.get(lang, labels['en'])
    category = _normalize_status_category(status_raw)
    icon = status_icons.get(category, status_icons['unknown'])
    status_label = status_text.get(category, status_text['unknown'])

    lines = [
        f"{L['format']} <code>{html.escape(_normalize_input_format(file_type))}</code>",
        f"{L['score']} <b>{max(0, min(100, int(total_score or 0)))}</b>",
        f"{L['status']} {icon} <b>{status_label}</b>",
        "",
        f"{L['company']} <code>{_summary_value(ai_result.get('Company Name'))}</code>",
        f"{L['company_number']} <code>{_summary_value(ai_result.get('Company Number'), max_len=30)}</code>",
        f"{L['domain']} <code>{_summary_value(ai_result.get('Website Domain'), max_len=80)}</code>",
    ]
    return "\n".join(lines)

async def process_file(file: types.Document):
    file_path = os.path.join(FILES_DIR, file.file_name)
    try:
        file_info = await bot.get_file(file.file_id)
        if file_info.file_size > MAX_SIZE_BYTES:
            return None, None, {"error": "File is too large (max 10 MB)"}
        file_data = await bot.download_file(file_info.file_path)
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)
    except Exception as e:
        return None, file_path if os.path.exists(file_path) else None, {"error": f"Download/write error: {str(e)}"}
    
    file_meta = await converter.get_file_format(file_path)  
    if isinstance(file_meta, dict) and file_meta.get("error"):
        return None, file_path, file_meta
    
    ext = file_meta.get("extension")
    
    text = await converter.convert_to_text(file_path)  
    if isinstance(text, dict) and text.get("status") == "error":
        error_msg = text.get("text", "Conversion failed")
        return None, file_path, {"error": error_msg}
    elif isinstance(text, str) and text.startswith("Ошибка"):
        return None, file_path, {"error": "Conversion failed"}
    
    contract_text, extraction_error = _extract_text_payload(text)
    if extraction_error:
        return None, file_path, {"error": extraction_error}

    return contract_text, file_path, ext

@bot.message_handler(commands=['check'])
async def handle_check(message: types.Message):
    user_id = str(message.chat.id)
    user_lang = await get_lang(user_id) or 'ru'
    
    # Проверка, не занят ли пользователь обработкой (BR-5 fix)
    if user_id in user_state and user_state[user_id].get('processing'):
        busy_text = {
            'ru': "⏳ Предыдущая задача на обработку ещё выполняется. Пожалуйста, дождитесь результата.",
            'tj': "⏳ Вақти коркарди кории қаблӣ ҳанӯз тамом нашудааст. Лутфан мунтазир шавед.",
            'en': "⏳ A previous processing task is still running. Please wait for it to finish."
        }
        await bot.send_message(message.chat.id, busy_text.get(user_lang, busy_text['en']))
        return
    
    cancel_check(user_id)

    intro_texts = {
        'ru': (
            "📄 *Проверка контракта*\n\n"
            "Отправьте файл для анализа (`.pdf`, `.docx`, `.xlsx`, `.csv`, `.jpeg`, `.jpg`, `.png`) "
            "или вставьте текст контракта прямо в чат.\n\n"
            "💡 *Совет:* текстовые файлы (`.pdf`, `.docx`) обрабатываются быстрее. "
            "Изображения требуют времени на OCR-распознавание.\n\n"
            "🔒 Ваши данные обрабатываются конфиденциально и безопасно.\n\n"
            "👉 Отправьте файл или вставьте текст — система начнёт анализ автоматически."
        ),
        'tj': (
            "📄 *Санҷиши шартнома*\n\n"
            "Файлро барои таҳлил фиристед (`.pdf`, `.docx`, `.xlsx`, `.csv`, `.jpeg`, `.jpg`, `.png`) "
            "ё матни шартномаро мустақим дар чат ҷойгир кунед.\n\n"
            "💡 *Маслиҳат:* файлҳои матнӣ (`.pdf`, `.docx`) зудтар коркард мешаванд. "
            "Аксҳо ба OCR ниёз доранд ва вақти бештар мегиранд.\n\n"
            "🔒 Маълумоти шумо махфӣ ва боэътимод коркард мешавад.\n\n"
            "👉 Файл ё матнро фиристед — система ба таври автоматӣ таҳлилро оғоз мекунад."
        ),
        'en': (
            "📄 *Contract Check*\n\n"
            "Send a file for analysis (`.pdf`, `.docx`, `.xlsx`, `.csv`, `.jpeg`, `.jpg`, `.png`) "
            "or paste the contract text directly into the chat.\n\n"
            "💡 *Tip:* text files (`.pdf`, `.docx`) are processed faster. Images require OCR recognition and take longer.\n\n"
            "🔒 Your data is processed confidentially and securely.\n\n"
            "👉 Send a file or paste the text — the system will start analysis automatically."
        )
    }

    user_state[user_id] = {
        'mode': 'check_waiting',
        'started_at': datetime.datetime.now(UTC),
        'processing': False
    }

    await bot.send_message(
        message.chat.id,
        intro_texts.get(user_lang, intro_texts['en']),
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )

@bot.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    user_id = str(message.chat.id)
    user_lang = await get_lang(user_id) or 'ru'

    if message.caption and message.caption.strip() in CANCEL_VARIANTS:
        cancel_check(user_id)
        await bot.send_message(message.chat.id, reply_markup=ReplyKeyboardRemove())
        return

    if not is_check_active(user_id):
        return

    if user_state[user_id].get('processing'):
        busy_text = {
            'ru': "⏳ Обработка ранее отправленного файла ещё в процессе. Пожалуйста, подождите.",
            'tj': "⏳ Коркарди файли қаблӣ ҳанӯз идома дорад. Лутфан каме сабр кунед.",
            'en': "⏳ A previously uploaded file is still being processed. Please wait a moment."
        }
        await bot.send_message(message.chat.id, busy_text.get(user_lang, busy_text['en']))
        return

    user_state[user_id]['processing'] = True
    wait_texts = {
        'ru': "⏳ Изображение обрабатывается (OCR)...",
        'tj': "⏳ Акс коркард мешавад (OCR)...",
        'en': "⏳ Processing image (OCR)..."
    }
    await bot.send_message(message.chat.id, wait_texts.get(user_lang, wait_texts['en']), reply_markup=ReplyKeyboardRemove())
    png_path: Optional[str] = None
    try:
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        
        if file.file_size > MAX_SIZE_BYTES:
            await bot.send_message(message.chat.id, 
                f"❌ Акс хеле калон аст — ҳадди аксар {MAX_SIZE_BYTES // (1024*1024)} MB.",
                parse_mode='Markdown')
            cancel_check(user_id)
            return

        file_data = await bot.download_file(file.file_path)

        png_path = os.path.join(FILES_DIR, f"{user_id}_temp_image.png")
        try:
            img = Image.open(io.BytesIO(file_data))
            img = img.convert("RGB")  
            img.save(png_path, "PNG")
        except Exception as e:
            await bot.send_message(message.chat.id, f"❌ Хатогӣ дар табдилдиҳӣ: {str(e)}")
            cancel_check(user_id)
            return

        text = await converter.convert_to_text(png_path)
        if isinstance(text, dict) and text.get("status") == "error":
            error_msg = text.get("text", "OCR failed")
            await bot.send_message(message.chat.id, f"❌ {error_msg}")
            if os.path.exists(png_path):
                os.remove(png_path)
            cancel_check(user_id)
            return
        elif isinstance(text, str) and text.startswith("Ошибка"):
            await bot.send_message(message.chat.id, "❌ OCR нашуд. Матн аз акс хонда нашуд.")
            if os.path.exists(png_path):
                os.remove(png_path)
            cancel_check(user_id)
            return

        contract_text, extraction_error = _extract_text_payload(text)
        if extraction_error:
            await bot.send_message(message.chat.id, "❌ OCR returned empty text. Please try a clearer image.")
            if os.path.exists(png_path):
                os.remove(png_path)
            cancel_check(user_id)
            return

        await process_contract_text(message, contract_text, file_path=png_path, file_type="png")
    except Exception as e:
        print(f"handle_photo fatal error: {e}")
        fallback_texts = {
            'ru': "\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438 \u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0435 \u0440\u0430\u0437.",
            'tj': "\u274c Xatoi korkardi aks. Lutfan boz kushish kuned.",
            'en': "\u274c Image processing error. Please try again.",
        }
        await bot.send_message(message.chat.id, fallback_texts.get(user_lang, fallback_texts['en']))
        if png_path and os.path.exists(png_path):
            try:
                os.remove(png_path)
            except Exception:
                pass
        cancel_check(user_id)

@bot.message_handler(content_types=['document'])
async def handle_document(message: types.Message):
    user_id = str(message.chat.id)
    user_lang = await get_lang(user_id) or 'ru'

    if message.caption and message.caption.strip() in CANCEL_VARIANTS:
        cancel_check(user_id)
        await bot.send_message(message.chat.id, reply_markup=ReplyKeyboardRemove())
        return

    if not is_check_active(user_id):
        return

    file_name = getattr(message.document, 'file_name', '') or ''
    mime_type = getattr(message.document, 'mime_type', '') or ''
    file_size = getattr(message.document, 'file_size', 0) or 0

    is_image = mime_type.startswith('image/') or Path(file_name).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

    if file_size > MAX_SIZE_BYTES:
        await bot.send_message(message.chat.id, 
            f"❌ Файл хеле калон — ҳадди аксар {MAX_SIZE_BYTES // (1024*1024)} MB.",
            parse_mode='Markdown')
        cancel_check(user_id)
        return

    if user_state[user_id].get('processing'):
        busy_text = {
            'ru': "⏳ Предыдущая задача ещё обрабатывается. Пожалуйста, подождите.",
            'tj': "⏳ Дархости қаблӣ ҳоло ҳам коркард мешавад. Лутфан интизор шавед.",
            'en': "⏳ A previous task is still being processed. Please wait.",
        }
        await bot.send_message(message.chat.id, busy_text.get(user_lang, busy_text['en']))
        return

    user_state[user_id]['processing'] = True
    wait_texts = {
        'ru': "⏳ Файл обрабатывается...",
        'tj': "⏳ Файл коркард мешавад...",
        'en': "⏳ File is being processed..."
    }
    await bot.send_message(message.chat.id, wait_texts.get(user_lang, wait_texts['en']), reply_markup=ReplyKeyboardRemove())
    temp_path: Optional[str] = None
    final_path: Optional[str] = None
    try:
        file_info = await bot.get_file(message.document.file_id)
        file_data = await bot.download_file(file_info.file_path)
        temp_path = os.path.join(FILES_DIR, f"{user_id}_doc_temp{Path(file_name).suffix}")
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(file_data)

        final_path = temp_path
        final_ext = "png" if is_image else Path(file_name).suffix.lower()

        if is_image:
            try:
                img = Image.open(temp_path)
                final_path = os.path.join(FILES_DIR, f"{user_id}_converted.png")
                img.convert("RGB").save(final_path, "PNG")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                await bot.send_message(message.chat.id, f"❌ Хатогӣ дар табдил: {e}")
                cancel_check(user_id)
                return

        if final_ext not in FORMATS and not is_image:
            await bot.send_message(message.chat.id, "❌ Формат дастгирӣ намешавад.")
            cancel_check(user_id)
            return

        text = await converter.convert_to_text(final_path)
        if isinstance(text, dict) and text.get("status") == "error":
            error_msg = text.get("text", "Conversion failed")
            await bot.send_message(message.chat.id, f"❌ {error_msg}")
            if os.path.exists(final_path):
                os.remove(final_path)
            cancel_check(user_id)
            return
        elif isinstance(text, str) and text.startswith("Ошибка"):
            await bot.send_message(message.chat.id, "❌ Матн хонда нашуд.")
            if os.path.exists(final_path):
                os.remove(final_path)
            cancel_check(user_id)
            return

        contract_text, extraction_error = _extract_text_payload(text)
        if extraction_error:
            await bot.send_message(message.chat.id, "❌ Unable to extract readable text from file.")
            if os.path.exists(final_path):
                os.remove(final_path)
            cancel_check(user_id)
            return

        await process_contract_text(message, contract_text, file_path=final_path, file_type=final_ext)
    except Exception as e:
        print(f"handle_document fatal error: {e}")
        fallback_texts = {
            'ru': "\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438 \u0444\u0430\u0439\u043b\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0435 \u0440\u0430\u0437.",
            'tj': "\u274c Xatoi korkardi fayl. Lutfan boz kushish kuned.",
            'en': "\u274c File processing error. Please try again.",
        }
        await bot.send_message(message.chat.id, fallback_texts.get(user_lang, fallback_texts['en']))
        for path in [temp_path, final_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        cancel_check(user_id)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text.strip() != '' and not m.text.startswith('/')
                  and is_check_active(str(m.chat.id)),content_types=['text'])

async def handle_text_input(message: types.Message):
    user_id = str(message.chat.id)
    text = message.text.strip()
    user_lang = await get_lang(user_id) or 'ru'

    if text in CANCEL_VARIANTS:
        cancel_check(user_id)
        cancel_msg = {
            'ru': "*Отменено.* Проверка остановлена.",
            'tj': "*Бекор шуд.* Санҷиш қатъ шуд.",
            'en': "*Cancelled.* Check stopped."
        }
        await bot.send_message(
            message.chat.id,
            cancel_msg.get(user_lang, cancel_msg['en']),
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return

    if not is_check_active(user_id):
        return

    if user_state[user_id].get('processing'):
        busy_text = {
            'ru': "⏳ Предыдущая задача на обработку ещё выполняется. Пожалуйста, дождитесь результата.",
            'tj': "⏳ Вақти коркарди кории қаблӣ ҳанӯз тамом нашудааст. Лутфан мунтазир шавед.",
            'en': "⏳ A previous processing task is still running. Please wait for it to finish."
        }
        await bot.send_message(message.chat.id, busy_text.get(user_lang, busy_text['en']))
        return

    user_state[user_id]['processing'] = True

    wait_texts = {
        'ru': "⏳ Текст обрабатывается. Пожалуйста, подождите.",
        'tj': "⏳ Матн коркард шуда истодааст. Лутфан интизор шавед.",
        'en': "⏳ Text is being processed. Please wait."
    }
    await bot.send_message(message.chat.id, wait_texts.get(user_lang, wait_texts['en']), reply_markup=ReplyKeyboardRemove())

    if len(text) < 50:
        short_texts = {
            'ru': "⚠️ Пожалуйста, введите полный текст контракта (больше 50 символов) или загрузите файл.",
            'tj': "⚠️ Лутфан матни пурраи шартномаро (зиёд аз 50 аломат) ворид кунед ё файл бор кунед.",
            'en': "⚠️ Please enter the full contract text (more than 50 characters) or upload a file."
        }
        await bot.send_message(message.chat.id, short_texts.get(user_lang, short_texts['en']))
        cancel_check(user_id)
        return

    await process_contract_text(message, text)

async def process_contract_text(
    message: types.Message,
    text: str,
    file_path: Optional[str] = None,
    file_type: str = 'text'
) -> None:
    user_id = str(message.chat.id)
    user_lang = await get_lang(user_id) or 'ru'

    try:
        contract_text, extraction_error = _extract_text_payload(text)
        if extraction_error:
            no_text = {
                'ru': "\u274c \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0438\u0437\u0432\u043b\u0435\u0447\u044c \u0447\u0438\u0442\u0430\u0435\u043c\u044b\u0439 \u0442\u0435\u043a\u0441\u0442.",
                'tj': "\u274c Matni khondashavanda yoft nashud.",
                'en': "\u274c Unable to extract readable text.",
            }
            await bot.send_message(message.chat.id, no_text.get(user_lang, no_text['en']))
            return

        if len(contract_text) < 50:
            short_texts = {
                'ru': "\u26a0\ufe0f \u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0442\u0435\u043a\u0441\u0442\u0430 \u0434\u043b\u044f \u0430\u043d\u0430\u043b\u0438\u0437\u0430. \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043f\u043e\u043b\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430.",
                'tj': "\u26a0\ufe0f Baroi tahlil matn kofi nest. Matni purrai shartnomaro firisted.",
                'en': "\u26a0\ufe0f Not enough text for analysis. Please send the full contract text.",
            }
            await bot.send_message(message.chat.id, short_texts.get(user_lang, short_texts['en']))
            return

        ai = AsyncAiProcessing(contract_text)
        try:
            ai_result = await asyncio.wait_for(ai.get_answer_json_dict(), timeout=70.0)
        except asyncio.TimeoutError:
            timeout_texts = {
                'ru': "\u274c \u0422\u0430\u0439\u043c\u0430\u0443\u0442 AI-\u0430\u043d\u0430\u043b\u0438\u0437\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435.",
                'tj': "\u274c Vaqti tahlili AI ba okhir rasid. Badtar kushish kuned.",
                'en': "\u274c AI analysis timed out. Please try again later.",
            }
            await bot.send_message(message.chat.id, timeout_texts.get(user_lang, timeout_texts['en']))
            return

        if not ai_result or not isinstance(ai_result, dict):
            failed_texts = {
                'ru': "\u274c \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0438\u0437\u0432\u043b\u0435\u0447\u044c \u0434\u0430\u043d\u043d\u044b\u0435 \u0438\u0437 \u0442\u0435\u043a\u0441\u0442\u0430.",
                'tj': "\u274c Malumoti lozima az matn girifta nashud.",
                'en': "\u274c Failed to extract data from text.",
            }
            await bot.send_message(message.chat.id, failed_texts.get(user_lang, failed_texts['en']))
            return

        try:
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text=contract_text) as analysis:
                detailed_report = await asyncio.wait_for(analysis.get_detailed_report(), timeout=45.0)
        except asyncio.TimeoutError:
            verify_timeout = {
                'ru': "\u274c \u0422\u0430\u0439\u043c\u0430\u0443\u0442 \u044d\u0442\u0430\u043f\u0430 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0438.",
                'tj': "\u274c Vaqti marhilai sanjishi shirkat ba okhir rasid.",
                'en': "\u274c Company verification step timed out.",
            }
            await bot.send_message(message.chat.id, verify_timeout.get(user_lang, verify_timeout['en']))
            return

        total_score = detailed_report.get("total_score", 0)
        status = detailed_report.get("status", "unknown")

        try:
            user_row = await get_user_by_telegram_id(user_id)
            user_db_id = user_row.get('id') if user_row else None
        except Exception:
            user_db_id = None

        company_id = None
        try:
            company_name = ai_result.get('Company Name')
            if company_name:
                payload = {
                    'name': company_name,
                    'company_number': ai_result.get('Company Number'),
                    'registered_address': ai_result.get('Registered Address'),
                    'status': 'unknown',
                    'score': total_score,
                    'website_domain': ai_result.get('Website Domain'),
                    'contact_email': None,
                    'phone_number': None,
                }
                company_id = await add_company(payload)
        except Exception as e:
            print(f"add_company error: {e}")

        contract_date_db = None
        try:
            raw_date = ai_result.get('Contract Date')
            if isinstance(raw_date, str) and raw_date.strip():
                normalized_raw_date = re.sub(r'(\d{1,2})(st|nd|rd|th)\b', r'\1', raw_date.strip(), flags=re.IGNORECASE)
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y.%m.%d",
                            "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%B %Y", "%b %Y"]:
                    try:
                        dt = datetime.datetime.strptime(normalized_raw_date, fmt)
                        contract_date_db = dt.date()
                        break
                    except ValueError:
                        continue
        except Exception as e:
            print(f"date parse error: {e}")

        try:
            await add_user_check({
                'user_id': user_db_id,
                'company_id': company_id,
                'contract_number': ai_result.get('Contract Number'),
                'contract_date': contract_date_db,
                'extracted_company_name': ai_result.get('Company Name'),
                'extracted_company_number': ai_result.get('Company Number'),
                'extracted_address': ai_result.get('Registered Address'),
                'website_domain': ai_result.get('Website Domain'),
                'total_score': total_score,
                'safety_rating': status,
                'detailed_scores': detailed_report.get('detailed_scores', {})
            })
        except Exception as e:
            print(f"add_user_check error: {e}")

        try:
            suspicious = (
                total_score < 50
                or (isinstance(ai_result.get('Suspicious Phrases Found'), list) and ai_result.get('Suspicious Phrases Found'))
            )
            if suspicious:
                name = ai_result.get('Company Name')
                number = ai_result.get('Company Number')
                if name or number:
                    await add_suspicious_company({
                        'company_name': name or (number and f"Company {number}"),
                        'company_number': number,
                        'evidence': json.dumps({'ai': ai_result, 'report': detailed_report}),
                        'source': 'bot_auto',
                        'status': 'active',
                        'website_domain': ai_result.get('Website Domain'),
                        'registered_address': ai_result.get('Registered Address'),
                        'contact_phone': None,
                        'contact_email': None,
                        'added_by': user_db_id
                    })
        except Exception as e:
            print(f"add_suspicious_company error: {e}")

        pretty_summary = _build_pretty_summary(
            lang=user_lang,
            file_type=file_type,
            total_score=total_score,
            status_raw=status,
            ai_result=ai_result,
        )

        await bot.send_message(
            message.chat.id,
            pretty_summary,
            parse_mode='HTML',
            disable_web_page_preview=True,
        )
    except Exception as e:
        print(f"process_contract_text fatal error: {e}")
        fail_texts = {
            'ru': "\u274c \u0421\u0438\u0441\u0442\u0435\u043c\u043d\u0430\u044f \u043e\u0448\u0438\u0431\u043a\u0430 \u0432\u043e \u0432\u0440\u0435\u043c\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438.",
            'tj': "\u274c Xatoi sistema hangomi sanjish.",
            'en': "\u274c System error during verification.",
        }
        await bot.send_message(message.chat.id, fail_texts.get(user_lang, fail_texts['en']))
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        cancel_check(user_id)
# ----------------------------------------------------------------------------




# -----------------------------------report------------------------------------
@bot.message_handler(commands=['report'])
async def handle_report(message: types.Message):
    cancel_check(str(message.chat.id))

    user_id = message.chat.id
    user_ids = str(message.chat.id)
    user_lang = await get_lang(user_ids) or 'en'

    try:
        user_row = await get_user_by_telegram_id(user_ids)
        db_user_id = user_row.get('id') if user_row else None
    except Exception:
        db_user_id = None

    checks_history = await get_user_checks_history(db_user_id or 0, limit=50)

    empty_messages = {
        'ru': (
            "📊 <b>Ваша история проверок</b>\n\n"
            "У вас пока нет завершённых проверок. Используйте команду /check, чтобы начать анализ контракта."
        ),
        'tj': (
            "📊 <b>Таҷрибаи санҷишҳои шумо</b>\n\n"
            "Шумо ҳанӯз санҷиши анҷомдодашуда надоред. Барои оғоз кардани таҳлил фармони /check -ро истифода баред."
        ),
        'en': (
            "📊 <b>Your Check History</b>\n\n"
            "You don't have any completed checks yet. Start with /check to analyze a contract."
        )
    }

    if not checks_history:
        await bot.send_message(message.chat.id, empty_messages.get(user_lang, empty_messages['en']), parse_mode='HTML')
        return

    total_pages = len(checks_history)

    user_state[user_id] = {
        'command': 'report',
        'page': 0,
        'total_pages': total_pages,
        'checks': checks_history
    }

    await show_report_page(message.chat.id, user_id, 0, user_lang)

def _localize_safety(safety_raw: str, lang: str):
    """Normalize raw safety string and return (icon, localized_label)."""
    if not safety_raw:
        safety_raw = ""
    s = str(safety_raw).lower()

    if any(k in s for k in ["safe", "безопас", "бехатар", "бовар"]):
        cat = "safe"
    elif any(k in s for k in ["warn", "треб", "эҳтиёт", "warning"]):
        cat = "warning"
    elif any(k in s for k in ["unsafe", "подоз", "хатар", "risk", "риск"]):
        cat = "unsafe"
    else:
        cat = "unknown"

    labels = {
        'ru': {
            'safe': ("🟢 🛡️", "Безопасно — надёжно"),
            'warning': ("🟡 ⚠️", "Требует внимания"),
            'unsafe': ("🔴 🚨", "Рисковано — подозрительно"),
            'unknown': ("⚪ ℹ️", "Неизвестно")
        },
        'tj': {
            'safe': ("🟢 🛡️", "Бехатар — боваринок"),
            'warning': ("🟡 ⚠️", "Ниёз ба диққат / Бо эҳтиёт"),
            'unsafe': ("🔴 🚨", "Хатарнок — шубҳанок"),
            'unknown': ("⚪ ℹ️", "Номаълум")
        },
        'en': {
            'safe': ("🟢 🛡️", "Safe — Reliable"),
            'warning': ("🟡 ⚠️", "Needs Attention"),
            'unsafe': ("🔴 🚨", "Risky — Suspicious"),
            'unknown': ("⚪ ℹ️", "Unknown")
        }
    }

    lang_map = labels.get(lang, labels['en'])
    return lang_map.get(cat, lang_map['unknown'])

def _score_bar(score: int, length: int = 10) -> str:
    if score is None:
        score = 0
    score = max(0, min(100, int(score)))
    filled = int(round((score / 100.0) * length))
    empty = length - filled
    if score >= 70:
        block = "🟩"
    elif score >= 40:
        block = "🟨"
    else:
        block = "🟥"
    return (block * filled) + ("▫️" * empty) + f"  <b>{score}/100</b>"

async def show_report_page(chat_id: int, user_id: int, page: int, lang: str):
    if user_id not in user_state or user_state[user_id].get('command') != 'report':
        return

    state = user_state[user_id]
    checks = state['checks']
    total_pages = state['total_pages']

    if page < 0 or page >= total_pages:
        return

    check = checks[page]

    check_date = check.get('created_at')
    if isinstance(check_date, datetime.datetime):
        check_date = check_date.strftime("%d.%m.%Y %H:%M")
    elif not check_date:
        check_date = "N/A"

    company_name = check.get('company_name') or check.get('extracted_company_name') or 'N/A'
    total_score = int(check.get('total_score', 0) or 0)
    safety_rating = check.get('safety_rating', 'Unknown')

    icon, localized_safety_label = _localize_safety(safety_rating, lang)

    texts = {
        'ru': {
            'title': f"{icon} <b>Детали проверки №{page+1} из {total_pages}</b>",
            'company': "🏢 <b>Компания:</b>",
            'date': "📅 <b>Дата проверки:</b>",
            'score': "⭐ <b>Итог:</b>",
            'safety': "🛡️ <b>Статус:</b>",
            'contract_number': "📄 <b>Номер договора:</b>",
            'contract_date': "📋 <b>Дата договора:</b>",
            'website': "🌐 <b>Веб-сайт:</b>",
            'detailed_scores': "<b>Детальная оценка</b>",
            'no_value': "—"
        },
        'tj': {
            'title': f"{icon} <b>Тафсилоти санҷиш №{page+1} аз {total_pages}</b>",
            'company': "🏢 <b>Ширкат:</b>",
            'date': "📅 <b>Санаи санҷиш:</b>",
            'score': "⭐ <b>Балл:</b>",
            'safety': "🛡️ <b>Ҳолат:</b>",
            'contract_number': "📄 <b>Рақами шартнома:</b>",
            'contract_date': "📋 <b>Санаи шартнома:</b>",
            'website': "🌐 <b>Веб-сайт:</b>",
            'detailed_scores': "<b>Ҳисоботи муфассал</b>",
            'no_value': "—"
        },
        'en': {
            'title': f"{icon} <b>Check Details №{page+1} of {total_pages}</b>",
            'company': "🏢 <b>Company:</b>",
            'date': "📅 <b>Check Date:</b>",
            'score': "⭐ <b>Score:</b>",
            'safety': "🛡️ <b>Safety:</b>",
            'contract_number': "📄 <b>Contract Number:</b>",
            'contract_date': "📋 <b>Contract Date:</b>",
            'website': "🌐 <b>Website:</b>",
            'detailed_scores': "<b>Detailed Scores</b>",
            'no_value': "—"
        }
    }

    L = texts.get(lang, texts['en'])

    header = [
        L['title'],
        "",
        f"{L['company']} <code>{company_name}</code>",
        f"{L['date']} {check_date}",
        f"{L['score']} {_score_bar(total_score, length=10)}",
        f"{L['safety']} {icon} <b>{localized_safety_label}</b>",
    ]

    if check.get('contract_number'):
        header.append(f"{L['contract_number']} {check.get('contract_number')}")
    if check.get('contract_date'):
        header.append(f"{L['contract_date']} {check.get('contract_date')}")
    if check.get('website_domain'):
        header.append(f"{L['website']} {check.get('website_domain')}")
    header.append("")  

    header_text = "\n".join(header)

    detailed_scores = check.get('detailed_scores', {}) or {}
    if isinstance(detailed_scores, str):
        try:
            detailed_scores = json.loads(detailed_scores)
        except Exception:
            detailed_scores = {}

    categories = [
        ('Contract Number', {'ru': '📄 Номер договора', 'tj': '📄 Рақами шартнома', 'en': '📄 Contract Number'}),
        ('Company Number', {'ru': '🏢 Номер компании', 'tj': '🏢 Рақами ширкат', 'en': '🏢 Company Number'}),
        ('Company Name', {'ru': '📛 Название компании', 'tj': '📛 Номи ширкат', 'en': '📛 Company Name'}),
        ('Registered Address', {'ru': '📍 Адрес', 'tj': '📍 Суроға', 'en': '📍 Registered Address'}),
        ('Contact Details', {'ru': '📞 Контакты', 'tj': '📞 Тамос', 'en': '📞 Contact Details'}),
        ('Suspicious Phrases', {'ru': '⚠️ Подозрительные фразы', 'tj': '⚠️ Ибораҳои шубҳанок', 'en': '⚠️ Suspicious Phrases'}),
        ('Text Style', {'ru': '📝 Стиль текста', 'tj': '📝 Услуби матн', 'en': '📝 Text Style'}),
        ('Website Domain', {'ru': '🌐 Веб-сайт', 'tj': '🌐 Веб-сайт', 'en': '🌐 Website Domain'}),
        ('Responsible Person', {'ru': '👤 Ответственное лицо', 'tj': '👤 Шахси масъул', 'en': '👤 Responsible Person'}),
        ('Contract Date', {'ru': '📅 Дата договора', 'tj': '📅 Санаи шартнома', 'en': '📅 Contract Date'})
    ]

    details_lines = [L['detailed_scores'], ""]
    for key, label_map in categories:
        display = label_map.get(lang, label_map['en'])
        value = detailed_scores.get(key, None)
        if isinstance(value, list):
            value_text = ", ".join(str(x) for x in value) if value else L['no_value']
        elif isinstance(value, bool):
            value_text = "Yes" if value else "No"
        elif value is None or value == "":
            value_text = L['no_value']
        else:
            value_text = str(value)
        presence = "✅" if value and value not in (0, "0", False) else "⚪"
        details_lines.append(f"{presence} <b>{display}:</b> <code>{value_text}</code>")

    details_text = "\n".join(details_lines)
    full_text = header_text + "\n" + details_text

    prev_label_map = {'ru': "⬅️ Пред", 'tj': "⬅️ Пешина", 'en': "⬅️ Prev"}
    next_label_map = {'ru': "След ➡️", 'tj': "Баъдӣ ➡️", 'en': "Next ➡️"}
    first_label_map = {'ru': "⏮️ Первая", 'tj': "⏮️ Аввал", 'en': "⏮️ First"}
    last_label_map = {'ru': "⏭️ Последняя", 'tj': "⏭️ Охирин", 'en': "⏭️ Last"}
    page_label = f"{page+1}/{total_pages}"

    kb = types.InlineKeyboardMarkup(row_width=5)
    buttons = []
    if page > 0:
        buttons.append(types.InlineKeyboardButton(first_label_map.get(lang), callback_data=f"report_goto_0"))
        buttons.append(types.InlineKeyboardButton(prev_label_map.get(lang), callback_data=f"report_prev_{page}"))
    buttons.append(types.InlineKeyboardButton(page_label, callback_data="report_page"))
    if page < total_pages - 1:
        buttons.append(types.InlineKeyboardButton(next_label_map.get(lang), callback_data=f"report_next_{page}"))
        buttons.append(types.InlineKeyboardButton(last_label_map.get(lang), callback_data=f"report_goto_{total_pages-1}"))

    kb.row(*buttons)

    try:
        if 'report_message_id' in user_state.get(user_id, {}):
            await bot.edit_message_text(
                full_text,
                chat_id=chat_id,
                message_id=user_state[user_id]['report_message_id'],
                parse_mode='HTML',
                reply_markup=kb,
                disable_web_page_preview=True
            )
            user_state[user_id]['page'] = page
            return
    except Exception:
        pass

    sent_message = await bot.send_message(chat_id, full_text, parse_mode='HTML', reply_markup=kb, disable_web_page_preview=True)
    user_state[user_id]['report_message_id'] = sent_message.message_id
    user_state[user_id]['page'] = page

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('report_'))
async def handle_report_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_lang = await get_lang(str(user_id)) or 'en'
    data = call.data

    def _get_index_from(data_str: str):
        try:
            return int(data_str.rsplit("_", 1)[1])
        except Exception:
            return None

    if data == "report_page":
        answers = {
            'ru': "Страница отображается",
            'tj': "Саҳифа намоиш дода шуд",
            'en': "Page displayed"
        }
        await bot.answer_callback_query(call.id, answers.get(user_lang, answers['en']))
        return

    if data.startswith("report_prev_"):
        idx = _get_index_from(data)
        if idx is not None:
            await show_report_page(call.message.chat.id, user_id, max(0, idx - 1), user_lang)
    elif data.startswith("report_next_"):
        idx = _get_index_from(data)
        if idx is not None:
            await show_report_page(call.message.chat.id, user_id, min(user_state[user_id]['total_pages'] - 1, idx + 1), user_lang)
    elif data.startswith("report_goto_"):
        idx = _get_index_from(data)
        if idx is not None:
            await show_report_page(call.message.chat.id, user_id, max(0, min(user_state[user_id]['total_pages'] - 1, idx)), user_lang)

    try:
        await bot.answer_callback_query(call.id)
    except Exception:
        pass
# ----------------------------------------------------------------------------




# ----------------------------------Buttons-----------------------------------
@bot.message_handler(commands=['buttons'])
async def handle_buttons(message: types.Message):
    user_id = str(message.chat.id)
    user_lang = await get_lang(user_id) or 'en'
    markup = get_main_menu_inline(user_lang)
    await bot.send_message(
        message.chat.id,
        "Главное меню / Менюи асосӣ / Main Menu",
        reply_markup=markup
    )
# ----------------------------------------------------------------------------




#----------------------------------main menu-----------------------------------
def get_main_menu_inline(lang: str = 'en') -> InlineKeyboardMarkup:    
    labels = {
        'language': {
            'ru': "🌐 Язык",
            'tj': "🌐 Забон",
            'en': "🌐 Language"
        },
        'check': {
            'ru': "🔍 Проверить",
            'tj': "🔍 Санҷиш",
            'en': "🔍 Check"
        },
        'report': {
            'ru': "📊 Отчет",
            'tj': "📊 Ҳисобот",
            'en': "📊 Report"
        },
        'feedback': {
            'ru': "💬 Отзыв",
            'tj': "💬 Фикр",
            'en': "💬 Feedback"
        },
        'help': {
            'ru': "🆘 Помощь",
            'tj': "🆘 Ёрдам",
            'en': "🆘 Help"
        },
        'about': {
            'ru': "ℹ️ О боте",
            'tj': "ℹ️ Дар бораи",
            'en': "ℹ️ About"
        }
    }

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(labels['language'].get(lang, labels['language']['en']), callback_data="menu_language"),
        InlineKeyboardButton(labels['check'].get(lang, labels['check']['en']), callback_data="menu_check")
    )
    markup.add(
        InlineKeyboardButton(labels['report'].get(lang, labels['report']['en']), callback_data="menu_report"),
        InlineKeyboardButton(labels['feedback'].get(lang, labels['feedback']['en']), callback_data="menu_feedback")
    )
    markup.add(
        InlineKeyboardButton(labels['help'].get(lang, labels['help']['en']), callback_data="menu_help"),
        InlineKeyboardButton(labels['about'].get(lang, labels['about']['en']), callback_data="menu_about")
    )
    
    return markup


@bot.message_handler(func=lambda message: True)
async def handle_all_other_messages(message: types.Message):
    user_id = str(message.chat.id)
    lang = await get_lang(user_id) or 'en'
    text = message.text.strip() if message.text else ""

    messages = {
        'ru': "❓ Нераспознанное сообщение или команда. Пожалуйста, выберите вариант из меню ниже:",
        'tj': "❓ Паёми номаълум ё фармон. Лутфан вариантро аз менюи поён интихоб кунед:",
        'en': "❓ Unrecognized message or command. Please choose an option from the menu below:"
    }
    msg = messages.get(lang, messages['en'])
    await bot.send_message(
        message.chat.id,
        msg,
        reply_markup=get_main_menu_inline(),
        parse_mode='HTML'
    )


@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("menu_"))
async def handle_main_menu_callback(call):
    user_id = str(call.from_user.id)
    user_lang = await get_lang(user_id) or 'en'
    data = call.data

    if data == "menu_language":
        await handle_language(call.message)
    elif data == "menu_check":
        await handle_check(call.message)
    elif data == "menu_report":
        await handle_report(call.message)
    elif data == "menu_feedback":
        await handle_feedback(call.message)
    elif data == "menu_help":
        await handle_help(call.message)
    elif data == "menu_about":
        await handle_about(call.message)

    try:
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    await bot.answer_callback_query(call.id)
# ----------------------------------------------------------------------------

