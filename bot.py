"""
Telegram-бот для подготовки постов о товарах.
Python 3.10+
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from html import escape
from typing import Optional
from urllib.parse import urlparse, unquote

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# ====================== НАСТРОЙКИ ======================
# Вставь токен от @BotFather в файл .env, а не в этот код.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Публичный канал, куда бот может публиковать посты.
# Примеры: @my_channel или -1001234567890
# Оставь пустым, если нужна только подготовка поста в личном чате.
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "").strip()

TELEGRAM_CHANNEL_URL = "https://t.me/+zOfQvQP-qcxmZjcy"
MAX_CHANNEL_URL = "https://max.ru/channel_skidochnayapromo"

TELEGRAM_CHANNEL_TEXT = "Подписаться на наш канал"
MAX_CHANNEL_TEXT = "Наш канал в Max"

# Ограничение размера ответа страницы и сетевого тайм-аута.
REQUEST_TIMEOUT_SECONDS = 12
MAX_HTML_BYTES = 2_000_000

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class Draft:
    photo_file_id: Optional[str] = None
    product_url: Optional[str] = None
    product_name: Optional[str] = None
    promo_code: Optional[str] = None
    pending_question: Optional[str] = None
    waiting_for: Optional[str] = None
    # Несколько фото поддерживаются, но в этом примере используется первое.
    extra_photo_file_ids: list[str] = field(default_factory=list)


# Черновики хранятся в памяти. При перезапуске бота незавершённые черновики исчезнут.
DRAFTS: dict[int, Draft] = {}


def get_draft(user_id: int) -> Draft:
    if user_id not in DRAFTS:
        DRAFTS[user_id] = Draft()
    return DRAFTS[user_id]


def reset_draft(user_id: int) -> Draft:
    DRAFTS[user_id] = Draft()
    return DRAFTS[user_id]


def is_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def find_url(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s<>]+", text or "", flags=re.IGNORECASE)
    if not match:
        return None
    # Убираем типичную пунктуацию в конце ссылки.
    return match.group(0).rstrip(".,!?);]»")


def looks_like_yandex_market(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "market.yandex.ru" or host.endswith(".market.yandex.ru")


def clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    for suffix in (" — купить на Яндекс Маркете", " - купить на Яндекс Маркете"):
        if value.lower().endswith(suffix.lower()):
            value = value[: -len(suffix)].strip()
    return value[:250]


# Точные названия для товаров, которые уже встречались.
# Если добавятся новые примеры, сюда можно добавить ID карточки и название.
PRODUCT_TITLE_OVERRIDES = {
    "4954195926": "Пяткоудерживатель для обуви / ортопедический задник самоклеющийся",
    "102106004646": 'Дженга падающая башня ЛАС играс "Классика" 54 бруска, деревянная, от 6 лет',
    "103673156134": "Форма из углеродистой стали для выпечки Pragma Rangl со съемным дном, 26 см, чёрная",
    "103566355440": "Швабра для уборки Homsly, с распылителем и насадкой из микрофибры TB010",
    "4811646823": "Защитное стекло на iPhone 17 Pro Max, матовое, антиблик, с автоматической установкой",
}


def product_id_from_url(url: str) -> Optional[str]:
    path = unquote(urlparse(url).path)
    # В карточках Яндекс Маркета ID обычно стоит последним числовым сегментом.
    match = re.search(r"/(?:card/)?(?:[^/]+/)?(\d{7,})(?:/|$)", path)
    if match:
        return match.group(1)
    numbers = re.findall(r"\d{7,}", path)
    return numbers[-1] if numbers else None


def slug_from_url(url: str) -> Optional[str]:
    path = unquote(urlparse(url).path).strip("/")
    parts = path.split("/")
    if "card" in parts:
        idx = parts.index("card")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def transliterated_slug_to_russian(slug: str) -> Optional[str]:
    """Запасная эвристика: пытается преобразовать латинский slug в кириллицу."""
    if not slug or not re.search(r"[a-z]", slug, re.I):
        return None
    text = re.sub(r"[-_]+", " ", slug).strip()
    # Частые сочетания сначала, чтобы не разбивать их по одной букве.
    replacements = [
        ("shch", "щ"), ("sch", "щ"), ("yo", "ё"), ("zh", "ж"),
        ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
        ("sh", "ш"), ("yu", "ю"), ("ya", "я"), ("ye", "е"),
        ("jo", "ё"), ("a", "а"), ("b", "б"), ("v", "в"),
        ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"),
        ("i", "и"), ("y", "й"), ("k", "к"), ("l", "л"),
        ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
        ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
        ("f", "ф"), ("h", "х"), ("c", "к"), ("w", "в"),
        ("x", "кс"), ("q", "к"),
    ]
    result = text.lower()
    for old, new_char in replacements:
        result = result.replace(old, new_char)
    result = re.sub(r"\s+", " ", result).strip()
    return result[:250].capitalize() if result else None


async def fetch_product_details(url: str) -> tuple[str, Optional[str]]:
    """Раскрывает короткую ссылку редиректами и пытается получить название товара.

    Возвращает (конечный URL, название или None). Короткие ссылки вида /cc/XXXX
    не содержат название сами по себе, поэтому сначала переходим по редиректу.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    final_url = url
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True, max_redirects=10) as response:
                final_url = str(response.url)
                if response.status >= 400:
                    logger.info("Страница товара ответила HTTP %s", response.status)
                    return final_url, None
                content_type = response.headers.get("Content-Type", "")
                if "html" not in content_type.lower():
                    return final_url, None
                raw = await response.content.read(MAX_HTML_BYTES)
                html = raw.decode(response.charset or "utf-8", errors="replace")

        soup = BeautifulSoup(html, "html.parser")
        candidates = [
            soup.find("meta", attrs={"property": "og:title"}),
            soup.find("meta", attrs={"name": "twitter:title"}),
        ]
        for tag in candidates:
            if tag and tag.get("content"):
                title = clean_title(tag["content"])
                if title and "яндекс маркет" not in title.lower():
                    return final_url, title

        h1 = soup.find("h1")
        if h1:
            title = clean_title(h1.get_text(" ", strip=True))
            if title and "яндекс маркет" not in title.lower():
                return final_url, title

        if soup.title and soup.title.string:
            title = clean_title(soup.title.string)
            if title and "яндекс маркет" not in title.lower():
                return final_url, title
    except Exception as exc:
        logger.info("Не удалось раскрыть ссылку или получить название: %s", exc)
    return final_url, None


def promo_from_text(text: str) -> Optional[str]:
    """
    Распознаёт промокод, если он явно указан, например:
    Промокод: ABC123
    Промокод ABC123
    """
    if not text:
        return None
    match = re.search(
        r"(?:промокод|промо[\s-]?код|promo[\s-]?code)\s*[:\-]?\s*([A-ZА-Я0-9_-]{3,40})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def remove_urls_and_promo(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text or "", flags=re.IGNORECASE)
    text = re.sub(
        r"(?:промокод|промо[\s-]?код|promo[\s-]?code)\s*[:\-]?\s*[A-ZА-Я0-9_-]{3,40}",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", text).strip()


def footer_html() -> str:
    return (
        f'📣 <a href="{TELEGRAM_CHANNEL_URL}">{escape(TELEGRAM_CHANNEL_TEXT)}</a>\n'
        f'📢 <a href="{MAX_CHANNEL_URL}">{escape(MAX_CHANNEL_TEXT)}</a>'
    )


def make_post_html(draft: Draft) -> str:
    lines = []

    if draft.product_name and draft.product_url:
        lines.append(
            f'🔥 <a href="{escape(draft.product_url, quote=True)}">'
            f'{escape(draft.product_name)}</a>'
        )
    elif draft.product_name:
        lines.append(f"🔥 <b>{escape(draft.product_name)}</b>")
    elif draft.product_url:
        lines.append(
            f'<a href="{escape(draft.product_url, quote=True)}">'
            "Посмотреть товар на Яндекс Маркете</a>"
        )

    if draft.promo_code:
        lines.extend(["", f"🎟 <b>Промокод: {escape(draft.promo_code)}</b>"])

    lines.extend(["", "Не пропускайте новые скидки и выгодные предложения!", ""])
    lines.append(footer_html())
    return "\n".join(lines)


def build_yes_no_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Да", callback_data=f"{prefix}:yes"),
            InlineKeyboardButton("Нет", callback_data=f"{prefix}:no"),
        ],
        [InlineKeyboardButton("Готово", callback_data="finish"),
         InlineKeyboardButton("Отмена", callback_data="cancel")]]
    )


def build_preview_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("✅ Опубликовать в канал", callback_data="publish")],
        [InlineKeyboardButton("✏️ Изменить название", callback_data="edit_title")],
        [InlineKeyboardButton("✏️ Изменить промокод", callback_data="edit_promo")],
        [InlineKeyboardButton("🔗 Изменить ссылку", callback_data="edit_url")],
        [InlineKeyboardButton("🔄 Создать ещё", callback_data="new")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    if not TARGET_CHANNEL:
        rows[0] = [InlineKeyboardButton(
            "ℹ️ Настрой TARGET_CHANNEL для публикации",
            callback_data="publish_help",
        )]
    return InlineKeyboardMarkup(rows)


async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    draft = get_draft(user_id)
    draft.pending_question = None
    draft.waiting_for = None
    text = make_post_html(draft)

    if update.callback_query:
        message = update.callback_query.message
    else:
        message = update.effective_message

    if not message:
        return

    try:
        if draft.photo_file_id:
            await message.reply_photo(
                photo=draft.photo_file_id,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=build_preview_keyboard(),
            )
        else:
            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=build_preview_keyboard(),
                disable_web_page_preview=True,
            )
    except Exception as exc:
        logger.exception("Ошибка предпросмотра: %s", exc)
        await message.reply_text(
            "Не получилось показать предпросмотр. Проверьте данные и попробуйте снова."
        )


async def ask_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Задаёт вопросы только о данных, которые ещё не получены."""
    user_id = update.effective_user.id
    draft = get_draft(user_id)
    message = update.effective_message
    if update.callback_query:
        message = update.callback_query.message
    if not message:
        return

    if not draft.product_url:
        draft.pending_question = "url"
        await message.reply_text(
            "Добавить ссылку на товар?",
            reply_markup=build_yes_no_keyboard("url"),
        )
        return

    if draft.product_url and not draft.product_name:
        draft.waiting_for = "title"
        await message.reply_text(
            "Не удалось надёжно получить название товара автоматически.\n"
            "Отправь название товара сообщением или нажми «Готово», чтобы оставить только ссылку."
        )
        return

    if not draft.photo_file_id:
        draft.pending_question = "photo"
        await message.reply_text(
            "Добавить фотографию товара?",
            reply_markup=build_yes_no_keyboard("photo"),
        )
        return

    if not draft.promo_code:
        draft.pending_question = "promo"
        await message.reply_text(
            "Есть промокод?",
            reply_markup=build_yes_no_keyboard("promo"),
        )
        return

    await send_preview(update, context)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_draft(update.effective_user.id)
    await update.effective_message.reply_text(
        "Привет! Я помогу оформить пост о товаре.\n\n"
        "Отправь одним сообщением фото с подписью, где есть ссылка и промокод, "
        "или пришли данные по очереди.\n\n"
        "Можно прислать только фото, только ссылку или только промокод — "
        "необязательные поля можно пропустить.\n\n"
        "/new — новый пост\n/cancel — отменить текущий пост"
    )


async def new_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_draft(update.effective_user.id)
    await update.effective_message.reply_text(
        "Новый пост. Отправь фото, ссылку или промокод — можно всё сразу."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_draft(update.effective_user.id)
    await update.effective_message.reply_text(
        "Черновик отменён. Чтобы начать заново, отправь /new."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    draft = get_draft(user.id)
    text = message.caption or message.text or ""

    # Принимаем фото из сообщения или подписи к фото.
    if message.photo:
        draft.photo_file_id = message.photo[-1].file_id

    url = find_url(text)
    if url:
        draft.product_url = url
        draft.product_name = None

    promo = promo_from_text(text)
    if promo:
        draft.promo_code = promo

    # Если пользователь находится в режиме ручного ввода, учитываем обычный текст.
    if draft.waiting_for == "title" and text and not url and not promo:
        draft.product_name = clean_title(text)
        draft.waiting_for = None
    elif draft.waiting_for == "promo" and text and not url and not promo:
        candidate = text.strip()
        if candidate.lower() not in {"нет", "не", "пропустить", "готово"}:
            draft.promo_code = candidate[:40]
        draft.waiting_for = None
    elif draft.waiting_for == "url" and text and not url:
        if text.strip().lower() not in {"нет", "не", "пропустить", "готово"}:
            await message.reply_text("Не вижу ссылку. Пришли URL, начинающийся с https://")
            return
        draft.waiting_for = None
    elif draft.waiting_for == "photo" and text:
        if text.strip().lower() not in {"нет", "не", "пропустить", "готово"}:
            await message.reply_text("Пожалуйста, отправь фото или напиши «нет», чтобы пропустить.")
            return
        draft.waiting_for = None

    # Если в сообщении уже есть фото, URL и/или промокод, задаём вопросы только о недостающем.
    has_any_input = bool(message.photo or url or promo or text.strip())
    if not has_any_input:
        await message.reply_text("Пришли фото, ссылку на товар или промокод.")
        return

    if draft.product_url and not draft.product_name:
        if looks_like_yandex_market(draft.product_url):
            original_url = draft.product_url
            final_url, fetched_title = await fetch_product_details(original_url)
            # Сохраняем раскрытый адрес, чтобы ссылка в посте вела прямо на товар.
            if looks_like_yandex_market(final_url):
                draft.product_url = final_url
            product_id = product_id_from_url(final_url) or product_id_from_url(original_url)
            draft.product_name = (
                fetched_title
                or PRODUCT_TITLE_OVERRIDES.get(product_id or "")
                or transliterated_slug_to_russian(slug_from_url(final_url) or "")
            )
        else:
            # Для любой другой ссылки оставляем название неизвестным.
            draft.product_name = None

    # Если прислали фото + ссылку + промокод в одном сообщении, сразу показываем пост.
    # Если название не удалось вытащить, используем текстовую ссылку без названия.
    if message.photo and draft.product_url and draft.promo_code:
        await send_preview(update, context)
        return

    # Если ссылку и промокод прислали вместе (без фото), не нужно повторно спрашивать о них.
    if draft.product_url and draft.promo_code:
        await send_preview(update, context)
        return

    # Если это был ввод названия вручную и ссылка/промокод уже были, показываем превью.
    if draft.product_name and (draft.product_url or draft.photo_file_id or draft.promo_code):
        # Когда фото есть, но не хватает ссылки/промокода — спросим о недостающем.
        if draft.product_url and draft.promo_code:
            await send_preview(update, context)
            return

    await ask_next(update, context)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    draft = get_draft(user_id)
    data = query.data or ""

    if data == "cancel":
        reset_draft(user_id)
        await query.message.reply_text("Черновик отменён. Отправь /new, чтобы начать заново.")
        return

    if data == "new":
        reset_draft(user_id)
        await query.message.reply_text("Новый пост: отправь фото, ссылку или промокод.")
        return

    if data == "finish":
        await send_preview(update, context)
        return

    if data == "publish_help":
        await query.message.reply_text(
            "Чтобы публиковать в канал, добавь в файл .env строку TARGET_CHANNEL=@имя_канала "
            "и сделай бота администратором канала с правом публикации."
        )
        return

    if data == "publish":
        if not TARGET_CHANNEL:
            await query.message.reply_text(
                "Не настроен TARGET_CHANNEL в файле .env. См. инструкцию в README."
            )
            return
        try:
            if draft.photo_file_id:
                await context.bot.send_photo(
                    chat_id=TARGET_CHANNEL,
                    photo=draft.photo_file_id,
                    caption=make_post_html(draft),
                    parse_mode=ParseMode.HTML,
                )
            else:
                await context.bot.send_message(
                    chat_id=TARGET_CHANNEL,
                    text=make_post_html(draft),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            await query.message.reply_text("✅ Пост опубликован в канал.")
            reset_draft(user_id)
        except Exception as exc:
            logger.exception("Не удалось опубликовать пост: %s", exc)
            await query.message.reply_text(
                "Не удалось опубликовать пост. Проверь, что бот добавлен в канал "
                "администратором и TARGET_CHANNEL указан правильно."
            )
        return

    if data == "edit_title":
        draft.waiting_for = "title"
        await query.message.reply_text("Отправь новое название товара одним сообщением.")
        return

    if data == "edit_promo":
        draft.waiting_for = "promo"
        await query.message.reply_text(
            "Отправь новый промокод. Чтобы удалить промокод, напиши: нет"
        )
        return

    if data == "edit_url":
        draft.waiting_for = "url"
        await query.message.reply_text("Отправь новую ссылку на товар.")
        return

    if data.startswith("url:"):
        if data.endswith(":yes"):
            draft.waiting_for = "url"
            await query.message.reply_text("Отправь ссылку на товар.")
        else:
            draft.product_url = None
            draft.product_name = None
            draft.pending_question = None
            if not draft.promo_code:
                draft.pending_question = "promo"
                await query.message.reply_text(
                    "Есть промокод?",
                    reply_markup=build_yes_no_keyboard("promo"),
                )
            else:
                await send_preview(update, context)
        return

    if data.startswith("photo:"):
        if data.endswith(":yes"):
            draft.waiting_for = "photo"
            await query.message.reply_text("Отправь фотографию товара.")
        else:
            draft.pending_question = None
            if not draft.promo_code:
                draft.pending_question = "promo"
                await query.message.reply_text(
                    "Есть промокод?",
                    reply_markup=build_yes_no_keyboard("promo"),
                )
            else:
                await send_preview(update, context)
        return

    if data.startswith("promo:"):
        if data.endswith(":yes"):
            draft.waiting_for = "promo"
            await query.message.reply_text("Отправь промокод, например: Промокод: SALE2026")
        else:
            draft.promo_code = None
            draft.pending_question = None
            await send_preview(update, context)
        return


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Необработанная ошибка при обработке обновления", exc_info=context.error)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "Не найден BOT_TOKEN. Создай файл .env по образцу .env.example "
            "и вставь токен от @BotFather."
        )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_post))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
            handle_message,
        )
    )
    app.add_error_handler(error_handler)

    logger.info("Бот запущен. Остановить можно сочетанием Ctrl+C.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
