# telegram_document_bot.py — Telegram бот с интеграцией PDF конструктора
# -----------------------------------------------------------------------------
# Документы: /контракт, /гарантия, /карта, /одобрение, /компенсация
# (латиница: /contrato|/contratto, /garanzia, /carta, /approvazione, /compensazione)
# -----------------------------------------------------------------------------
# Интеграция с pdf_costructor.py API
# -----------------------------------------------------------------------------
import logging
import os
from io import BytesIO

import telegram
from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, MessageHandler, ContextTypes, filters,
)

from pdf_costructor import (
    generate_contratto_pdf,
    generate_garanzia_pdf,
    generate_carta_pdf,
    generate_approvazione_pdf,
    generate_compensazione_pdf,
    monthly_payment,
    format_money
)


# ---------------------- Настройки ------------------------------------------
TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
DEFAULT_TAN = 7.86
DEFAULT_TAEG = 8.30

# Настройки прокси
PROXY_URL = "http://user351165:35rmsy@166.0.208.215:1479"


logging.basicConfig(format="%(asctime)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Состояния Conversation -------------------------------
CHOOSING_DOC, ASK_NAME, ASK_AMOUNT, ASK_DURATION, ASK_TAN, ASK_TAEG, ASK_COMP_COMMISSION, ASK_COMP_INDEMNITY = range(8)

# ---------------------- PDF-строители через API -------------------------
def build_contratto(data: dict) -> BytesIO:
    """Генерация PDF договора через API pdf_costructor"""
    return generate_contratto_pdf(data)


def build_lettera_garanzia(name: str) -> BytesIO:
    """Генерация PDF гарантийного письма через API pdf_costructor"""
    return generate_garanzia_pdf(name)


def build_lettera_carta(data: dict) -> BytesIO:
    """Генерация PDF письма о карте через API pdf_costructor"""
    return generate_carta_pdf(data)


def build_lettera_approvazione(data: dict) -> BytesIO:
    """Генерация PDF письма об одобрении через API pdf_costructor"""
    return generate_approvazione_pdf(data)


def build_compensazione(data: dict) -> BytesIO:
    return generate_compensazione_pdf(data)


# ------------------------- Handlers -----------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    kb = [["/контракт", "/гарантия"], ["/карта", "/одобрение"], ["/компенсация"]]
    await update.message.reply_text(
        "Выберите документ:",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING_DOC

async def choose_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    doc_type = update.message.text
    context.user_data['doc_type'] = doc_type
    await update.message.reply_text(
        "Введите имя и фамилию клиента:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    dt = context.user_data['doc_type']
    if dt in ('/garanzia', '/гарантия'):
        try:
            buf = build_lettera_garanzia(name)
            await update.message.reply_document(InputFile(buf, f"Garantía_{name}.pdf"))
        except Exception as e:
            logger.error(f"Ошибка генерации garanzia: {e}")
            await update.message.reply_text(f"Ошибка создания документа: {e}")
        return await start(update, context)
    if dt in ('/компенсация', '/compensazione'):
        context.user_data['name'] = name
        await update.message.reply_text("Введите сумму административного взноса (комиссии), €:")
        return ASK_COMP_COMMISSION
    context.user_data['name'] = name
    await update.message.reply_text("Введите сумму (€):")
    return ASK_AMOUNT

async def ask_comp_commission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amt = float(update.message.text.replace('€', '').replace(',', '.').replace(' ', ''))
    except Exception:
        await update.message.reply_text("Неверная сумма, попробуйте снова:")
        return ASK_COMP_COMMISSION
    context.user_data['commission'] = round(amt, 2)
    await update.message.reply_text("Введите сумму компенсации (индемпнитета), €:")
    return ASK_COMP_INDEMNITY


async def ask_comp_indemnity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amt = float(update.message.text.replace('€', '').replace(',', '.').replace(' ', ''))
    except Exception:
        await update.message.reply_text("Неверная сумма, попробуйте снова:")
        return ASK_COMP_INDEMNITY
    context.user_data['indemnity'] = round(amt, 2)
    d = context.user_data
    try:
        payload = {
            'name': d['name'],
            'commission': d['commission'],
            'indemnity': d['indemnity'],
        }
        buf = build_compensazione(payload)
        safe = d['name'].replace('/', '_').replace('\\', '_')[:80]
        await update.message.reply_document(InputFile(buf, f"Compensazione_{safe}.pdf"))
    except Exception as e:
        logger.error(f"Ошибка генерации compensazione: {e}")
        await update.message.reply_text(f"Ошибка создания документа: {e}")
    return await start(update, context)

async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amt = float(update.message.text.replace('€','').replace(',','.').replace(' ',''))
    except:
        await update.message.reply_text("Неверная сумма, попробуйте снова:")
        return ASK_AMOUNT
    context.user_data['amount'] = round(amt, 2)

    dt = context.user_data['doc_type']

    # Для всех документов кроме approvazione запрашиваем duration
    if dt not in ('/approvazione', '/одобрение'):
        await update.message.reply_text("Введите срок (месяцев):")
        return ASK_DURATION

    # Для approvazione сразу запрашиваем TAN
    await update.message.reply_text(f"Введите TAN (%), Enter для {DEFAULT_TAN}%:")
    return ASK_TAN

async def ask_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        mn = int(update.message.text)
    except:
        await update.message.reply_text("Неверный срок, попробуйте снова:")
        return ASK_DURATION
    context.user_data['duration'] = mn
    await update.message.reply_text(f"Введите TAN (%), Enter для {DEFAULT_TAN}%:")
    return ASK_TAN

async def ask_tan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    try:
        context.user_data['tan'] = float(txt.replace(',','.')) if txt else DEFAULT_TAN
    except:
        context.user_data['tan'] = DEFAULT_TAN

    dt = context.user_data['doc_type']

    # Для approvazione сразу генерируем документ (TAEG не нужен)
    if dt in ('/approvazione', '/одобрение'):
        d = context.user_data
        try:
            buf = build_lettera_approvazione(d)
            await update.message.reply_document(InputFile(buf, f"Aprobación_{d['name']}.pdf"))
        except Exception as e:
            logger.error(f"Ошибка генерации approvazione: {e}")
            await update.message.reply_text(f"Ошибка создания документа: {e}")
        return await start(update, context)

    # Для других документов запрашиваем TAEG
    await update.message.reply_text(f"Введите TAEG (%), Enter для {DEFAULT_TAEG}%:")
    return ASK_TAEG

async def ask_taeg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    try:
        context.user_data['taeg'] = float(txt.replace(',','.')) if txt else DEFAULT_TAEG
    except:
        context.user_data['taeg'] = DEFAULT_TAEG
    
    d = context.user_data
    d['payment'] = monthly_payment(d['amount'], d['duration'], d['tan'])
    dt = d['doc_type']
    
    try:
        if dt in ('/contrato', '/contratto', '/контракт'):
            buf = build_contratto(d)
            filename = f"Contrato_{d['name']}.pdf"
        else:
            buf = build_lettera_carta(d)
            filename = f"Tarjeta_{d['name']}.pdf"
            
        await update.message.reply_document(InputFile(buf, filename))
    except Exception as e:
        logger.error(f"Ошибка генерации PDF {dt}: {e}")
        await update.message.reply_text(f"Ошибка создания документа: {e}")
    
    return await start(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")

    if isinstance(context.error, telegram.error.Conflict):
        logger.error("Конфликт: другая копия бота уже работает! Убедитесь, что запущена только одна инстанс.")
        return

    if update and hasattr(update, 'effective_message'):
        try:
            await update.effective_message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
        except Exception:
            pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
    return await start(update, context)

# ---------------------------- Main -------------------------------------------
def main():
    app = Application.builder().token(TOKEN).proxy_url(PROXY_URL).build()

    app.add_error_handler(error_handler)

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_DOC: [MessageHandler(filters.Regex(r'^(/contrato|/contratto|/garanzia|/carta|/approvazione|/compensazione|/контракт|/гарантия|/карта|/одобрение|/компенсация)$'), choose_doc)],
            ASK_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_AMOUNT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            ASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_duration)],
            ASK_TAN:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_tan)],
            ASK_TAEG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_taeg)],
            ASK_COMP_COMMISSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_comp_commission)],
            ASK_COMP_INDEMNITY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_comp_indemnity)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )
    app.add_handler(conv)

    print("Документы: /контракт, /гарантия, /карта, /одобрение, /компенсация")
    print("🔧 Использует PDF конструктор из pdf_costructor.py")
    print("🌐 Подключен через прокси: 166.0.208.215:1479")
    print("⚠️  Убедитесь, что запущена только одна копия бота!")

    try:
        app.run_polling()
    except KeyboardInterrupt:
        print("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка при работе бота: {e}")

if __name__ == '__main__':
    main()
