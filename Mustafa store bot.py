
import asyncio
import sqlite3
import random
import string
import traceback
from datetime import datetime, timedelta
import re
import requests
import json
import os

from telegram import (
    Update,
    InlineKeyboardMarkup as _PTBInlineKeyboardMarkup,
    InlineKeyboardButton as _PTBInlineKeyboardButton,
    LabeledPrice,
    CopyTextButton,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    PicklePersistence,
    filters,
)
from telegram.error import BadRequest

# ===================== شيم لمحاكاة واجهة telebot الخاصة بلوحات الأزرار =====================
# يسمح باستخدام .row()/.add() كما في telebot، مع بناء كائن InlineKeyboardMarkup
# أصلي من python-telegram-bot تحت الغطاء بدون تعديل آلاف أسطر بناء لوحات الأزرار.
#
# ملاحظة تقنية: PTB يجمّد (freeze) الكائنات فور إنشائها ويمنع تعيين أي خاصية
# ليست من الحقول الرسمية (مثل row_width) أو حتى إعادة تعيين حقل رسمي بعد
# التجميد (مثل inline_keyboard). نتحايل على هذا باستخدام object.__setattr__
# مباشرة، والتي تتجاوز آلية __setattr__ المخصصة بالكامل.
class InlineKeyboardMarkup(_PTBInlineKeyboardMarkup):
    def __init__(self, row_width=1):
        super().__init__(inline_keyboard=[])
        object.__setattr__(self, '_row_width', row_width)
        object.__setattr__(self, '_rows', [])

    def row(self, *buttons):
        self._rows.append(list(buttons))
        object.__setattr__(self, 'inline_keyboard', tuple(tuple(r) for r in self._rows))
        return self

    def add(self, *buttons):
        for i in range(0, len(buttons), self._row_width):
            self._rows.append(list(buttons[i:i + self._row_width]))
        object.__setattr__(self, 'inline_keyboard', tuple(tuple(r) for r in self._rows))
        return self

# شيم لأزرار InlineKeyboardButton: كل الأزرار زرقاء (primary) افتراضيًا
# إلا إذا حددنا style صراحة عند تعريف الزر (success/danger).
class InlineKeyboardButton(_PTBInlineKeyboardButton):
    def __init__(self, text, style="primary", **kwargs):
        super().__init__(text=text, style=style, **kwargs)

# ===================== التوكنات والمتغيرات =====================
TOKEN = "8974623152:AAFRlr8P3Ju6u8Qi2xdEM9mjYzNACQaG7CE"
API_KEY = "7adf22fcaf76de35136f41bed8862f7b"  # مفتاح fast70.com
SMM_API_URL = "https://fast70.com/api/v2"  # ⚠️ تأكد من الرابط بالضبط من صفحة "توثيقات API" بحسابك (fast70.com/api)
FREE_SMM_API_URL = "https://perfectfollow.app/api/v2"  # مزود الخدمات المجانية
FREE_SMM_API_KEY = "89b9973c796dc5250a6b4c40e916c0ae"  # مفتاح perfectfollow.app (خدمات مجانية)
SMM_PROFIT_MARGIN = 1.10  # هامش ربح 10% فوق سعر المزود
POINTS_PER_USD = 10000    # 10,000 نقطة = 1 دولار
ORDER_COMPLETION_CHANNEL = "@NNL38"  # قناة نشر رسائل اكتمال الطلبات

# ===================== أسماء الخدمات المدفوعة (لعرضها بشكل ثابت عند اختيار الخدمة) =====================
SMM_SERVICE_NAMES = {
    "kick_8861": "متابعين 👤 كيك (بدون ضمان) الأرخص 🎁",
    "kick_8347": "مشاهدات 👁 كيك ( ضمان 30 يوم) 🚀",
    "kick_8356": "مشاهدات 👁 كيك كليب ( بدون ضمان ) 🚀",
    "kick_8350": "تصويت كيك 📊 استطلاع رأي(ضمان 30 يوم)🚀",
    "kick_8367": "مشاهدات 👁 كيك بث مباشر ( 5 دقيقة ) 🚀",
    "kick_8366": "مشاهدات 👁 كيك بث مباشر ( 10 دقيقة ) 🚀",
    "kick_8357": "مشاهدات 👁 كيك بث مباشر ( 15 دقيقة ) 🚀",
    "kick_8358": "مشاهدات 👁 كيك بث مباشر ( 30 دقيقة ) 🚀",
    "kick_8359": "مشاهدات 👁 كيك بث مباشر ( 45 دقيقة ) 🚀",
    "kick_8360": "مشاهدات 👁 كيك بث مباشر ( 60 دقيقة ) 🚀",
    "kick_8368": "مشاهدات 👁 كيك بث مباشر ( 90 دقيقة ) 🚀",
    "kwai_5420": "متابعين 👤 كواي ( بدون ضمان ) الأرخص 🎁",
    "kwai_2157": "لايكات 🤎 كواي ( ضمان 30 يوم ) 🚀",
    "kwai_5440": "مشاركات ♻️ كواي ( بدون ضمان) 🚀",
    "kwai_5416": "تعليقات💬كواي عرب مخصص(ضمان 30يوم)🚀",
    "kwai_8369": "لايكات 🤎 كواي بث مباشر ( عرب) 🚀",
    "kwai_8370": "مشاركات ♻️ كواي بث مباشر ( عرب) 🚀",
    "kwai_5438": "مشاهدات 👁 كواي 🇪🇬 ( بدون ضمان ) 🚀",
    "kwai_5493": "مشاهدات 👁 كواي 🇱🇧 ( بدون ضمان ) 🚀",
    "kwai_5499": "مشاهدات 👁 كواي 🇮🇶 ( بدون ضمان ) 🚀",
    "kwai_5421": "مشاهدات 👁 كواي 🇹🇷 ( بدون ضمان ) 🚀",
    "kwai_5484": "مشاهدات 👁 كواي 🇸🇦 ( بدون ضمان ) 🚀",
    "kwai_5486": "مشاهدات 👁 كواي 🇰🇼 ( بدون ضمان ) 🚀",
    "kwai_5495": "مشاهدات 👁 كواي 🇶🇦 ( بدون ضمان ) 🚀",
    "kwai_5494": "مشاهدات 👁 كواي 🇴🇲 ( بدون ضمان ) 🚀",
    "spotify_4641": "متابعين 👤 سبوتيفاي ( مدى الحياة ) 🚀",
    "twitter_998": "متابعين 👤 تويتر ( بدون ضمان ) 🚀",
    "twitter_7761": "لايكات 🤎 تويتر ( بدون ضمان ) 🚀",
    "twitch_2252": "متابعين 👤 تويتش ( ضمان 15 يوم ) 🚀",
    "trovo_7289": "متابعين 👤 تروفو ( جودة جيدة ) 🚀",
    "whatsapp_7335": "اعضاء 👤 واتساب ( بدون ضمان ) 🚀",
    "whatsapp_5634": "استطلاع رأي 📊 واتساب ( خيار A ) 🚀",
    "whatsapp_8015": "استطلاع رأي 📊 واتساب ( خيار B ) 🚀",
    "whatsapp_5636": "استطلاع رأي 📊 واتساب ( خيار C ) 🚀",
    "whatsapp_8021": "استطلاع رأي 📊 واتساب ( خيار D ) 🚀",
    "whatsapp_8612": "تفاعل ( 👍 ) واتساب ( منشور قناة ) 🚀",
    "whatsapp_8613": "تفاعل ( ❤️ ) واتساب ( منشور قناة ) 🚀",
    "whatsapp_8614": "تفاعل ( 😂 ) واتساب ( منشور قناة ) 🚀",
    "whatsapp_8615": "تفاعل ( 😲 ) واتساب ( منشور قناة ) 🚀",
    "whatsapp_8616": "تفاعل ( 😢 ) واتساب ( منشور قناة ) 🚀",
    "whatsapp_8618": "تفاعل ( 👍 ❤️ 🔥 🎉 😁 ) واتساب( منشور قناة ) 🚀",

    "insta_720": "متابعين انستاكرام - ثابت 100% -زيادة 20%- تعويض 6 أشهر",
    "insta_608": "متابعين انستاكرام - ثابت 100%-زيادة 80% -تعويض لمدة 6 أشهر",
    "insta_610": "متابعين انستغرام - ثابت 100% -زيادة 40%- تعويض 90 يوم",
    "insta_561": "متابعين انستاكرام - ثابت 100% -زيادة 40%- تعويض 30 يوم",
    "insta_682": "متابعين انستاكرام - سرعة فائقة الأفضل - تعويض 30 يوم زيادة 20%",
    "insta_731": "متابعين انستغرام - سرعة فائقة الأفضل - تعويض 30 يوم",
    "insta_582": "متابعين انستاكرام - زيادة %20 - 50% - سرعة فائقة",
    "insta_696": "متابعين انستاكرام - سرعة فائقة جودة عالية الأفضل",
    "insta_721": "متابعين انستاكرام - حسابات قديمة - نزول 10-20% الأرخص - زيادة 20%",
    "insta_580": "متابعين انستاكرام - الأرخص - بدون تعويض",
    "insta_730": "متابعين انستاكرام - حسابات قديمة - نزول 10-20% الأرخص",
    "insta_419": "لايكات انستاكرام حقيقية عراقية | دعم ممول - فوري",
    "insta_722": "لايكات إنستقرام ريلز + بوست - الأرخص",
    "insta_562": "لايكات إنستقرام ريلز + بوست - سرعة عالية",
    "insta_519": "لايكات إنستقرام شاملة - سرعة عالية",
    "insta_343": "لايكات إنستقرام ريلز + بوست - سريع",
    "insta_642": "مشاهدات ستوري انستاكرام لجميع الستوريات - سريع",
    "insta_621": "مشاهدات إنستقرام ريلز 1م ✅ - مضمونة وسريعة للكميات الكبيرة!",
    "insta_620": "مشاهدات انستاكرام - ريلز - للكميات الكبيرة جدا 1+ مليون",
    "insta_402": "مشاركات فيديو ريلز انستقرام | حركة الاكسبلور 🔁 10م",
    "insta_639": "أعضاء قناة أنستاكرام - بدون تعويض",
    "insta_566": "دعم اضافات بنات - دعم عراقي",
    "fb_369": "متابعين فيسبوك شامل 📘 | بيج + بروفايل",
    "fb_654": "متابعين فيسبوك | بيج + صفحة شخصية",
    "fb_655": "متابعين فيسبوك | بيج + صفحة شخصية",
    "fb_656": "متابعين فيسبوك | بيج + صفحة شخصية",
    "fb_657": "متابعين فيسبوك | بيج + صفحة شخصية",
    "fb_499": "متابعين بروفايل و بيجات عامة فيسبوك | 500ك | فوري 🌺",
    "fb_651": "فيسبوك - لايكات للمنشور - ريلز + بوست",
    "fb_652": "فيسبوك - لايكات للمنشور - ريلز + بوست",
    "fb_705": "فيسبوك - لايكات للمنشور - ريلز + بوست",
    "fb_659": "مشاهدات فيديو فيسبوك | ريلز و عادي | تعويض تلقائي",
    "fb_660": "مشاهدات فيديو فيسبوك | ريلز و عادي",
    "fb_661": "مشاهدات فيديو فيسبوك | ريلز و عادي",
    "fb_662": "مشاهدات فيديو فيسبوك | ريلز و عادي",
    "fb_663": "مشاهدات فيديو فيسبوك | ريلز و عادي",
    "fb_757": "أعضاء كروب فيسبوك - جودة عالية - سرعة متوسطة",
    "tiktok_564": "دعم ممول - 1000 متابع تيكتوك عراقي حقيقي 🇮🇶 100%",
    "tiktok_704": "متابعين تيكتوك - فوري - جديد",
    "tiktok_748": "متابعين تيكتوك - فوري - جديد",
    "tiktok_645": "تيكتوك مشاركة حركة الأكسبلور",
    "tiktok_646": "تيكتوك مشاركة حركة الأكسبلور",
    "tiktok_648": "تيكتوك مشاركة حركة الأكسبلور",
    "tiktok_753": "لايكات تيكتوك - بدون ضمان",
    "tiktok_754": "لايكات تيكتوك - بدون ضمان",
    "tiktok_756": "لايكات تيكتوك + مشاهدات - حسابات حقيقية مختلطه - تعويض 10 أيام",
    "tiktok_746": "مشاهدات تيكتوك حقيقية - من الاعلانات- ضمان مدى الحياة - بدون نزول",
    "tiktok_747": "مشاهدات تيكتوك حقيقية - من الاعلانات- ضمان مدى الحياة - بدون نزول",
    "telegram_698": "اعضاء تليكرام -حسابات محذوفة - ضمان 90 يوم سريع",
    "telegram_714": "اعضاء تليكرام - قناة عامه - ضمان 60يوم",
    "telegram_358": "مشاهدات تلي لبوست واحد 🔥",
    "telegram_627": "مشاهدات بوست تليكرام - سوبر فاست",
    "telegram_480": "مشاهدات تلي لبوست واحد 🔥",
    "telegram_710": "مشاهدات تلي لبوست واحد 🔥 سريع",
    "telegram_732": "مشاهدات تلي- مستقبلية - 5 بوست",
    "telegram_733": "مشاهدات تلي- مستقبلية - 10 بوست",
    "telegram_734": "مشاهدات تلي- مستقبلية - 20 بوست",
    "telegram_735": "مشاهدات تلي- مستقبلية - 30 بوست",
    "telegram_736": "مشاهدات تلي- مستقبلية - 20 بوست",
    "telegram_737": "مشاهدات تلي- مستقبلية - 100 بوست",
    "telegram_738": "مشاهدات تلي- أخر 5 بوست",
    "telegram_739": "مشاهدات تلي- أخر 5 بوست",
    "telegram_740": "مشاهدات تلي- أخر 5 بوست",
    "telegram_741": "مشاهدات تلي- أخر 10 بوست",
    "telegram_742": "مشاهدات تلي- أخر 10 بوست",
    "telegram_743": "مشاهدات تلي- أخر 20 بوست",
    "telegram_745": "مشاهدات تلي- أخر 100 بوست",
    "telegram_355": "أعضاء تيليجرام 🇨🇳 صينيين - مناسب للقنوات العامة",
    "telegram_725": "اعضاء قناة تليكرام - بدون تعويض - نزول عالي",
    "telegram_726": "اعضاء قناة تليكرام - بدون تعويض - نزول عالي",
    "telegram_767": "تليكرام - تفاعلات برمز {💋}",
    "telegram_769": "تليكرام - تفاعلات برمز {❤️}",
    "telegram_759": "تليكرام - تفاعلات برمز {🔥}",
    "telegram_764": "تليكرام - تفاعلات برمز {🤩}",
    "telegram_765": "تليكرام - تفاعلات برمز {😱}",
    "telegram_763": "تليكرام - تفاعلات برمز {🤣}",
    "telegram_629": "تليكرام - تفاعلات بوست تليكرام 👎💩🤮🤔🤯😁😢🤬 - سريع",
    "telegram_713": "تليكرام تفاعلات ايجابية 👍🤩🎉🔥❤️🥰👏🏻🥳😍❤️‍🔥💯",
    "telegram_631": "خدمة تعزيز قناة تيليجرام 💎 | تفعيل ميزة القصص Story ضمان 1 يوم",
    "telegram_632": "خدمة تعزيز قناة تيليجرام 💎 | تفعيل ميزة القصص Story ضمان 1 يوم",
    "telegram_638": "مشاهدات ستوري تليكرام - سريع",
    "telegram_750": "اعضاء تليكرام بريميوم ضمان 7 أيام",
    "telegram_751": "اعضاء تليكرام بريميوم ضمان 15-30 يوم",
    "telegram_752": "اعضاء تليكرام بريميوم ضمان 30-60 يوم",
    "youtube_624": "مشاهدات يوتيوب | ٢٠ ألف مشاهدة يوميًا | - تعويض 30 يوم",
    "ad_paid_1": "لمدة 1 ساعة 🕐 = 1 نجمة ⭐️",
    "ad_paid_2": "لمدة 2 ساعة 🕐 = 1 نجمة ⭐️",
    "ad_paid_3": "لمدة 3 ساعة 🕐 = 1 نجمة ⭐️",
    "ad_paid_4": "لمدة 4 ساعة 🕐 = 1 نجمة ⭐️",
    "ad_paid_5": "لمدة 5 ساعة 🕐 = 1 نجمة ⭐️",
}

ADMIN_IDS = [8767001570]
GROUP_SUPPORT_USERNAME = "NN34LL"  # كروب "دعم قناتك بالكروب" المستهدف
SUPPORT_USERNAME = "NN25LL"  # يوزر حساب الدعم الفني
AUTOPOST_CHANNEL = "NN72D"  # قناة نشر كود النقاط التلقائي (قناة توزيع النقاط)
AUTOPOST_COUPON_POINTS = 25
AUTOPOST_COUPON_MAX_USES = 40
DEFAULT_FORCE_SUB_CHANNEL_USERNAME = "NN32J"  # القناة الافتراضية للاشتراك الإجباري بالكروب (لما ما يكون في قناة مدفوعة فعالة)
DEFAULT_FORCE_SUB_CHANNEL_LINK = "https://t.me/NN32J"

# كل "أعلام الانتظار" (gate flags) يلي تحدد كيف يُفسَّر أول رسالة نصية جاية من المستخدم.
# لازم تكون متبادلة الاستبعاد دايماً: أي فعل جديد يبلش "انتظار" لازم يمسح الباقي أول،
# وإلا رسالة المستخدم بتنفسّر غلط حسب أقدم علم عالق (باگ شائع كان موجود بكل الكود).
PENDING_INPUT_FLAGS = [
    'awaiting_backup_file', 'awaiting_broadcast_content', 'awaiting_cancel_order_id',
    'awaiting_coupon_create', 'awaiting_force_sub_channel', 'awaiting_free_link',
    'awaiting_fsub_target', 'awaiting_autopost_interval',
    'awaiting_manual_delivery_id', 'awaiting_order_search', 'awaiting_payment_add',
    'awaiting_provider_add', 'awaiting_service_add', 'awaiting_setting_key',
    'awaiting_smm_link', 'awaiting_smm_quantity', 'balance_action',
    'waiting_add_points', 'waiting_add_user_id', 'waiting_ban_user',
    'waiting_check_order', 'waiting_crypto_amount', 'waiting_crypto_txid',
    'waiting_for_code', 'waiting_free_quantity', 'waiting_payment_screenshot',
    'waiting_remove_points', 'waiting_search_user', 'waiting_add_admin',
    'tg_support_request', 'group_support_request',
]


def clear_pending_input_flags(context):
    """يمسح كل أعلام الانتظار المعلّقة دفعة وحدة. يُستدعى أول أي فعل/زر جديد حتى ما تختلط الحالات ببعض."""
    for flag in PENDING_INPUT_FLAGS:
        context.user_data.pop(flag, None)

# حد أدنى مفروض يدويًا لبعض الخدمات المجانية (يتغلب على القيمة الراجعة من المزود لو كانت غير دقيقة)
FREE_SERVICE_MIN_OVERRIDE = {
    "724": 50,  # لايكات انستغرام ريلز + بوست
}
POINTS_PER_REFERRAL = 500
completed_services = 0

# ===================== إعدادات التحقق التلقائي من العملات الرقمية =====================
POINTS_PER_USD = 10000  # كل 1 دولار = 10000 نقطة (حسب جدول الأسعار)
CRYPTO_AMOUNT_TOLERANCE = 0.01  # هامش سماح بسيط لفروقات رسوم الشبكة (1%)
TON_RATE = 0.60  # كل 0.60 TON = 1$

CRYPTO_WALLETS = {
    "ton": "UQDDWf3qjtEe9YwbQ1xpyxDIDkXZHZvVWAf8dTEJb0mLCCsp",
    "usdtbep20": "0x2AF2781b3F24e69Fae30952DBB8737AeC596a573",
    "usdttrc20": "TP8wHFh39SmNyPcf7aWWfyjEoKbdB5cqfa"
}

CRYPTO_NAMES = {
    "ton": "Gram ( تون سابقًا )",
    "usdtbep20": "USDT ( BEP20 )",
    "usdttrc20": "USDT ( TRC20 )"
}

# 🔑 مفتاح BscScan مجاني - سجل حساب على bscscan.com/apis واحصل على مفتاح مجاني وضعه هنا
BSCSCAN_API_KEY = "QS8D44ZT8FM973SEDTKXVQ7MSCFP896BF2"

# عقد USDT الرسمي على شبكة BSC (BEP20) - لا تغيّره
USDT_BEP20_CONTRACT = "0x55d398326f99059ff775485246999027b3197955"


def verify_trc20_transaction(txid, expected_wallet, expected_amount):
    """
    يتحقق من عملية USDT TRC20 عبر Tronscan API العام (بدون الحاجة لمفتاح API).
    يرجع (True, المبلغ_الفعلي) عند النجاح، أو (False, رسالة_الخطأ) عند الفشل.
    """
    try:
        url = f"https://apilist.tronscanapi.com/api/transaction-info?hash={txid}"
        resp = requests.get(url, timeout=15)
        data = resp.json()

        if not data or "confirmed" not in data:
            return False, "لم يتم العثور على عملية بهذا الرقم"

        if not data.get("confirmed", False):
            return False, "العملية لم تتأكد بعد على الشبكة، انتظر قليلاً وحاول مرة أخرى"

        transfers = data.get("trc20TransferInfo", [])
        if not transfers:
            return False, "هذه العملية لا تحتوي على تحويل USDT"

        for t in transfers:
            to_address = t.get("to_address", "")
            symbol = t.get("symbol", "")
            decimals = int(t.get("decimals", 6))
            raw_amount = t.get("amount_str", "0")

            if to_address.lower() == expected_wallet.lower() and symbol == "USDT":
                actual_amount = int(raw_amount) / (10 ** decimals)
                if abs(actual_amount - expected_amount) <= expected_amount * CRYPTO_AMOUNT_TOLERANCE:
                    return True, actual_amount
                else:
                    return False, f"المبلغ غير مطابق (المرسل: {actual_amount} USDT، المطلوب: {expected_amount} USDT)"

        return False, "العنوان المستلم في هذه العملية لا يطابق محفظتنا"

    except Exception as e:
        return False, f"تعذر التحقق من العملية حاليًا، حاول لاحقًا"


def verify_bep20_transaction(txid, expected_wallet, expected_amount):
    """
    يتحقق من عملية USDT BEP20 عبر BscScan API (يحتاج BSCSCAN_API_KEY مجاني).
    يرجع (True, المبلغ_الفعلي) عند النجاح، أو (False, رسالة_الخطأ) عند الفشل.
    """
    try:
        url = "https://api.bscscan.com/api"
        params = {
            "module": "proxy",
            "action": "eth_getTransactionReceipt",
            "txhash": txid,
            "apikey": BSCSCAN_API_KEY
        }
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        result = data.get("result")

        if not result:
            return False, "لم يتم العثور على عملية بهذا الرقم"

        if result.get("status") != "0x1":
            return False, "هذه العملية فاشلة على الشبكة"

        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        logs = result.get("logs", [])

        for log in logs:
            if log.get("address", "").lower() != USDT_BEP20_CONTRACT.lower():
                continue
            topics = log.get("topics", [])
            if len(topics) < 3 or topics[0].lower() != transfer_topic:
                continue

            to_address = "0x" + topics[2][-40:]
            raw_amount = int(log.get("data", "0x0"), 16)
            actual_amount = raw_amount / (10 ** 18)

            if to_address.lower() == expected_wallet.lower():
                if abs(actual_amount - expected_amount) <= expected_amount * CRYPTO_AMOUNT_TOLERANCE:
                    return True, actual_amount
                else:
                    return False, f"المبلغ غير مطابق (المرسل: {actual_amount} USDT، المطلوب: {expected_amount} USDT)"

        return False, "العنوان المستلم في هذه العملية لا يطابق محفظتنا"

    except Exception:
        return False, "تعذر التحقق من العملية حاليًا، حاول لاحقًا"


def verify_ton_transaction(txid, expected_wallet, expected_amount):
    """
    يتحقق من عملية TON عبر TonAPI العام (بدون الحاجة لمفتاح API لعدد استدعاءات محدود).
    يرجع (True, المبلغ_الفعلي) عند النجاح، أو (False, رسالة_الخطأ) عند الفشل.
    """
    try:
        url = f"https://tonapi.io/v2/blockchain/transactions/{txid}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return False, "لم يتم العثور على عملية بهذا الرقم"

        data = resp.json()
        in_msg = data.get("in_msg", {})
        destination = in_msg.get("destination", {})
        dest_address = destination.get("address", "") if isinstance(destination, dict) else ""
        raw_value = in_msg.get("value", 0)
        actual_amount = raw_value / (10 ** 9)

        if not dest_address:
            return False, "لم يتم العثور على تفاصيل الوجهة بهذه العملية"

        if dest_address.lower() not in expected_wallet.lower():
            return False, "العنوان المستلم في هذه العملية لا يطابق محفظتنا"

        if abs(actual_amount - expected_amount) <= max(expected_amount * CRYPTO_AMOUNT_TOLERANCE, 0.01):
            return True, actual_amount
        else:
            return False, f"المبلغ غير مطابق (المرسل: {actual_amount} TON، المطلوب: {expected_amount} TON)"

    except Exception:
        return False, "تعذر التحقق من العملية حاليًا، حاول لاحقًا"


def verify_crypto_transaction(currency_key, txid, expected_amount):
    """موزّع التحقق حسب نوع العملة"""
    wallet = CRYPTO_WALLETS.get(currency_key)
    if currency_key == "usdttrc20":
        return verify_trc20_transaction(txid, wallet, expected_amount)
    elif currency_key == "usdtbep20":
        return verify_bep20_transaction(txid, wallet, expected_amount)
    elif currency_key == "ton":
        return verify_ton_transaction(txid, wallet, expected_amount)
    return False, "عملة غير مدعومة"

# ===================== متغيرات روابط الدفع =====================
INVOICE_LINKS = {}
DONATE_LINK = None

# ===================== قاعدة البيانات تبقى محفوظة بين كل تشغيل وآخر =====================
# (تمت إزالة الحذف التلقائي القديم الذي كان يمسح كل بيانات المستخدمين والنقاط عند كل إعادة تشغيل)

# ===================== دالة إنشاء قاعدة البيانات =====================
def init_db():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    
    # جدول المستخدمين (مع جميع الأعمدة)
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, 
                  last_daily_date TEXT, 
                  last_game_date TEXT,
                  points INTEGER DEFAULT 0,
                  total_invites INTEGER DEFAULT 0,
                  total_transfers INTEGER DEFAULT 0,
                  total_purchases INTEGER DEFAULT 0,
                  balance INTEGER DEFAULT 0,
                  stars INTEGER DEFAULT 0,
                  is_banned INTEGER DEFAULT 0,
                  join_date TEXT,
                  last_active TEXT,
                  username TEXT,
                  first_name TEXT)''')
    
    # جدول النشاطات
    c.execute('''CREATE TABLE IF NOT EXISTS user_activities 
                 (user_id INTEGER, activity_type TEXT, activity_date TEXT, points_earned INTEGER)''')
    
    # جدول الإحالات
    c.execute('''CREATE TABLE IF NOT EXISTS referrals 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  referrer_id INTEGER,
                  referred_id INTEGER,
                  date TEXT,
                  completed INTEGER DEFAULT 0)''')
    
    # جدول المشتريات
    c.execute('''CREATE TABLE IF NOT EXISTS purchases 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  service_name TEXT,
                  stars INTEGER,
                  price INTEGER,
                  purchase_number INTEGER,
                  date TEXT,
                  status TEXT,
                  service_id TEXT,
                  link TEXT,
                  quantity INTEGER,
                  provider_order_id TEXT,
                  profit INTEGER,
                  source TEXT DEFAULT 'gifts')''')
    
    # جدول العداد العام
    c.execute('''CREATE TABLE IF NOT EXISTS global_counter 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  last_number INTEGER DEFAULT 0)''')
    
    # جدول الخدمات المكتملة
    c.execute('''CREATE TABLE IF NOT EXISTS completed_services 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  service_name TEXT,
                  user_id INTEGER,
                  date TEXT)''')
    
    # جدول عداد الخدمات
    c.execute('''CREATE TABLE IF NOT EXISTS services_counter 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  total_services INTEGER DEFAULT 0)''')
    
    # جدول الإعلانات
    c.execute('''CREATE TABLE IF NOT EXISTS ads 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  ad_text TEXT,
                  duration_hours INTEGER,
                  price INTEGER,
                  currency TEXT,
                  created_at TEXT,
                  status TEXT,
                  approved_at TEXT)''')
    
    
    
    # جدول الخدمات
    c.execute('''CREATE TABLE IF NOT EXISTS services 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  service_id TEXT,
                  name TEXT,
                  category TEXT,
                  provider_id TEXT,
                  provider_service_id TEXT,
                  price INTEGER,
                  min_order INTEGER,
                  max_order INTEGER,
                  status INTEGER DEFAULT 1,
                  description TEXT,
                  image TEXT)''')
    
    # جدول مزودي API
    c.execute('''CREATE TABLE IF NOT EXISTS providers 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  api_url TEXT,
                  api_key TEXT,
                  balance INTEGER DEFAULT 0,
                  currency TEXT,
                  status INTEGER DEFAULT 1,
                  priority INTEGER DEFAULT 0,
                  last_sync TEXT)''')
    
    # جدول السجلات
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  log_date TEXT,
                  admin_id INTEGER,
                  admin_name TEXT,
                  action_type TEXT,
                  target_user INTEGER,
                  value TEXT,
                  result TEXT,
                  ip TEXT,
                  notes TEXT)''')
    
    # جدول الكوبونات
    c.execute('''CREATE TABLE IF NOT EXISTS coupons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE,
                    points INTEGER,
                    max_uses INTEGER,
                    used_count INTEGER DEFAULT 0,
                    created_date TEXT,
                    status INTEGER DEFAULT 1)''')

    # جدول عمليات استخدام الأكواد (يمنع نفس المستخدم من استخدام نفس الكود مرتين)
    c.execute('''CREATE TABLE IF NOT EXISTS coupon_redemptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coupon_id INTEGER,
                    user_id INTEGER,
                    date TEXT,
                    UNIQUE(coupon_id, user_id))''')

    # جدول وسائل الدفع
    c.execute('''CREATE TABLE IF NOT EXISTS payment_methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    details TEXT,
                    sort_order INTEGER DEFAULT 0,
                    status INTEGER DEFAULT 1)''')

    # جدول الإعدادات العامة (key-value)
    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT)''')

    # جدول طلبات الرشق الفعلية (مزود fast70.com)
    c.execute('''CREATE TABLE IF NOT EXISTS smm_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    service_id TEXT,
                    link TEXT,
                    quantity INTEGER,
                    provider_order_id TEXT,
                    status TEXT,
                    date TEXT)''')

    # جدول قنوات الاشتراك الإجباري
    c.execute('''CREATE TABLE IF NOT EXISTS force_sub_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_username TEXT,
                    channel_id TEXT UNIQUE,
                    added_date TEXT,
                    bot_is_admin INTEGER DEFAULT 1)''')

    # جدول موحّد لتتبع "مين انحسب" بكل طلب دعم (تليجرام / كروب) - يمنع احتساب نفس الشخص مرتين بنفس الجولة
    # سواء جانا من إشعار تيليجرام (push) أو من فحصنا المباشر (pull)
    c.execute('''CREATE TABLE IF NOT EXISTS support_request_joined_users (
                    request_type TEXT,
                    request_id INTEGER,
                    user_id INTEGER,
                    joined_date TEXT,
                    PRIMARY KEY (request_type, request_id, user_id))''')

    # جدول الأدمنية الإضافيين اللي ينضافون من لوحة الأدمن (بالإضافة للأدمن الأساسي بـ ADMIN_IDS بالكود)
    c.execute('''CREATE TABLE IF NOT EXISTS extra_admins (
                    user_id INTEGER PRIMARY KEY,
                    added_date TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS crypto_transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  txid TEXT UNIQUE,
                  user_id INTEGER,
                  currency TEXT,
                  amount_usd REAL,
                  points INTEGER,
                  date TEXT)''')

    # جدول طلبات دعم قنوات تليجرام
    c.execute('''CREATE TABLE IF NOT EXISTS tg_channel_support_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  channel_username TEXT,
                  channel_id TEXT,
                  members INTEGER,
                  price INTEGER,
                  currency TEXT,
                  purchase_number INTEGER,
                  status TEXT DEFAULT 'pending',
                  request_date TEXT,
                  admin_id INTEGER,
                  invite_link TEXT,
                  joined_count INTEGER DEFAULT 0)''')

    # جدول طلبات دعم قناتك بالكروب
    c.execute('''CREATE TABLE IF NOT EXISTS group_channel_support_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  channel_username TEXT,
                  channel_id TEXT,
                  members INTEGER,
                  price INTEGER,
                  currency TEXT,
                  purchase_number INTEGER,
                  status TEXT DEFAULT 'pending',
                  request_date TEXT,
                  admin_id INTEGER,
                  invite_link TEXT,
                  joined_count INTEGER DEFAULT 0)''')

    # جدول قنوات الاشتراك الإجباري الخاصة بكروب دعم قناتك بالكروب
    c.execute('''CREATE TABLE IF NOT EXISTS group_force_sub_channels
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  channel_username TEXT,
                  channel_id TEXT UNIQUE,
                  invite_link TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS force_sub_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER DEFAULT 1)''')

    c.execute('INSERT OR IGNORE INTO force_sub_settings (id, enabled) VALUES (1, 1)')

    # إدخال البيانات الافتراضية
    c.execute('INSERT OR IGNORE INTO global_counter (id, last_number) VALUES (1, 0)')
    c.execute('INSERT OR IGNORE INTO services_counter (id, total_services) VALUES (1, 0)')

    # ترحيل: إضافة عمود رابط الدعوة الخاص بالتتبع للقنوات الإجبارية
    try:
        c.execute('ALTER TABLE force_sub_channels ADD COLUMN invite_link TEXT')
    except sqlite3.OperationalError:
        pass

    # ترحيل: إضافة أعمدة تتبع رابط الدعوة وعدد المنضمين لطلبات دعم قنوات تليجرام
    try:
        c.execute('ALTER TABLE tg_channel_support_requests ADD COLUMN invite_link TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        c.execute('ALTER TABLE tg_channel_support_requests ADD COLUMN joined_count INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    # ترحيل: إضافة أعمدة تتبع رابط الدعوة وعدد المنضمين لطلبات دعم قناتك بالكروب
    try:
        c.execute('ALTER TABLE group_channel_support_requests ADD COLUMN invite_link TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        c.execute('ALTER TABLE group_channel_support_requests ADD COLUMN joined_count INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()
    print("✅ تم إنشاء قاعدة البيانات الجديدة بنجاح!")

# ===================== نظام الاشتراك الإجباري متعدد القنوات =====================
def get_force_sub_channels():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT id, channel_username, channel_id, added_date, bot_is_admin, invite_link FROM force_sub_channels')
    rows = c.fetchall()
    conn.close()
    return rows

def add_force_sub_channel(channel_username, channel_id, invite_link=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO force_sub_channels (channel_username, channel_id, added_date, invite_link) VALUES (?, ?, ?, ?)',
                  (channel_username, str(channel_id), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), invite_link))
        conn.commit()
        ok = True
    except sqlite3.IntegrityError:
        # القناة مضافة مسبقاً بالجدول (channel_id فريد) -> نحدّث الرابط والاسم بدل ما نفشل بصمت
        # عشان لو الصف القديم كان فيه رابط معطوب/فارغ من محاولة سابقة فاشلة، ينحدّث بالرابط الصحيح الجديد
        c.execute('UPDATE force_sub_channels SET channel_username = ?, invite_link = ? WHERE channel_id = ?',
                  (channel_username, invite_link, str(channel_id)))
        conn.commit()
        ok = True
    conn.close()
    return ok

def remove_force_sub_channel(channel_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('DELETE FROM force_sub_channels WHERE channel_id = ?', (str(channel_id),))
    conn.commit()
    conn.close()


async def build_fsub_manage_view(bot):
    """يبني نص وأزرار واجهة إدارة القنوات الإجبارية (لوحة الأدمن)، بأسماء القنوات الحقيقية على الأزرار."""
    channels = get_force_sub_channels()
    markup = InlineKeyboardMarkup(row_width=1)
    for _id, username, channel_id, _date, _admin, invite_link in channels:
        try:
            chat = await bot.get_chat(channel_id)
            display_name = chat.title or username
        except Exception:
            display_name = username
        markup.row(InlineKeyboardButton(f"{display_name}", callback_data="noop"))
        markup.row(
            InlineKeyboardButton("🎯 تعيين عدد الانضمامات", callback_data=f"admin_fsub_target_{channel_id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"admin_fsub_del_{channel_id}")
        )
    markup.row(InlineKeyboardButton("➕ إضافة قناة", callback_data="admin_add_channel_btn"))
    markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))

    if channels:
        text = f"<b>🔒 إدارة القنوات الإجبارية</b>\n\nالقنوات المفعّلة حاليًا ({len(channels)}):"
    else:
        text = "<b>🔒 إدارة القنوات الإجبارية</b>\n\nما في قنوات اشتراك إجباري مفعّلة حاليًا."
    return text, markup

def is_force_sub_enabled():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT enabled FROM force_sub_settings WHERE id = 1')
    row = c.fetchone()
    conn.close()
    return bool(row[0]) if row else True

def set_force_sub_enabled(enabled: bool):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE force_sub_settings SET enabled = ? WHERE id = 1', (1 if enabled else 0,))
    conn.commit()
    conn.close()

# ===================== دوال دعم قنوات تليجرام (اشتراك إجباري عبر شراء) =====================
def add_tg_channel_support_request(user_id, channel_username, channel_id, members, price, currency, purchase_number):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO tg_channel_support_requests
                 (user_id, channel_username, channel_id, members, price, currency, purchase_number, status, request_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)''',
              (user_id, channel_username, str(channel_id), members, price, currency, purchase_number,
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def get_tg_channel_support_request_by_purchase(purchase_number):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT id, user_id, channel_username, channel_id, members, price, currency, status
                 FROM tg_channel_support_requests WHERE purchase_number = ?''', (purchase_number,))
    row = c.fetchone()
    conn.close()
    return row

def update_tg_channel_support_status(request_id, status, admin_id=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE tg_channel_support_requests SET status = ?, admin_id = ? WHERE id = ?',
              (status, admin_id, request_id))
    conn.commit()
    conn.close()

def set_tg_request_invite_link(request_id, invite_link):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE tg_channel_support_requests SET invite_link = ? WHERE id = ?', (invite_link, request_id))
    conn.commit()
    conn.close()

def get_active_tg_request_by_invite_link(invite_link):
    """يرجع الطلب الموافق عليه المرتبط برابط دعوة معين (لسا ما اكتمل)."""
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT id, user_id, channel_username, channel_id, members, joined_count, price, currency
                 FROM tg_channel_support_requests
                 WHERE invite_link = ? AND status = 'approved' ''', (invite_link,))
    row = c.fetchone()
    conn.close()
    return row

def credit_join_if_new(request_type, request_id, user_id):
    """
    يسجّل إن هذا المستخدم انحسب بهذا الطلب (تليجرام أو كروب) لأول مرة بهاي الجولة.
    يرجع True لو هذي أول مرة ننسبها له (لازم نزيد العداد)، و False لو كان محسوب مسبقاً (نتجاهله بدون ما نكرر).
    هذا هو الحارس الوحيد لمنع الاحتساب المكرر - سواء جانا الحدث من إشعار تيليجرام أو من فحصنا المباشر.
    """
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO support_request_joined_users (request_type, request_id, user_id, joined_date) VALUES (?, ?, ?, ?)',
                  (request_type, request_id, user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        is_new = True
    except sqlite3.IntegrityError:
        is_new = False
    conn.close()
    return is_new

def get_active_tg_request_by_channel_id(channel_id):
    """احتياطي للقنوات العامة: تيليجرام لا يرفق invite_link بتحديثات الانضمام للقنوات العامة أبداً،
    فنبحث عن أي طلب معتمد نشط لنفس القناة بدل الاعتماد على تطابق الرابط."""
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT id, user_id, channel_username, channel_id, members, joined_count, price, currency, invite_link
                 FROM tg_channel_support_requests
                 WHERE channel_id = ? AND status = 'approved' ''', (str(channel_id),))
    row = c.fetchone()
    conn.close()
    return row

def increment_tg_request_joined(request_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE tg_channel_support_requests SET joined_count = joined_count + 1 WHERE id = ?', (request_id,))
    conn.commit()
    c.execute('SELECT joined_count FROM tg_channel_support_requests WHERE id = ?', (request_id,))
    new_count = c.fetchone()[0]
    conn.close()
    return new_count

# ===================== دوال دعم قناتك بالكروب =====================
def add_group_channel_support_request(user_id, channel_username, channel_id, members, price, currency, purchase_number):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO group_channel_support_requests
                 (user_id, channel_username, channel_id, members, price, currency, purchase_number, status, request_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)''',
              (user_id, channel_username, str(channel_id), members, price, currency, purchase_number,
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def get_group_channel_support_request_by_purchase(purchase_number):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT id, user_id, channel_username, channel_id, members, price, currency, status
                 FROM group_channel_support_requests WHERE purchase_number = ?''', (purchase_number,))
    row = c.fetchone()
    conn.close()
    return row

def update_group_channel_support_status(request_id, status, admin_id=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE group_channel_support_requests SET status = ?, admin_id = ? WHERE id = ?',
              (status, admin_id, request_id))
    conn.commit()
    conn.close()

def set_group_request_invite_link(request_id, invite_link):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE group_channel_support_requests SET invite_link = ? WHERE id = ?', (invite_link, request_id))
    conn.commit()
    conn.close()

def get_active_group_request_by_invite_link(invite_link):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT id, user_id, channel_username, channel_id, members, joined_count, price, currency
                 FROM group_channel_support_requests
                 WHERE invite_link = ? AND status = 'active' ''', (invite_link,))
    row = c.fetchone()
    conn.close()
    return row

def get_active_group_request_by_channel_id(channel_id):
    """احتياطي للقنوات العامة: تيليجرام لا يرفق invite_link بتحديثات الانضمام للقنوات العامة أبداً."""
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT id, user_id, channel_username, channel_id, members, joined_count, price, currency, invite_link
                 FROM group_channel_support_requests
                 WHERE channel_id = ? AND status = 'active' ''', (str(channel_id),))
    row = c.fetchone()
    conn.close()
    return row

def increment_group_request_joined(request_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE group_channel_support_requests SET joined_count = joined_count + 1 WHERE id = ?', (request_id,))
    conn.commit()
    c.execute('SELECT joined_count FROM group_channel_support_requests WHERE id = ?', (request_id,))
    new_count = c.fetchone()[0]
    conn.close()
    return new_count

def get_group_force_sub_channels():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT channel_username, channel_id, invite_link FROM group_force_sub_channels')
    rows = c.fetchall()
    conn.close()
    return rows

def add_group_force_sub_channel(channel_username, channel_id, invite_link=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT id FROM group_force_sub_channels WHERE channel_id = ?', (str(channel_id),))
    if c.fetchone():
        conn.close()
        return False
    c.execute('INSERT INTO group_force_sub_channels (channel_username, channel_id, invite_link) VALUES (?, ?, ?)',
              (channel_username, str(channel_id), invite_link))
    conn.commit()
    conn.close()
    return True

def remove_group_force_sub_channel(channel_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('DELETE FROM group_force_sub_channels WHERE channel_id = ?', (str(channel_id),))
    conn.commit()
    conn.close()


# ===================== نظام الطابور: قناة واحدة فعالة بنفس الوقت =====================
def get_next_queued_group_request():
    """يرجع أقدم طلب بحالة 'queued' (حسب أسبقية موافقة الأدمن)."""
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''SELECT id, user_id, channel_username, channel_id, members, price, currency
                 FROM group_channel_support_requests
                 WHERE status = 'queued' ORDER BY id ASC LIMIT 1''')
    row = c.fetchone()
    conn.close()
    return row


async def activate_group_request(bot, req, admin_id=None):
    """ينشئ رابط الدعوة الخاص بالطلب ويفعّله كقناة الاشتراك الإجباري الحالية بالكروب."""
    req_id, buyer_id, channel_username, channel_id, members, price, currency = req
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=channel_id,
            name=f"دعم قناتك بالكروب - طلب {req_id}"
        )
        invite_link = invite.invite_link
        set_group_request_invite_link(req_id, invite_link)
    except Exception as e:
        print(f"⚠️ تعذر إنشاء رابط دعوة خاص للقناة {channel_username}: {e}")
        for aid in ADMIN_IDS:
            try:
                await bot.send_message(
                    aid,
                    f"<b>⚠️ تعذر إنشاء رابط دعوة للقناة @{channel_username} (طلب {req_id}).\n"
                    f"تأكد أن البوت أدمن بالقناة وعنده صلاحية دعوة المستخدمين، ثم أعد المحاولة يدويًا.</b>",
                    parse_mode='HTML'
                )
            except Exception:
                pass
        return False

    add_group_force_sub_channel(channel_username, channel_id, invite_link)
    update_group_channel_support_status(req_id, 'active', admin_id)
    try:
        await bot.send_message(
            buyer_id,
            f"<b>🔔 حان دور قناتك بالطابور!\n"
            f"قناتك @{channel_username} أصبحت الاشتراك الإجباري بكروب @{GROUP_SUPPORT_USERNAME} الآن ⚜️</b>",
            parse_mode='HTML'
        )
    except Exception:
        pass
    return True


async def activate_next_group_channel_if_needed(bot):
    """لو ما في قناة فعالة حاليًا، يفعّل أقدم طلب بالطابور. لو الطابور فاضي، يبقى الاشتراك على القناة الافتراضية تلقائيًا."""
    if get_group_force_sub_channels():
        return
    nxt = get_next_queued_group_request()
    if nxt:
        # لو تعذر التفعيل (رابط الدعوة)، تبقى القناة بمقدمة الطابور والأدمن انتبلغ بالمشكلة
        # حتى ما يتخطى الدور ترتيب الأسبقية.
        await activate_group_request(bot, nxt)


async def check_user_subscription(bot, user_id, channel_id):
    """يتحقق هل المستخدم مشترك بالقناة المحددة (channel_id يقبل رقم أو @يوزر)."""
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in ('member', 'administrator', 'creator')
    except Exception:
        return False


async def delete_force_sub_message_with_animation(bot, chat_id, message_id, final_text="✅"):
    """
    يحذف رسالة الاشتراك الإجباري بتأثير انتقالي (تعديل النص + إزالة الأزرار ثم الحذف بعد لحظة).
    ملاحظة: تليجرام Bot API ما بيدعم Animation حقيقي متحكم فيه عند الحذف، هاد أقرب تقريب متاح.
    """
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_text)
    except Exception:
        pass
    try:
        await asyncio.sleep(0.6)
    except Exception:
        pass
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def get_current_group_force_sub_channel():
    """
    يرجع القناة الفعّالة حاليًا للاشتراك الإجباري بالكروب: (username, channel_id, invite_link)
    - إذا وجدت قناة مدفوعة فعالة (بالطابور): يرجعها.
    - إذا ما في أي قناة مدفوعة فعالة: يرجع القناة الافتراضية.
    """
    rows = get_group_force_sub_channels()
    if rows:
        username, channel_id, invite_link = rows[0]
        return username, channel_id, invite_link
    return (
        DEFAULT_FORCE_SUB_CHANNEL_USERNAME,
        f"@{DEFAULT_FORCE_SUB_CHANNEL_USERNAME}",
        DEFAULT_FORCE_SUB_CHANNEL_LINK,
    )


async def check_bot_admin_status(channel_id, bot):
    """يتحقق هل البوت أدمن بالقناة وعنده صلاحية دعوة المستخدمين."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(channel_id, me.id)
        status = member.status
        is_admin = status in ('administrator', 'creator')
        can_invite = bool(getattr(member, 'can_invite_users', False)) or status == 'creator'
        return {'is_admin': is_admin, 'can_invite': can_invite, 'status': status}
    except Exception as e:
        return {'is_admin': False, 'can_invite': False, 'status': f'error: {e}'}


async def get_missing_force_sub_channels(bot, user_id):
    if not is_force_sub_enabled():
        return []
    missing = []
    for _id, username, channel_id, _date, _admin, invite_link in get_force_sub_channels():
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            subscribed = member.status in ['member', 'administrator', 'creator']
        except Exception:
            continue
        if not subscribed:
            missing.append((username, channel_id, invite_link))
    return missing

async def build_force_sub_keyboard(bot, missing_channels):
    markup = InlineKeyboardMarkup(row_width=1)
    for item in missing_channels:
        username, channel_id, stored_invite_link = item
        try:
            chat = await bot.get_chat(channel_id)
            display_name = chat.title or username
            if stored_invite_link:
                url = stored_invite_link
            elif chat.username:
                url = f"https://t.me/{chat.username}"
            else:
                invite = await bot.create_chat_invite_link(chat_id=channel_id, member_limit=0)
                url = invite.invite_link
        except Exception:
            display_name = username
            url = stored_invite_link or f"https://t.me/{username.lstrip('@')}"
        markup.add(_PTBInlineKeyboardButton(f"{display_name}", url=url))
    return markup

async def send_force_sub_prompt(bot, chat_id, missing_channels, user_id=None):
    markup = await build_force_sub_keyboard(bot, missing_channels)

    if user_id is not None:
        old = pending_global_force_sub_prompts.pop(user_id, None)
        if old:
            old_chat_id, old_message_id = old
            try:
                await bot.delete_message(old_chat_id, old_message_id)
            except Exception:
                pass

    sent = await bot.send_message(
        chat_id,
        "<b>📬| لطفاً عليك الاشتراك في قنوات البوت أولاً اشترك ثم اضغط /start للتحقق ✅:</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

    if user_id is not None:
        pending_global_force_sub_prompts[user_id] = (sent.chat_id, sent.message_id)


async def refresh_or_clear_global_force_sub_prompt(bot, user_id):
    """
    تُستدعى بعد ما تكتمل/تنحذف قناة اشتراك إجباري عامة.
    تشيك حالة المستخدم يلي عنده رسالة معلّقة: لو ما عاد ناقصه شي تحذف رسالته وتبلغه،
    ولو لسا ناقصه قنوات ثانية تحدّث له الأزرار بس (تشيل زر القناة يلي خلصت).
    """
    pending = pending_global_force_sub_prompts.get(user_id)
    if not pending:
        return
    chat_id, message_id = pending

    try:
        missing = await get_missing_force_sub_channels(bot, user_id)
    except Exception:
        return

    if not missing:
        pending_global_force_sub_prompts.pop(user_id, None)
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        try:
            await bot.send_message(chat_id, "✅ تم التحقق من اشتراكك بنجاح.\n\nأرسل /start للمتابعة.")
        except Exception:
            pass
    else:
        try:
            markup = await build_force_sub_keyboard(bot, missing)
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=markup)
        except Exception:
            pass

# ===================== إرسال طلب رشق فعلي لمزود الخدمة (fast70.com) =====================
def submit_smm_order(service_id, link, quantity):
    """
    يرسل طلب فعلي لمزود الرشق عبر SMM API القياسي (Standard v2).
    يرجع dict: {'success': True, 'order_id': ...} أو {'success': False, 'error': ...}
    """
    try:
        response = requests.post(SMM_API_URL, data={
            'key': API_KEY,
            'action': 'add',
            'service': service_id,
            'link': link,
            'quantity': quantity
        }, timeout=15)
        data = response.json()
        if 'order' in data:
            return {'success': True, 'order_id': data['order']}
        else:
            return {'success': False, 'error': data.get('error', 'خطأ غير معروف من المزود')}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ===================== إرسال طلب فعلي لمزود الخدمات المجانية (perfectfollow.app) =====================
def submit_free_smm_order(service_id, link, quantity):
    """
    يرسل طلب فعلي لمزود الخدمات المجانية عبر SMM API القياسي (Standard v2).
    يرجع dict: {'success': True, 'order_id': ...} أو {'success': False, 'error': ...}
    """
    try:
        response = requests.post(FREE_SMM_API_URL, data={
            'key': FREE_SMM_API_KEY,
            'action': 'add',
            'service': service_id,
            'link': link,
            'quantity': quantity
        }, timeout=15)
        data = response.json()
        if 'order' in data:
            return {'success': True, 'order_id': data['order']}
        else:
            return {'success': False, 'error': data.get('error', 'خطأ غير معروف من المزود')}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    """يجيب سعر الخدمة الحالي (لكل 1000) من المزود مباشرة. يرجع float أو None عند الفشل."""
    try:
        response = requests.post(SMM_API_URL, data={
            'key': API_KEY,
            'action': 'services'
        }, timeout=15)
        services = response.json()
        for s in services:
            if str(s.get('service')) == str(service_id):
                return float(s.get('rate', 0))
        return None
    except Exception:
        return None

def get_smm_service_details(service_id):
    """يجيب تفاصيل الخدمة كاملة (السعر لكل 1000 + أقل وأكبر طلب) من المزود مباشرة.
    يرجع dict {'rate': float, 'min': int, 'max': int} أو None عند الفشل."""
    try:
        response = requests.post(SMM_API_URL, data={
            'key': API_KEY,
            'action': 'services'
        }, timeout=15)
        services = response.json()
        for s in services:
            if str(s.get('service')) == str(service_id):
                return {
                    'rate': float(s.get('rate', 0)),
                    'min': int(float(s.get('min', 0))),
                    'max': int(float(s.get('max', 0)))
                }
        return None
    except Exception:
        return None

def get_free_smm_service_details(service_id):
    """يجيب تفاصيل خدمة مجانية (أقل وأكبر طلب) من مزود الخدمات المجانية مباشرة.
    يرجع dict {'min': int, 'max': int} أو None عند الفشل."""
    try:
        response = requests.post(FREE_SMM_API_URL, data={
            'key': FREE_SMM_API_KEY,
            'action': 'services'
        }, timeout=15)
        services = response.json()
        for s in services:
            if str(s.get('service')) == str(service_id):
                return {
                    'min': int(float(s.get('min', 0))),
                    'max': int(float(s.get('max', 0)))
                }
        return None
    except Exception:
        return None


def check_smm_order_status(order_id):
    """يتحقق من حالة الطلب (pending/in progress/completed/partial/canceled)."""
    try:
        response = requests.post(SMM_API_URL, data={
            'key': API_KEY,
            'action': 'status',
            'order': order_id
        }, timeout=15)
        return response.json()
    except Exception as e:
        return {'error': str(e)}

# ===================== إعدادات عامة (key-value) =====================
def get_setting(key, default=""):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, str(value)))
    conn.commit()
    conn.close()

# ===================== دوال أكواد النقاط (الكوبونات) =====================
def get_coupon_by_code(code):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT id, points, max_uses, used_count, status FROM coupons WHERE code = ?', (code,))
    row = c.fetchone()
    conn.close()
    return row

def has_user_redeemed_coupon(coupon_id, user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT id FROM coupon_redemptions WHERE coupon_id = ? AND user_id = ?', (coupon_id, user_id))
    row = c.fetchone()
    conn.close()
    return row is not None

def redeem_coupon(coupon_id, user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO coupon_redemptions (coupon_id, user_id, date) VALUES (?, ?, ?)',
              (coupon_id, user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    c.execute('UPDATE coupons SET used_count = used_count + 1 WHERE id = ?', (coupon_id,))
    conn.commit()
    conn.close()

def generate_coupon_code(length=4):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

# ===================== النشر التلقائي لكود نقاط جديد =====================
async def auto_post_coupon_job(context: ContextTypes.DEFAULT_TYPE):
    """يشتغل كل مدة محددة: يولّد كود نقاط جديد وينشره بقناة توزيع النقاط."""
    code = generate_coupon_code()
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO coupons (code, points, max_uses, used_count, created_date, status) VALUES (?, ?, ?, 0, ?, 1)',
                  (code, AUTOPOST_COUPON_POINTS, AUTOPOST_COUPON_MAX_USES, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return  # تصادم نادر بالكود، بترسل وحدة جديدة بالمرة الجاية
    conn.close()

    try:
        bot_username = (await context.bot.get_me()).username
    except Exception:
        bot_username = "bot"

    text = (
        f"<b>كود نقاط مجانا : @{bot_username} 🎁\n"
        f"• الكود : </b><code>{code}</code><b>\n"
        f"• اذهب الى متجر النخبة 🏆\n"
        f"• اضغط استخدام كود يتم شحن النقاط 💸</b>\n"
        f"<blockquote><b>#شارك رابط الدعوة لكل شخص يقوم بالدخول ستحصل على 500 نقطه مجاناً 😍</b></blockquote>"
    )
    try:
        await context.bot.send_message(f"@{AUTOPOST_CHANNEL}", text, parse_mode='HTML')
    except Exception as e:
        print(f"❌ فشل نشر كود النقاط التلقائي: {e}")


def schedule_autopost_job(application, minutes):
    """يجدول (أو يعيد جدولة) مهمة النشر التلقائي كل عدد دقائق محدد."""
    if application.job_queue is None:
        print("⚠️ job_queue غير مفعّل بالبيئة (يحتاج تثبيت: pip install \"python-telegram-bot[job-queue]\")")
        return False
    for job in application.job_queue.get_jobs_by_name("autopost_coupon"):
        job.schedule_removal()
    application.job_queue.run_repeating(
        auto_post_coupon_job, interval=minutes * 60, first=10, name="autopost_coupon"
    )
    return True

def log_admin_action(admin_id, admin_name, action_type, target_user=None, value=None, result="success", notes=""):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO logs (log_date, admin_id, admin_name, action_type, target_user, value, result, ip, notes)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), admin_id, admin_name, action_type, target_user, value, result, "", notes))
    conn.commit()
    conn.close()

# ===================== إنشاء قاعدة البيانات =====================
init_db()

def load_extra_admins():
    """يحمّل الأدمنية الإضافيين المخزّنين بقاعدة البيانات ويضيفهم لـ ADMIN_IDS بالذاكرة."""
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM extra_admins')
    rows = c.fetchall()
    conn.close()
    for (uid,) in rows:
        if uid not in ADMIN_IDS:
            ADMIN_IDS.append(uid)

def add_extra_admin(user_id):
    """يضيف أدمن جديد: يخزّنه بقاعدة البيانات (يضل بعد إعادة تشغيل البوت) ويضيفه فورًا لـ ADMIN_IDS."""
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO extra_admins (user_id, added_date) VALUES (?, ?)',
                  (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        added = True
    except sqlite3.IntegrityError:
        added = False
    conn.close()
    if user_id not in ADMIN_IDS:
        ADMIN_IDS.append(user_id)
    return added

load_extra_admins()

# ===================== دوال المستخدم =====================
def get_user_points(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT points FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_points_add(user_id, points):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    current = get_user_points(user_id)
    new_points = current + points
    c.execute('''INSERT INTO users (user_id, points) VALUES (?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET points = excluded.points''', (user_id, new_points))
    conn.commit()
    conn.close()
    return new_points

def update_points_remove(user_id, points):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    current = get_user_points(user_id)
    new_points = current - points
    if new_points < 0:
        new_points = 0
    c.execute('''INSERT INTO users (user_id, points) VALUES (?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET points = excluded.points''', (user_id, new_points))
    conn.commit()
    conn.close()
    return new_points

def is_crypto_txid_used(txid):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT id FROM crypto_transactions WHERE txid = ?', (txid,))
    result = c.fetchone()
    conn.close()
    return result is not None

def save_crypto_transaction(txid, user_id, currency, amount_usd, points):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO crypto_transactions (txid, user_id, currency, amount_usd, points, date)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (txid, user_id, currency, amount_usd, points, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def is_user_banned(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return bool(result and result[0])

def set_user_ban(user_id, banned: bool):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE users SET is_banned = ? WHERE user_id = ?', (1 if banned else 0, user_id))
    conn.commit()
    conn.close()

def get_bot_statistics():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()

    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
    banned_users = c.fetchone()[0]

    c.execute('SELECT COALESCE(SUM(points), 0) FROM users')
    total_points = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM purchases')
    total_purchases = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM purchases WHERE source = 'crypto_recharge'")
    crypto_recharges = c.fetchone()[0]

    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (f'{today}%',))
    new_today = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM referrals')
    total_referrals = c.fetchone()[0]

    conn.close()
    return {
        'total_users': total_users,
        'banned_users': banned_users,
        'total_points': total_points,
        'total_purchases': total_purchases,
        'crypto_recharges': crypto_recharges,
        'new_today': new_today,
        'total_referrals': total_referrals,
    }

def check_user_exists(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_purchase(user_id, service_name, stars, price, status='pending', service_id=None, link=None, quantity=0, provider_order_id=None, profit=0, source='gifts'):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT last_number FROM global_counter')
    last_number = c.fetchone()[0]
    new_number = last_number + 1
    c.execute('UPDATE global_counter SET last_number = ?', (new_number,))
    c.execute('''INSERT INTO purchases 
                 (user_id, service_name, stars, price, purchase_number, date, status, service_id, link, quantity, provider_order_id, profit, source) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, service_name, stars, price, new_number, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
               status, service_id, link, quantity, provider_order_id, profit, source))
    c.execute('UPDATE users SET total_purchases = total_purchases + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return new_number

def get_total_purchases(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM purchases WHERE user_id = ?', (user_id,))
    total = c.fetchone()[0]
    conn.close()
    return total

def get_user_purchases(user_id, source_filter=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    if source_filter:
        c.execute('SELECT service_name, stars, price, purchase_number, date, status, service_id, link, quantity, provider_order_id, profit, source FROM purchases WHERE user_id = ? AND source = ? ORDER BY purchase_number DESC', (user_id, source_filter))
    else:
        c.execute('SELECT service_name, stars, price, purchase_number, date, status, service_id, link, quantity, provider_order_id, profit, source FROM purchases WHERE user_id = ? ORDER BY purchase_number DESC', (user_id,))
    purchases = c.fetchall()
    conn.close()
    return purchases

def get_purchase_by_number(purchase_number, user_id=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    if user_id is not None:
        c.execute('SELECT user_id, service_name, stars, price, purchase_number, date, status, service_id, link, quantity, provider_order_id, profit, source FROM purchases WHERE purchase_number = ? AND user_id = ?', (purchase_number, user_id))
    else:
        c.execute('SELECT user_id, service_name, stars, price, purchase_number, date, status, service_id, link, quantity, provider_order_id, profit, source FROM purchases WHERE purchase_number = ?', (purchase_number,))
    row = c.fetchone()
    conn.close()
    return row

def format_order_date(dt=None):
    """تنسيق التاريخ كما طُلب: السنة-اليوم-الشهر- الساعة:الدقيقة"""
    dt = dt or datetime.now()
    return f"{dt.year}-{dt.day:02d}-{dt.month:02d}- {dt.hour}:{dt.minute:02d}"

def mask_user_id(user_id):
    """يخفي هوية المستخدم ويظهر آخر 5 أرقام فقط، مثال: •••••01570"""
    uid_str = str(user_id)
    return "•••••" + uid_str[-5:]

async def post_order_completion(bot, user_id, service_name, quantity, price, is_free, bot_username, deep_link_payload):
    """ينشر رسالة اكتمال الطلب في قناة اكتمال الطلبات مع زر 'اطلب الآن'."""
    try:
        markup = InlineKeyboardMarkup(row_width=1)
        order_link = f"https://t.me/{bot_username}?start=svc_{deep_link_payload}"
        markup.add(InlineKeyboardButton("اطلب الآن ✅️", url=order_link))
        text = (
            f"<b>🆕️ | طلب جديد تم اكتمالة \n"
            f"👤 | العضو : {mask_user_id(user_id)}\n"
            f"🛒 | الخدمة : {service_name}\n"
            f"🔰 | الكمية : {quantity}\n"
            f"💰 | التكلفة : {price} نقطة \n"
            f"⌚️ | {format_order_date()}\n\n"
            f"🎁 | مجاني : {'نعم' if is_free else 'لا'}\n\n"
            f"★ شكراً لاستخدامك متجر النخبة ♥️</b>"
        )
        await bot.send_message(ORDER_COMPLETION_CHANNEL, text, parse_mode='HTML', reply_markup=markup)
    except Exception as e:
        print(f"❌ فشل نشر رسالة اكتمال الطلب: {e}")

def add_completed_service(service_name, user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO completed_services (service_name, user_id, date) VALUES (?, ?, ?)',
              (service_name, user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    c.execute('UPDATE services_counter SET total_services = total_services + 1')
    conn.commit()
    conn.close()
    global completed_services
    completed_services += 1

def get_total_services():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT total_services FROM services_counter')
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def get_user_info(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT username, first_name, points, balance, stars, is_banned, join_date, last_active, total_purchases FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return {
            'username': result[0] or 'لا يوجد',
            'first_name': result[1] or 'مستخدم',
            'points': result[2] or 0,
            'balance': result[3] or 0,
            'stars': result[4] or 0,
            'is_banned': result[5] or 0,
            'join_date': result[6] or 'غير معروف',
            'last_active': result[7] or 'غير معروف',
            'total_purchases': result[8] or 0
        }
    return None

def log_action(admin_id, admin_name, action_type, target_user=None, value=None, result='success', ip=None, notes=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO logs (log_date, admin_id, admin_name, action_type, target_user, value, result, ip, notes) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), admin_id, admin_name, action_type, target_user, value, result, ip, notes))
    conn.commit()
    conn.close()

# ===================== دوال الهدية اليومية =====================
def can_claim_daily(user_id):
    if user_id in ADMIN_IDS:
        return True
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT last_daily_date FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        try:
            last_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            time_diff = datetime.now() - last_date
            return time_diff.total_seconds() >= 24 * 3600
        except:
            return True
    return True

def update_daily(user_id):
    if user_id in ADMIN_IDS:
        return
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('UPDATE users SET last_daily_date = ? WHERE user_id = ?', (now, user_id))
    conn.commit()
    conn.close()

def get_time_remaining_daily(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT last_daily_date FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        try:
            last_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            next_date = last_date + timedelta(hours=24)
            remaining = next_date - datetime.now()
            if remaining.total_seconds() <= 0:
                return None
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            return hours, minutes
        except:
            return None
    return None

def log_daily_gift(user_id, points):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO user_activities (user_id, activity_type, activity_date, points_earned) VALUES (?, ?, ?, ?)',
              (user_id, "daily_gift", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), points))
    conn.commit()
    conn.close()

def get_daily_count(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM user_activities WHERE user_id = ? AND activity_type = "daily_gift"', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_game_count(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM user_activities WHERE user_id = ? AND activity_type = "game_played"', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

# ===================== دوال لعبة تخمين المربع =====================
def can_play_game(user_id):
    if user_id in ADMIN_IDS:
        return True
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT last_game_date FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        try:
            last_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            time_diff = datetime.now() - last_date
            return time_diff.total_seconds() >= 24 * 3600
        except:
            return True
    return True

def update_game_date(user_id):
    if user_id in ADMIN_IDS:
        return
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('UPDATE users SET last_game_date = ? WHERE user_id = ?', (now, user_id))
    conn.commit()
    conn.close()

def get_next_game_time(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT last_game_date FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        try:
            last_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            next_date = last_date + timedelta(hours=24)
            return next_date
        except:
            return None
    return None

def log_game_played(user_id, points=None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO user_activities (user_id, activity_type, activity_date, points_earned) VALUES (?, ?, ?, ?)',
              (user_id, "game_played", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), points or 0))
    conn.commit()
    conn.close()

# ===================== دوال رابط الدعوة =====================
def get_total_invites(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT total_invites FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def get_top_inviters():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT user_id, total_invites FROM users WHERE total_invites > 0 ORDER BY total_invites DESC LIMIT 3')
    top = c.fetchall()
    conn.close()
    return top

def add_referral(referrer_id, referred_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO referrals (referrer_id, referred_id, date, completed) VALUES (?, ?, ?, ?)', 
              (referrer_id, referred_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 0))
    conn.commit()
    conn.close()

def complete_referral(referred_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT referrer_id, id FROM referrals WHERE referred_id = ? AND completed = 0', (referred_id,))
    referral = c.fetchone()
    if referral:
        referrer_id, ref_id = referral
        c.execute('UPDATE referrals SET completed = 1 WHERE id = ?', (ref_id,))
        c.execute('UPDATE users SET total_invites = total_invites + 1, points = points + ? WHERE user_id = ?', 
                  (POINTS_PER_REFERRAL, referrer_id))
        conn.commit()
        conn.close()
        return referrer_id
    conn.close()
    return None

def update_transfers_count(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('UPDATE users SET total_transfers = total_transfers + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_total_transfers(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT total_transfers FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

# ===================== دوال الكود =====================
active_code = {
    'code': None,
    'points': None,
    'used_count': 0,
    'max_uses': 40,
    'created_at': None
}
used_by_users = set()

custom_code = {
    'code': None,
    'points': None,
    'max_uses': None,
    'used_count': 0,
    'created_at': None,
    'created_by': None
}
custom_code_users = set()
code_reply_sent = {}

# آخر رسالة اشتراك إجباري معلقة بالكروب لكل مستخدم: user_id -> (chat_id, message_id)
# تُستخدم لحذف الرسالة القديمة تلقائيًا (بدل تراكم أكثر من رسالة لنفس العضو)
pending_group_force_sub_warnings = {}

# آخر رسالة اشتراك إجباري عام (بوت-وايد) معلقة لكل عضو: user_id -> (chat_id, message_id)
pending_global_force_sub_prompts = {}

# ===================== إنشاء روابط الدفع =====================
async def create_invoice_links(bot):
    global INVOICE_LINKS, DONATE_LINK

    print("🔄 جاري إنشاء روابط الدفع...")

    star_packages = [
        {"stars": 1, "points": 200, "key": "star_1"},
        {"stars": 2, "points": 400, "key": "star_2"},
        {"stars": 3, "points": 600, "key": "star_3"},
        {"stars": 4, "points": 800, "key": "star_4"},
        {"stars": 5, "points": 1000, "key": "star_5"},
        {"stars": 10, "points": 2000, "key": "star_10"},
        {"stars": 20, "points": 4000, "key": "star_20"},
        {"stars": 30, "points": 6000, "key": "star_30"},
        {"stars": 40, "points": 8000, "key": "star_40"},
        {"stars": 50, "points": 10000, "key": "star_50"}
    ]

    for pkg in star_packages:
        try:
            invoice_link = await bot.create_invoice_link(
                title=f"{pkg['points']} نقطة",
                description=f"شحن {pkg['points']} نقطة في متجر النخبة",
                payload=f"recharge_{pkg['stars']}_{pkg['points']}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(f"{pkg['points']} نقطة", pkg['stars'])]
            )
            INVOICE_LINKS[pkg['key']] = invoice_link
            print(f"✅ تم إنشاء رابط شحن {pkg['stars']} ⭐️ = {pkg['points']} نقطة")
        except Exception as e:
            print(f"❌ خطأ في إنشاء رابط شحن {pkg['stars']} ⭐️: {e}")

    tgsupport_packages = [
        {"members": 100, "stars": 75, "key": "tgsupport_100"},
        {"members": 200, "stars": 130, "key": "tgsupport_200"},
        {"members": 300, "stars": 200, "key": "tgsupport_300"}
    ]

    for pkg in tgsupport_packages:
        try:
            invoice_link = await bot.create_invoice_link(
                title=f"{pkg['members']} عضو 👤 (دعم قنوات تليجرام)",
                description=f"دعم قنوات تليجرام - {pkg['members']} عضو",
                payload=f"tgsupport_{pkg['members']}_{pkg['stars']}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(f"{pkg['members']} عضو", pkg['stars'])]
            )
            INVOICE_LINKS[pkg['key']] = invoice_link
            print(f"✅ تم إنشاء رابط دعم قنوات تليجرام {pkg['key']} بـ {pkg['stars']} نجمة")
        except Exception as e:
            print(f"❌ خطأ في إنشاء رابط دعم قنوات تليجرام {pkg['key']}: {e}")

    print("✅ تم إنشاء جميع روابط الدفع بنجاح!")

    ad_star_packages = [
        {"hours": 1, "stars": 1, "key": "ad_paid_1"},
        {"hours": 2, "stars": 1, "key": "ad_paid_2"},
        {"hours": 3, "stars": 1, "key": "ad_paid_3"},
        {"hours": 4, "stars": 1, "key": "ad_paid_4"},
        {"hours": 5, "stars": 1, "key": "ad_paid_5"},
    ]

    for pkg in ad_star_packages:
        try:
            invoice_link = await bot.create_invoice_link(
                title=f"إعلان مدفوع لمدة {pkg['hours']} ساعة",
                description=f"نشر إعلان لمدة {pkg['hours']} ساعة في قنوات متجر النخبة",
                payload=f"adpaid_{pkg['hours']}_{pkg['stars']}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(f"إعلان {pkg['hours']} ساعة", pkg['stars'])]
            )
            INVOICE_LINKS[pkg['key']] = invoice_link
            print(f"✅ تم إنشاء رابط دفع إعلان مدفوع لمدة {pkg['hours']} ساعة")
        except Exception as e:
            print(f"❌ خطأ في إنشاء رابط دفع إعلان مدفوع لمدة {pkg['hours']} ساعة: {e}")



# ===================== خريطة الإعدادات الموحّدة =====================
SETTINGS_MAP = {
    "admin_bot_settings": ("اسم/وصف البوت", "bot_name", "متجر النخبة"),
    "admin_api_settings": ("رابط API المزود", "smm_api_url", SMM_API_URL),
    "admin_messages_settings": ("رسالة الترحيب", "welcome_message", "أهلاً بك في متجر النخبة"),
    "admin_language_settings": ("لغة البوت", "language", "العربية"),
    "admin_currency_settings": ("العملة الافتراضية", "currency", "نقطة"),
    "admin_channels_settings": ("القناة الرئيسية للبوت", "main_channel", "غير محددة"),
    "admin_support_settings": ("معرف الدعم الفني", "support_contact", "غير محدد"),
    "admin_terms_settings": ("نص شروط الاستخدام", "terms_text", "لا يوجد نص مخصص بعد"),
    "admin_privacy_settings": ("نص سياسة الخصوصية", "privacy_policy", "لا يوجد نص مخصص بعد"),
    "admin_discount_settings": ("نسبة الخصم الافتراضية %", "default_discount", "0"),
    "admin_services_settings": ("ملاحظة عرض الخدمات", "services_note", "لا توجد ملاحظة"),
    "admin_broadcast_settings": ("توقيع رسائل الإذاعة", "broadcast_signature", "★ متجر النخبة"),
}

# ===================== أمر /start =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id

    if user_id not in ADMIN_IDS and is_user_banned(user_id):
        await message.reply_text("🚫 تم حظرك من استخدام هذا البوت.")
        return

    text = message.text

    missing = await get_missing_force_sub_channels(context.bot, user_id)
    if missing:
        # نحفظ أي payload (دعوة/طلب خدمة) قبل ما نوقفه بجدار الاشتراك الإجباري،
        # حتى ما تنضاع لما يرجع يضغط /start عادي بعد ما يشترك (بدون الرابط الأصلي).
        if text and len(text.split()) > 1:
            context.user_data['pending_start_payload'] = text
        await send_force_sub_prompt(context.bot, message.chat.id, missing, user_id=user_id)
        return

    if (not text or text.strip() == '/start') and 'pending_start_payload' in context.user_data:
        text = context.user_data.pop('pending_start_payload')

    is_new_user = not check_user_exists(user_id)

    # ===== تسجيل/تحديث بيانات المستخدم فور اجتيازه الاشتراك الإجباري =====
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO users (user_id, username, first_name, join_date, last_active) VALUES (?, ?, ?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET
                     username = excluded.username,
                     first_name = excluded.first_name,
                     last_active = excluded.last_active''',
              (user_id, message.from_user.username or '', message.from_user.first_name or '',
               datetime.now().strftime('%Y-%m-%d %H:%M:%S'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

    # ===== إشعار الأدمن بانضمام مستخدم جديد (مرة واحدة فقط لكل شخص) =====
    if is_new_user:
        username_display = f"@{message.from_user.username}" if message.from_user.username else "لا يوجد يوزر"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"<b>🆕 لقد انضم {message.from_user.first_name or user_id} إلى البوت</b>\n\n"
                    f"<b>يوزرة: {username_display}</b>\n"
                    f"<b>🆔 الايدي: <code>{user_id}</code></b>",
                    parse_mode='HTML'
                )
            except:
                pass

    points = get_user_points(user_id)

    # ===== رابط "اطلب الآن ✅️" من رسالة اكتمال الطلب بالقناة =====
    if text and text.startswith('/start svc_'):
        payload = text.split(' ', 1)[1][len('svc_'):]

        if payload.startswith('free_'):
            await send_free_service_selection(context.bot, message.chat.id, context, payload)
        else:
            await send_smm_service_selection(context.bot, message.chat.id, context, payload)
        return

    if text and text.startswith('/start '):
        try:
            referrer_id = int(text.split()[1])
            if referrer_id != user_id:
                if is_new_user:
                    add_referral(referrer_id, user_id)
                completed = complete_referral(user_id)
                if completed:
                    user_name = message.from_user.first_name or "المستخدم"
                    await context.bot.send_message(
                        referrer_id,
                        f"<b>لقد قام {user_name} بالانضمام عبر رابط دعوتك ♥️\nلقد حصلت على {POINTS_PER_REFERRAL} نقطة 💎</b>",
                        parse_mode='HTML'
                    )
                    await context.bot.send_message(
                        user_id,
                        "<b>لقد قمت بالانضمام عبر رابط دعوة صديقك ♥️</b>",
                        parse_mode='HTML'
                    )
        except:
            pass
    
    total_services = get_total_services()
    
    welcome_text = (
        f"اهـلاَ بك عزيزي في متجر النخبة - Store\n"
        f"المتجر يوفر لك جميع الميزات المميزة \n"
        f"نقاطك 💎 | {points}\n"
        f"ايديك 🆔️ | `{user_id}`"
    )
    
    markup = InlineKeyboardMarkup(row_width=2)
    
    btn_rashek = InlineKeyboardButton("خدمات رشق 🛒", callback_data="rashek_services", style="success")
    btn1 = InlineKeyboardButton("هدايا وجوائز ⭐️", callback_data="gifts")
    btn2 = InlineKeyboardButton("تجميع النقاط 💎", callback_data="collect")
    btn3 = InlineKeyboardButton("تحويل النقاط ♻️", callback_data="transfer")
    btn4 = InlineKeyboardButton("استخدام الكود 💳", callback_data="use_code")
    btn5 = InlineKeyboardButton("مشترياتي 🛍", callback_data="my_purchases")
    btn6 = InlineKeyboardButton("معلومات حسابي 🤖", callback_data="my_info")
    btn7 = InlineKeyboardButton("شحن النقاط 💰", callback_data="recharge")
    btn_terms = InlineKeyboardButton("شروط البوت 📛", callback_data="terms_of_use", style="danger")
    btn8 = InlineKeyboardButton("اكتمال الطلبات 🏆", url="https://t.me/NNL38")
    btn_my_orders = InlineKeyboardButton("طلباتي 🗓", callback_data="my_orders", style="primary")
    btn_check_order = InlineKeyboardButton("فحص الطلب 🔍", callback_data="check_order", style="primary")
    btn_updates = InlineKeyboardButton("تحديثات البوت 🚀", callback_data="bot_updates", style="primary")
    btn_api = InlineKeyboardButton("واجهة ( API )", callback_data="noop", style="primary")
    btn10 = InlineKeyboardButton(f"عدد الخدمات المكتملة : {total_services} ✅️", callback_data="noop", style="success")
    
    markup.row(btn_rashek)
    markup.row(btn1)
    markup.row(btn2, btn3)
    markup.row(btn4, btn5)
    markup.row(btn6, btn7)
    markup.row(btn_my_orders, btn_check_order)
    markup.row(btn8, btn_terms)
    markup.row(btn_updates, btn_api)
    markup.row(btn10)
    
    if user_id in ADMIN_IDS:
        markup.row(InlineKeyboardButton("لوحة الأدمن 👑", callback_data="admin_panel", style="success"))
    
    await context.bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

async def send_smm_service_selection(bot, chat_id, context, call_data, message_id=None):
    """يعرض رسالة اختيار خدمة رشق مدفوعة. إذا تم تمرير message_id يعدّل نفس الرسالة (زر)، وإلا يرسل رسالة جديدة (رابط مباشر)."""
    service_id = call_data.split("_", 1)[1]
    details = get_smm_service_details(service_id)
    if details is None:
        error_text = "❌ تعذّر جلب بيانات هذه الخدمة حاليًا من المزود، حاول لاحقًا."
        if message_id:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_text)
        else:
            await bot.send_message(chat_id, error_text)
        return

    price_per_1000_points = round(details['rate'] * SMM_PROFIT_MARGIN * POINTS_PER_USD)
    service_name = SMM_SERVICE_NAMES.get(call_data, f"خدمة #{service_id}")

    context.user_data['smm_service_id'] = service_id
    context.user_data['smm_call_data'] = call_data
    context.user_data['smm_price_per_1000'] = price_per_1000_points
    context.user_data['smm_min_order'] = details['min']
    context.user_data['smm_max_order'] = details['max']
    context.user_data['awaiting_smm_quantity'] = True

    text = (
        f"💎| اسم الخدمة : <b>{service_name}</b>\n"
        f"💎| السعر : لكل 1000⇐ {price_per_1000_points} نقطة\n"
        f"⚡| اقل طلب : {details['min']}\n"
        f"🚀| اكبر طلب : {details['max']}\n\n"
        f"🔰| ارسل العدد الذي تريدة !"
    )

    platform_back_menu = {
        "insta": "rashek_instagram", "fb": "rashek_facebook", "tiktok": "rashek_tiktok",
        "telegram": "rashek_telegram", "youtube": "rashek_youtube", "kick": "rashek_kick",
        "kwai": "rashek_kwai", "spotify": "rashek_spotify", "twitter": "rashek_twitter",
        "twitch": "rashek_twitch", "trovo": "rashek_trovo", "whatsapp": "rashek_whatsapp",
    }
    platform_prefix = call_data.split("_", 1)[0]
    back_callback = platform_back_menu.get(platform_prefix, "rashek_services")

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data=back_callback, style="danger"))

    if message_id:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode='HTML', reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

async def send_free_service_selection(bot, chat_id, context, call_data):
    """يعرض رسالة اختيار خدمة مجانية (مستخدمة من الزر ومن الرابط المباشر 'اطلب الآن')."""
    service_names = {
        "free_728": "متابعين انستغرام مجاني - جودة عالية جدا",
        "free_694": "مشاهدات استوري انستكرام - سريع",
        "free_615": "مشاهدات انستكرام - فيديو ريلز - سريع",
        "free_687": "مشاركات انستكرام اكسبلور",
        "free_724": "لايكات انستكرام ريلز + بوست",
        "free_616": "مشاهدات فيديو تيك توك",
        "free_693": "تيك توك - حفظ الفيديو",
        "free_614": "مشاهدات تليكرام للبوست",
        "free_690": "تفاعلات تليكرام ايجابية",
        "free_691": "تفاعلات تليكرام سلبية"
    }
    service_name = service_names.get(call_data, "خدمة مجانية")
    service_id = call_data.split("_", 1)[1]

    details = get_free_smm_service_details(service_id)
    if details is None:
        await bot.send_message(chat_id, "❌ تعذّر جلب بيانات هذه الخدمة حاليًا من المزود، حاول لاحقًا.")
        return

    min_order = max(details['min'], FREE_SERVICE_MIN_OVERRIDE.get(service_id, 0))
    max_order = max(details['max'], min_order)

    context.user_data['free_service'] = call_data
    context.user_data['free_service_id'] = service_id
    context.user_data['free_service_name'] = service_name
    context.user_data['free_min'] = min_order
    context.user_data['free_max'] = max_order
    context.user_data['awaiting_free_link'] = True

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_free", style="danger"))

    await bot.send_message(
        chat_id,
        f"💎| اسم الخدمة : <b>{service_name}</b>\n"
        f"💰| السعر : مجاني بالكامل 🎁\n\n"
        f"🔗| أرسل الآن رابط الحساب/المنشور المطلوب تنفيذ الخدمة عليه:",
        parse_mode='HTML',
        reply_markup=markup
    )

# ===================== معالج الأزرار =====================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    call = update.callback_query
    try:
        if call.from_user.id not in ADMIN_IDS and is_user_banned(call.from_user.id):
            await call.answer("🚫 تم حظرك من استخدام هذا البوت.", show_alert=True)
            return

        # أي ضغطة زر جديدة تلغي تلقائيًا أي "انتظار" سابق عالق (رابط/كمية/مبلغ...الخ)
        # ما عدا الزر يلي وظيفته بالتحديد إنه يبلش انتظار جديد (بيحطه هو بعد هالسطر).
        clear_pending_input_flags(context)

        # ===================== طلب خدمة رشق فعلية (انستقرام/فيسبوك/تيك توك/تيليجرام) =====================
        if (call.data.startswith("insta_") or call.data.startswith("fb_")
              or call.data.startswith("tiktok_") or call.data.startswith("telegram_")
              or call.data.startswith("youtube_") or call.data.startswith("ad_paid_")
              or call.data.startswith("kick_") or call.data.startswith("kwai_")
              or call.data.startswith("spotify_") or call.data.startswith("twitter_")
              or call.data.startswith("twitch_") or call.data.startswith("trovo_")
              or call.data.startswith("whatsapp_")):
            await call.answer()
            await send_smm_service_selection(context.bot, call.message.chat.id, context, call.data, message_id=call.message.message_id)

        # ===================== تأكيد/إلغاء طلب الرشق =====================
        elif call.data == "smm_confirm":
            user_id = call.from_user.id
            service_id = context.user_data.get('smm_service_id')
            smm_call_data = context.user_data.get('smm_call_data', f"insta_{service_id}")
            link = context.user_data.get('smm_link')
            quantity = context.user_data.get('smm_quantity')
            total_price = context.user_data.get('smm_total_price')

            if not all([service_id, link, quantity, total_price]):
                await call.answer("❌ انتهت صلاحية الطلب، ابدأ من جديد.", show_alert=True)
                return

            current_points = get_user_points(user_id)
            if current_points < total_price:
                await call.answer("❌ رصيدك غير كافٍ!", show_alert=True)
                return

            await call.answer()
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="⏳ جاري إرسال طلبك لمزود الخدمة..."
            )

            result = submit_smm_order(service_id, link, quantity)
            service_name = SMM_SERVICE_NAMES.get(smm_call_data, f"خدمة #{service_id}")

            if result.get('success'):
                conn = sqlite3.connect('bot_database.db')
                c = conn.cursor()
                c.execute('UPDATE users SET points = points - ? WHERE user_id = ?', (total_price, user_id))
                c.execute('''INSERT INTO smm_orders (user_id, service_id, link, quantity, provider_order_id, status, date)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (user_id, service_id, link, quantity, str(result['order_id']), 'submitted',
                           datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()

                purchase_number = add_purchase(
                    user_id, service_name, 0, total_price, 'completed',
                    service_id=service_id, link=link, quantity=quantity,
                    provider_order_id=str(result['order_id']), source='rashek_paid'
                )

                new_points_balance = get_user_points(user_id)

                await context.bot.edit_message_text(
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    text=(
                        f"<b>✅| تم استلام طلبك : {service_name}\n"
                        f"💰| التكلفة: {total_price} نقطة\n"
                        f"🆔| ايدي الطلب: {purchase_number}\n"
                        f"💎| نقاطك الحالية: {new_points_balance} نقطة\n"
                        f"🔎| لمعرفة حالة طلبك استخدم زر فحص الطلب</b>"
                    ),
                    parse_mode='HTML'
                )

                try:
                    bot_username = (await context.bot.get_me()).username
                    await post_order_completion(
                        context.bot, user_id, service_name, quantity, total_price,
                        is_free=False, bot_username=bot_username, deep_link_payload=smm_call_data
                    )
                except Exception as e:
                    print(f"❌ فشل نشر رسالة اكتمال الطلب: {e}")

                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            admin_id,
                            f"📥 طلب رشق جديد\nمستخدم: {user_id}\nخدمة: {service_id}\nرابط: {link}\nكمية: {quantity}\n💎السعر: {total_price}\nرقم طلب المزود: {result['order_id']}"
                        )
                    except Exception:
                        pass
            else:
                await context.bot.edit_message_text(
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    text=f"❌ فشل تنفيذ الطلب: {result.get('error', 'خطأ غير معروف')}\n\nلم يتم خصم أي نقاط من رصيدك."
                )

            for key in ('smm_service_id', 'smm_call_data', 'smm_link', 'smm_quantity', 'smm_total_price', 'smm_price_per_1000', 'smm_min_order', 'smm_max_order'):
                context.user_data.pop(key, None)

        elif call.data == "smm_cancel":
            for key in ('smm_service_id', 'smm_link', 'smm_quantity', 'smm_total_price', 'smm_price_per_1000'):
                context.user_data.pop(key, None)
            await call.answer("تم إلغاء الطلب")
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="❌ تم إلغاء الطلب."
            )

        # ===================== زر تحقق من الاشتراك الإجباري =====================
        elif call.data == "force_sub_verify":
            user_id = call.from_user.id
            missing = await get_missing_force_sub_channels(context.bot, user_id)
            if missing:
                await call.answer("❌ لم تكمل الاشتراك بعد.", show_alert=True)
                return
            await call.answer()
            pending_global_force_sub_prompts.pop(user_id, None)
            try:
                await context.bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            await context.bot.send_message(call.message.chat.id, "✅ تم التحقق من اشتراكك بنجاح.\n\nأرسل /start للمتابعة.")
            return

        # ===================== إدارة الاشتراك الإجباري (لوحة الأدمن) =====================
        # ===================== لوحة الأدمن =====================
        elif call.data == "admin_panel":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return

            markup = InlineKeyboardMarkup(row_width=2)
            btn_add = InlineKeyboardButton("➕ إضافة نقاط", callback_data="admin_add_points_btn")
            btn_remove = InlineKeyboardButton("➖ خصم نقاط", callback_data="admin_remove_points_btn")
            btn_reset = InlineKeyboardButton("🗑 تصفير نقاط الجميع", callback_data="admin_reset_all_points")
            btn_channel = InlineKeyboardButton("🔒 إدارة القنوات الإجبارية", callback_data="admin_fsub_manage")
            btn_stats = InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats")
            btn_broadcast = InlineKeyboardButton("📣 إذاعة المستخدمين", callback_data="admin_broadcast_btn")
            btn_ban = InlineKeyboardButton("🚫 حظر المستخدمين", callback_data="admin_ban_btn")
            btn_coupon = InlineKeyboardButton("🎁 إنشاء كود نقاط", callback_data="admin_coupon_btn")
            btn_autopost = InlineKeyboardButton("📢 نشر تلقائي", callback_data="admin_autopost_btn")
            btn_autopost_stop = InlineKeyboardButton("⏹ إيقاف النشر التلقائي", callback_data="admin_autopost_stop")
            btn_add_admin = InlineKeyboardButton("👤 إضافة أدمن", callback_data="admin_add_admin_btn")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")

            markup.row(btn_add, btn_remove)
            markup.row(btn_reset)
            markup.row(btn_channel)
            markup.row(btn_stats)
            markup.row(btn_broadcast)
            markup.row(btn_ban)
            markup.row(btn_coupon, btn_autopost)
            markup.row(btn_autopost_stop)
            markup.row(btn_add_admin)
            markup.row(btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>👑 لوحة تحكم الأدمن</b>\n\nاختر الإجراء الذي تريده:",
                parse_mode='HTML',
                reply_markup=markup
            )

        # ===== زر: إضافة نقاط =====
        elif call.data == "admin_add_points_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['waiting_add_points'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>➕ إضافة نقاط</b>\n\nأرسل: ايدي_المستخدم عدد_النقاط\n\nمثال: 123456789 1000",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: إضافة أدمن =====
        elif call.data == "admin_add_admin_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['waiting_add_admin'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>👤 إضافة أدمن</b>\n\nأرسل آيدي المستخدم اللي تريد تسويه أدمن.\n\nمثال: 123456789",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: خصم نقاط =====
        elif call.data == "admin_remove_points_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['waiting_remove_points'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>➖ خصم نقاط</b>\n\nأرسل: ايدي_المستخدم عدد_النقاط\n\nمثال: 123456789 500",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: تصفير نقاط الجميع (يطلب تأكيد) =====
        elif call.data == "admin_reset_all_points":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            markup = InlineKeyboardMarkup(row_width=2)
            btn_confirm = InlineKeyboardButton("✅ نعم، تصفير الكل", callback_data="admin_reset_all_points_confirm", style="danger")
            btn_cancel = InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")
            markup.row(btn_confirm, btn_cancel)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>⚠️ تحذير</b>\n\nهذا الإجراء سيصفّر نقاط جميع المستخدمين بدون استثناء ولا يمكن التراجع عنه.\n\nهل أنت متأكد؟",
                parse_mode='HTML', reply_markup=markup
            )

        elif call.data == "admin_reset_all_points_confirm":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('UPDATE users SET points = 0')
            affected = c.rowcount
            conn.commit()
            conn.close()
            log_admin_action(call.from_user.id, call.from_user.first_name or "أدمن", "reset_all_points", value=f"{affected} مستخدم")
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=f"✅ تم تصفير نقاط جميع المستخدمين ({affected} مستخدم).",
                reply_markup=markup
            )

        # ===== زر: إضافة قناة إجبارية =====
        elif call.data == "admin_add_channel_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['awaiting_force_sub_channel'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_fsub_manage", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>📢 إضافة قناة اشتراك إجباري</b>\n\n"
                     "أرسل معرف القناة (مثال: @channel) أو الآيدي الرقمي.\n\n"
                     "⚠️ تأكد أن البوت أدمن بالقناة قبل الإرسال.",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: إدارة القنوات الإجبارية (قائمة + حذف + تعيين هدف) =====
        elif call.data == "admin_fsub_manage":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            text, markup = await build_fsub_manage_view(context.bot)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=text, parse_mode='HTML', reply_markup=markup
            )

        elif call.data.startswith("admin_fsub_del_"):
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            channel_id = call.data[len("admin_fsub_del_"):]
            remove_force_sub_channel(channel_id)
            await call.answer("✅ تم حذف القناة من الاشتراك الإجباري")
            text, markup = await build_fsub_manage_view(context.bot)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=text, parse_mode='HTML', reply_markup=markup
            )

        elif call.data.startswith("admin_fsub_target_"):
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            channel_id = call.data[len("admin_fsub_target_"):]
            channels = get_force_sub_channels()
            channel_username = next(
                (u for (_i, u, cid, _d, _a, _l) in channels if str(cid) == str(channel_id)),
                channel_id
            )
            context.user_data['fsub_target_channel_id'] = channel_id
            context.user_data['fsub_target_channel_username'] = channel_username
            context.user_data['awaiting_fsub_target'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_fsub_manage", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=f"<b>🎯 تعيين عدد الانضمامات — {channel_username}</b>\n\n"
                     f"أرسل العدد المطلوب. رح ينشئ البوت رابط دعوة خاص بهذا العدد بالضبط،\n"
                     f"وبمجرد ما يوصل عدد المنضمين عبره للعدد المطلوب، تنحذف القناة تلقائيًا من الاشتراك الإجباري.\n\n"
                     f"مثال: 200",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: نشر تلقائي لكود نقاط =====
        elif call.data == "admin_autopost_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['awaiting_autopost_interval'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            current = get_setting('autopost_interval_minutes', '')
            current_line = f"\n\n⏱ المدة الحالية المفعّلة: {current} دقيقة" if current else ""
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>📢 نشر تلقائي لكود نقاط</b>\n\n"
                     f"أرسل المدة بالدقائق بين كل نشر وآخر (بينشر بقناة @{AUTOPOST_CHANNEL}).\n\n"
                     f"مثال: 60{current_line}",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: إيقاف النشر التلقائي =====
        elif call.data == "admin_autopost_stop":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return

            was_running = False
            if context.application.job_queue is not None:
                jobs = context.application.job_queue.get_jobs_by_name("autopost_coupon")
                for job in jobs:
                    job.schedule_removal()
                    was_running = True

            set_setting('autopost_interval_minutes', '')

            if was_running:
                await call.answer("⏹ تم إيقاف النشر التلقائي", show_alert=True)
            else:
                await call.answer("ما في نشر تلقائي شغّال حالياً", show_alert=True)

        # ===== زر: إحصائيات البوت =====
        elif call.data == "admin_stats":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            stats = get_bot_statistics()
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=f"<b>📊 إحصائيات البوت</b>\n\n"
                     f"👥 إجمالي المستخدمين: {stats['total_users']}\n"
                     f"🆕 مستخدمين جدد اليوم: {stats['new_today']}\n"
                     f"🚫 محظورين: {stats['banned_users']}\n"
                     f"💎 مجموع نقاط جميع المستخدمين: {stats['total_points']}\n"
                     f"🛒 إجمالي الطلبات: {stats['total_purchases']}\n"
                     f"💰 عمليات شحن عملات رقمية: {stats['crypto_recharges']}\n"
                     f"🔗 إجمالي الإحالات: {stats['total_referrals']}",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: إذاعة المستخدمين =====
        elif call.data == "admin_broadcast_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['awaiting_broadcast_content'] = True
            context.user_data['broadcast_mode'] = 'admin_broadcast_text'
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>📣 إذاعة للمستخدمين</b>\n\nأرسل نص الرسالة التي تريد إذاعتها لجميع المستخدمين.",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: حظر المستخدمين =====
        elif call.data == "admin_ban_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['waiting_ban_user'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>🚫 حظر / فك حظر مستخدم</b>\n\n"
                     "أرسل ايدي المستخدم.\n"
                     "(لو كان محظورًا مسبقًا، سيتم فك الحظر عنه تلقائيًا)",
                parse_mode='HTML', reply_markup=markup
            )

        # ===== زر: إنشاء كود نقاط =====
        elif call.data == "admin_coupon_btn":
            if call.from_user.id not in ADMIN_IDS:
                await call.answer("❌ هذا الأمر للأدمن فقط!", show_alert=True)
                return
            context.user_data['awaiting_coupon_create'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="admin_panel", style="danger"))
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="<b>🎁 إنشاء كود نقاط</b>\n\n"
                     "أرسل بالصيغة: الكود | النقاط | عدد الاستخدامات\n\n"
                     "مثال: ELITE100 | 1000 | 50",
                parse_mode='HTML', reply_markup=markup
            )

        # ===================== فحص الطلب =====================
        elif call.data == "check_order":
            await call.answer()
            context.user_data['waiting_check_order'] = True
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            markup.add(btn_back)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="ارسل رقم الخدمة 🔍",
                reply_markup=markup
            )

        # ===================== طلباتي (طلبات خدمات الرشق المدفوعة) =====================
        elif call.data == "my_orders":
            user_id = call.from_user.id
            orders = get_user_purchases(user_id, source_filter='rashek_paid')

            if not orders:
                await call.answer("لم تقم بشراء أي طلب❗️", show_alert=True)
                return

            markup = InlineKeyboardMarkup(row_width=1)
            for order in orders:
                service_name, stars, price, purchase_number, date, status, service_id, link, quantity, provider_order_id, profit, source = order
                markup.add(InlineKeyboardButton(service_name, callback_data=f"order_detail_{purchase_number}"))
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger"))

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤖| مرحبا بك في قسم طلباتي\n⚜️| هنا طلباتك التي طلبتها من خدمات الرشق</b>",
                parse_mode='HTML',
                reply_markup=markup
            )

        # ===================== تفاصيل طلب من طلباتي =====================
        elif call.data.startswith("order_detail_"):
            user_id = call.from_user.id
            purchase_number = int(call.data.replace("order_detail_", ""))
            order = get_purchase_by_number(purchase_number, user_id=user_id)

            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="my_orders", style="danger"))

            if not order:
                await context.bot.edit_message_text(
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    text="❌ لم يتم العثور على هذا الطلب.", reply_markup=markup
                )
                return

            (o_user_id, service_name, stars, price, p_number, date, status,
             service_id, link, quantity, provider_order_id, profit, source) = order

            status_text = "اكتمل الطلب بنجاح !" if status == 'completed' else status
            try:
                dt = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
                date_display = format_order_date(dt)
            except Exception:
                date_display = date

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=(
                    f"<b>تفاصيل الطلب :\n\n"
                    f"🛒 | الخدمة : {service_name}\n"
                    f"🔰 | الكمية : {quantity}\n"
                    f"💰 | السعر : {price} نقطة \n"
                    f"📅 | تاريخ الطلب : {date_display}\n"
                    f"🔗 | رابط الطلب : {link or '—'}\n"
                    f"✅️ | حالة الطلب : {status_text}</b>"
                ),
                parse_mode='HTML',
                reply_markup=markup
            )

        # ===================== زر شروط استخدام البوت =====================
        elif call.data == "terms_of_use":
            markup = InlineKeyboardMarkup(row_width=1)
            btn_support = InlineKeyboardButton("الدعم الفني 🧑‍🔧", url="https://t.me/NN25LL", style=None)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style=None)
            markup.add(btn_support)
            markup.add(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>📜 شروط استخدام بوت متجر النخبة\n\n"
                     "👋 أهلاً وسهلاً بك في بوت متجر النخبة، يرجى قراءة الشروط التالية بعناية قبل إنشاء أي طلب.\n\n"
                     "━━━━━━━━━━━━━━━━━━\n\n"
                     "⚠️ شروط الاستخدام\n\n"
                     "🔹 عند تغيير معرف الحساب (Username) أثناء تنفيذ الطلب، يُعتبر الطلب منفذًا جزئيًا، ولا يحق المطالبة بأي تعويض.\n\n"
                     "🔹 في حال حذف المنشور أو الفيديو أثناء تنفيذ الطلب، يُعتبر الطلب مكتملًا، ولا يحق المطالبة بأي تعويض.\n\n"
                     "🔹 إذا قمت بتغيير معرف الحساب بعد اكتمال تنفيذ الطلب، فلن يتم قبول أي طلب تعويض.\n\n"
                     "🔹 يجب أن يكون الحساب أو القناة أو الصفحة عامة (Public) طوال فترة التنفيذ، ولا يتم تنفيذ الطلبات للحسابات الخاصة.\n\n"
                     "🔹 إذا تم تحويل الحساب إلى خاص أثناء التنفيذ، فسيُعتبر الطلب منفذًا جزئيًا، ولن يتم تعويضه.\n\n"
                     "🔹 لا يمكن إلغاء أي طلب بعد إرساله، لذا تأكد من صحة الرابط والخدمة والكمية قبل تأكيد الطلب.\n\n"
                     "🔹 تعتمد جميع خدماتنا على نظام التثبيت التلقائي وفق آلية عمل السيرفرات، وقد تختلف مدة التنفيذ من خدمة إلى أخرى.\n\n"
                     "🔹 يُرجى قراءة تفاصيل كل خدمة قبل إنشاء أي طلب، حيث تختلف مدة التنفيذ والضمان حسب نوع الخدمة.\n\n"
                     "🔹 لا يتم استرداد قيمة أي طلب بعد إرساله، إلا إذا تعذر على النظام تنفيذ الخدمة بالكامل.\n\n"
                     "🔹 إنشاء أي طلب يعني أنك قرأت جميع الشروط والأحكام، ووافقت عليها بالكامل.\n\n"
                     "━━━━━━━━━━━━━━━━━━\n\n"
                     "🤝 التواصل مع الدعم\n\n"
                     "يرجى الالتزام بالاحترام عند التواصل مع فريق الدعم، وأي إساءة أو ألفاظ غير لائقة قد تؤدي إلى حظر حسابك من استخدام البوت.\n\n"
                     "━━━━━━━━━━━━━━━━━━\n\n"
                     "♻️ نظام التعويض التلقائي\n\n"
                     "إذا تعرض الطلب لنقص بعد اكتمال التنفيذ، وكانت الخدمة تدعم التعويض، فسيتم تعويض النقص تلقائيًا وفق مدة الضمان الخاصة بالخدمة.\n\n"
                     "━━━━━━━━━━━━━━━━━━\n\n"
                     "📢 القناة الرسمية للبوت\n"
                     "@NN32J\n\n"
                     "💙 شكرًا لاستخدامكم بوت متجر النخبة، ونتمنى لكم تجربة مميزة.</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
# ===================== خدمات رشق =====================
        elif call.data == "rashek_services":
            markup = InlineKeyboardMarkup(row_width=2)
            btn1 = InlineKeyboardButton("الخدمات المجانية 🎁", callback_data="rashek_free")
            btn2 = InlineKeyboardButton("تليكرام", callback_data="rashek_telegram")
            btn3 = InlineKeyboardButton("انستغرام", callback_data="rashek_instagram")
            btn_telegram_interactions = InlineKeyboardButton("تفاعلات تليكرام", callback_data="soon")
            btn4 = InlineKeyboardButton("تيك توك", callback_data="rashek_tiktok")
            btn5 = InlineKeyboardButton("فيسبوك", callback_data="rashek_facebook")
            btn6 = InlineKeyboardButton("يوتيوب", callback_data="rashek_youtube")
            btn_twitter = InlineKeyboardButton("تويتر", callback_data="rashek_twitter")
            btn_spotify = InlineKeyboardButton("سبوتيفاي", callback_data="rashek_spotify")
            btn_snapchat = InlineKeyboardButton("سناب شات", callback_data="soon")
            btn_kick = InlineKeyboardButton("كيك", callback_data="rashek_kick")
            btn_kwai = InlineKeyboardButton("كواي", callback_data="rashek_kwai")
            btn_trovo = InlineKeyboardButton("تروفو", callback_data="rashek_trovo")
            btn_twitch = InlineKeyboardButton("تويتش", callback_data="rashek_twitch")
            btn_threads = InlineKeyboardButton("ثريدز", callback_data="soon")
            btn_ads_section = InlineKeyboardButton("قسم الإعلانات", callback_data="publish_ad")
            btn_whatsapp = InlineKeyboardButton("واتساب", callback_data="rashek_whatsapp")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            
            markup.row(btn1)
            markup.row(btn2, btn3)
            markup.row(btn_telegram_interactions, btn_whatsapp)
            markup.row(btn4, btn5)
            markup.row(btn6, btn_twitter)
            markup.row(btn_spotify, btn_snapchat)
            markup.row(btn_kick, btn_kwai)
            markup.row(btn_trovo, btn_twitch)
            markup.row(btn_threads)
            markup.row(btn_ads_section)
            markup.row(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="- اهلا بك في قسم خدمات الرشق 😍\n- اختر الخدمة التي تريدها ✅️",
                reply_markup=markup
            )
        
        # ===================== الخدمات المجانية =====================
        elif call.data == "rashek_free":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("لايكات انستغرام ريلز + بوست 🎁", callback_data="free_724")
            btn2 = InlineKeyboardButton("مشاهدات استوري انستكرام - سريع", callback_data="free_694")
            btn3 = InlineKeyboardButton("مشاهدات انستكرام - فيديو ريلز - سريع", callback_data="free_615")
            btn4 = InlineKeyboardButton("مشاركات انستكرام اكسبلور", callback_data="free_687")
            btn5 = InlineKeyboardButton("لايكات انستكرام ريلز + بوست", callback_data="free_724")
            btn6 = InlineKeyboardButton("مشاهدات فيديو تيك توك", callback_data="free_616")
            btn7 = InlineKeyboardButton("تيك توك - حفظ الفيديو", callback_data="free_693")
            btn8 = InlineKeyboardButton("مشاهدات تليكرام للبوست", callback_data="free_614")
            btn9 = InlineKeyboardButton("تفاعلات تليكرام ايجابية (👍🤩🎉🔥❤️🥰👏🏻🥳😍❤️‍🔥💯)", callback_data="free_690")
            btn10 = InlineKeyboardButton("تفاعلات تليكرام سلبية (💔👎😢💩🤮🤬😡🥱😈)", callback_data="free_691")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")
            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="اهلا بك في قسم الخدمات المجانية \nاختر الخدمة الذي تريدها",
                reply_markup=markup
            )
        
        # ===================== اختيار خدمة مجانية =====================
        elif call.data.startswith("free_"):
            user_id = call.from_user.id
            service_id = call.data.split("_", 1)[1]
            service_names = {
                "free_728": "متابعين انستغرام مجاني - جودة عالية جدا",
                "free_694": "مشاهدات استوري انستكرام - سريع",
                "free_615": "مشاهدات انستكرام - فيديو ريلز - سريع",
                "free_687": "مشاركات انستكرام اكسبلور",
                "free_724": "لايكات انستكرام ريلز + بوست",
                "free_616": "مشاهدات فيديو تيك توك",
                "free_693": "تيك توك - حفظ الفيديو",
                "free_614": "مشاهدات تليكرام للبوست",
                "free_690": "تفاعلات تليكرام ايجابية",
                "free_691": "تفاعلات تليكرام سلبية"
            }
            service_name = service_names.get(call.data, "خدمة مجانية")

            details = get_free_smm_service_details(service_id)
            if details is None:
                await call.answer("❌ تعذّر جلب بيانات هذه الخدمة حاليًا من المزود، حاول لاحقًا.", show_alert=True)
                return

            min_order = max(details['min'], FREE_SERVICE_MIN_OVERRIDE.get(service_id, 0))
            max_order = max(details['max'], min_order)

            context.user_data['free_service'] = call.data
            context.user_data['free_service_id'] = service_id
            context.user_data['free_service_name'] = service_name
            context.user_data['free_min'] = min_order
            context.user_data['free_max'] = max_order
            context.user_data['awaiting_free_link'] = True
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_free", style="danger")
            markup.add(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"💎| اسم الخدمة : {service_name}\n"
                     f"💰| السعر : مجاني بالكامل 🎁\n\n"
                     f"🔗| أرسل الآن رابط الحساب/المنشور المطلوب تنفيذ الخدمة عليه:",
                reply_markup=markup
            )
        
        # ===================== تأكيد الطلب المجاني =====================
        elif call.data == "confirm_free_order":
            user_id = call.from_user.id
            service_id = context.user_data.get('free_service_id')
            service_name = context.user_data.get('free_service_name', 'خدمة مجانية')
            link = context.user_data.get('free_link')
            quantity = context.user_data.get('free_quantity', 10)
            free_call_data = context.user_data.get('free_service', 'free_728')

            if not all([service_id, link, quantity]):
                await call.answer("❌ انتهت صلاحية الطلب، ابدأ من جديد.", show_alert=True)
                return

            await call.answer()
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text="⏳ جاري إرسال طلبك لمزود الخدمة..."
            )

            result = submit_free_smm_order(service_id, link, quantity)

            if not result.get('success'):
                await context.bot.edit_message_text(
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    text=f"❌ فشل تنفيذ الطلب: {result.get('error', 'خطأ غير معروف')}"
                )
                for key in ('free_service', 'free_service_id', 'free_service_name', 'free_link', 'free_quantity', 'free_min', 'free_max'):
                    context.user_data.pop(key, None)
                return

            purchase_number = add_purchase(
                user_id, service_name, 0, 0, 'completed',
                service_id=service_id, link=link, quantity=quantity,
                provider_order_id=str(result['order_id']), source='rashek_free'
            )
            add_completed_service(service_name, user_id)

            new_points_balance = get_user_points(user_id)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                text=(
                    f"<b>✅| تم استلام طلبك : {service_name}\n"
                    f"💰| التكلفة: 0 نقطة (مجاني)\n"
                    f"🆔| ايدي الطلب: {purchase_number}\n"
                    f"💎| نقاطك الحالية: {new_points_balance} نقطة\n"
                    f"🔎| لمعرفة حالة طلبك استخدم زر فحص الطلب</b>"
                ),
                parse_mode='HTML'
            )

            try:
                bot_username = (await context.bot.get_me()).username
                await post_order_completion(
                    context.bot, user_id, service_name, quantity, 0,
                    is_free=True, bot_username=bot_username, deep_link_payload=free_call_data
                )
            except Exception as e:
                print(f"❌ فشل نشر رسالة اكتمال الطلب: {e}")

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"<b>🎁 طلب مجاني جديد 🎁</b>\n\n"
                        f"<b>🛒 الخدمة: {service_name}</b>\n"
                        f"<b>🔗 الرابط: {link}</b>\n"
                        f"<b>📊 العدد: {quantity}</b>\n"
                        f"<b>🆔️ المشتري: <code>{user_id}</code></b>\n"
                        f"<b>🆔️ رقم طلب المزود: {result['order_id']}</b>\n"
                        f"<b>📅 التاريخ: {datetime.now().strftime('%Y/%m/%d %H:%M')}</b>",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            if 'free_service' in context.user_data:
                del context.user_data['free_service']
            if 'free_service_id' in context.user_data:
                del context.user_data['free_service_id']
            if 'free_service_name' in context.user_data:
                del context.user_data['free_service_name']
            if 'free_link' in context.user_data:
                del context.user_data['free_link']
            if 'free_quantity' in context.user_data:
                del context.user_data['free_quantity']
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_free", style="danger")
            markup.add(btn_back)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="اهلا بك في قسم الخدمات المجانية \nاختر الخدمة الذي تريدها",
                reply_markup=markup
            )
        
        # ===================== إلغاء الطلب المجاني =====================
        elif call.data == "cancel_free_order":
            user_id = call.from_user.id
            
            for key in ('free_service', 'free_service_id', 'free_service_name', 'free_link', 'free_quantity', 'awaiting_free_link', 'waiting_free_quantity'):
                context.user_data.pop(key, None)
            
            await call.answer("تم إلغاء الطلب", show_alert=False)
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_free", style="danger")
            markup.add(btn_back)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="اهلا بك في قسم الخدمات المجانية \nاختر الخدمة الذي تريدها",
                reply_markup=markup
            )
        
        # ===================== انستغرام =====================
        elif call.data == "rashek_instagram":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين انستاكرام - ثابت 100% -زيادة 20%- تعويض 6 أشهر", callback_data="insta_720")
            btn2 = InlineKeyboardButton("متابعين انستاكرام - ثابت 100%-زيادة 80% -تعويض لمدة 6 أشهر", callback_data="insta_608")
            btn3 = InlineKeyboardButton("متابعين انستغرام - ثابت 100% -زيادة 40%- تعويض 90 يوم", callback_data="insta_610")
            btn4 = InlineKeyboardButton("متابعين انستاكرام - ثابت 100% -زيادة 40%- تعويض 30 يوم", callback_data="insta_561")
            btn5 = InlineKeyboardButton("متابعين انستاكرام - سرعة فائقة الأفضل - تعويض 30 يوم زيادة 20%", callback_data="insta_682")
            btn6 = InlineKeyboardButton("متابعين انستغرام - سرعة فائقة الأفضل - تعويض 30 يوم", callback_data="insta_731")
            btn7 = InlineKeyboardButton("متابعين انستاكرام - زيادة %20 - 50% - سرعة فائقة", callback_data="insta_582")
            btn8 = InlineKeyboardButton("متابعين انستاكرام - سرعة فائقة جودة عالية الأفضل", callback_data="insta_696")
            btn9 = InlineKeyboardButton("متابعين انستاكرام - حسابات قديمة - نزول 10-20% الأرخص - زيادة 20%", callback_data="insta_721")
            btn10 = InlineKeyboardButton("متابعين انستاكرام - الأرخص - بدون تعويض", callback_data="insta_580")
            btn11 = InlineKeyboardButton("متابعين انستاكرام - حسابات قديمة - نزول 10-20% الأرخص", callback_data="insta_730")
            btn12 = InlineKeyboardButton("لايكات انستاكرام حقيقية عراقية | دعم ممول - فوري", callback_data="insta_419")
            btn13 = InlineKeyboardButton("لايكات إنستقرام ريلز + بوست - الأرخص", callback_data="insta_722")
            btn14 = InlineKeyboardButton("لايكات إنستقرام ريلز + بوست - سرعة عالية", callback_data="insta_562")
            btn15 = InlineKeyboardButton("لايكات إنستقرام شاملة - سرعة عالية", callback_data="insta_519")
            btn16 = InlineKeyboardButton("لايكات إنستقرام ريلز + بوست - سريع", callback_data="insta_343")
            btn17 = InlineKeyboardButton("مشاهدات ستوري انستاكرام لجميع الستوريات - سريع", callback_data="insta_642")
            btn18 = InlineKeyboardButton("مشاهدات إنستقرام ريلز 1م ✅ - مضمونة وسريعة للكميات الكبيرة!", callback_data="insta_621")
            btn19 = InlineKeyboardButton("مشاهدات انستاكرام - ريلز - للكميات الكبيرة جدا 1+ مليون", callback_data="insta_620")
            btn20 = InlineKeyboardButton("مشاركات فيديو ريلز انستقرام | حركة الاكسبلور 🔁 10م", callback_data="insta_402")
            btn21 = InlineKeyboardButton("أعضاء قناة أنستاكرام - بدون تعويض", callback_data="insta_639")
            btn22 = InlineKeyboardButton("دعم اضافات بنات - دعم عراقي", callback_data="insta_566")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")
            
            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn12, btn13, btn14, btn15, btn16, btn17, btn18, btn19, btn20, btn21, btn22, btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : انستغرام\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== فيسبوك =====================
        elif call.data == "rashek_facebook":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين فيسبوك شامل 📘 | بيج + بروفايل", callback_data="fb_369")
            btn2 = InlineKeyboardButton("متابعين فيسبوك | بيج + صفحة شخصية", callback_data="fb_654")
            btn3 = InlineKeyboardButton("متابعين فيسبوك | بيج + صفحة شخصية", callback_data="fb_655")
            btn4 = InlineKeyboardButton("متابعين فيسبوك | بيج + صفحة شخصية", callback_data="fb_656")
            btn5 = InlineKeyboardButton("متابعين فيسبوك | بيج + صفحة شخصية", callback_data="fb_657")
            btn6 = InlineKeyboardButton("متابعين بروفايل و بيجات عامة فيسبوك | 500ك | فوري 🌺", callback_data="fb_499")
            btn7 = InlineKeyboardButton("فيسبوك - لايكات للمنشور - ريلز + بوست", callback_data="fb_651")
            btn8 = InlineKeyboardButton("فيسبوك - لايكات للمنشور - ريلز + بوست", callback_data="fb_652")
            btn9 = InlineKeyboardButton("فيسبوك - لايكات للمنشور - ريلز + بوست", callback_data="fb_705")
            btn10 = InlineKeyboardButton("مشاهدات فيديو فيسبوك | ريلز و عادي | تعويض تلقائي", callback_data="fb_659")
            btn11 = InlineKeyboardButton("مشاهدات فيديو فيسبوك | ريلز و عادي", callback_data="fb_660")
            btn12 = InlineKeyboardButton("مشاهدات فيديو فيسبوك | ريلز و عادي", callback_data="fb_661")
            btn13 = InlineKeyboardButton("مشاهدات فيديو فيسبوك | ريلز و عادي", callback_data="fb_662")
            btn14 = InlineKeyboardButton("مشاهدات فيديو فيسبوك | ريلز و عادي", callback_data="fb_663")
            btn15 = InlineKeyboardButton("أعضاء كروب فيسبوك - جودة عالية - سرعة متوسطة", callback_data="fb_757")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")
            
            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn12, btn13, btn14, btn15, btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : فيسبوك\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== تيك توك =====================
        elif call.data == "rashek_tiktok":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("دعم ممول - 1000 متابع تيكتوك عراقي حقيقي 🇮🇶 100%", callback_data="tiktok_564")
            btn2 = InlineKeyboardButton("متابعين تيكتوك - فوري - جديد", callback_data="tiktok_704")
            btn3 = InlineKeyboardButton("متابعين تيكتوك - فوري - جديد", callback_data="tiktok_748")
            btn4 = InlineKeyboardButton("تيكتوك مشاركة حركة الأكسبلور", callback_data="tiktok_645")
            btn5 = InlineKeyboardButton("تيكتوك مشاركة حركة الأكسبلور", callback_data="tiktok_646")
            btn6 = InlineKeyboardButton("تيكتوك مشاركة حركة الأكسبلور", callback_data="tiktok_648")
            btn7 = InlineKeyboardButton("لايكات تيكتوك - بدون ضمان", callback_data="tiktok_753")
            btn8 = InlineKeyboardButton("لايكات تيكتوك - بدون ضمان", callback_data="tiktok_754")
            btn9 = InlineKeyboardButton("لايكات تيكتوك + مشاهدات - حسابات حقيقية مختلطه - تعويض 10 أيام", callback_data="tiktok_756")
            btn10 = InlineKeyboardButton("مشاهدات تيكتوك حقيقية - من الاعلانات- ضمان مدى الحياة - بدون نزول", callback_data="tiktok_746")
            btn11 = InlineKeyboardButton("مشاهدات تيكتوك حقيقية - من الاعلانات- ضمان مدى الحياة - بدون نزول", callback_data="tiktok_747")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")
            
            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : تيك توك\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== تليكرام =====================
        elif call.data == "rashek_telegram":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("اعضاء تليكرام -حسابات محذوفة - ضمان 90 يوم سريع", callback_data="telegram_698")
            btn2 = InlineKeyboardButton("اعضاء تليكرام - قناة عامه - ضمان 60يوم", callback_data="telegram_714")
            btn3 = InlineKeyboardButton("مشاهدات تلي لبوست واحد 🔥", callback_data="telegram_358")
            btn4 = InlineKeyboardButton("مشاهدات بوست تليكرام - سوبر فاست", callback_data="telegram_627")
            btn5 = InlineKeyboardButton("مشاهدات تلي لبوست واحد 🔥", callback_data="telegram_480")
            btn6 = InlineKeyboardButton("مشاهدات تلي لبوست واحد 🔥 سريع", callback_data="telegram_710")
            btn7 = InlineKeyboardButton("مشاهدات تلي- مستقبلية - 5 بوست", callback_data="telegram_732")
            btn8 = InlineKeyboardButton("مشاهدات تلي- مستقبلية - 10 بوست", callback_data="telegram_733")
            btn9 = InlineKeyboardButton("مشاهدات تلي- مستقبلية - 20 بوست", callback_data="telegram_734")
            btn10 = InlineKeyboardButton("مشاهدات تلي- مستقبلية - 30 بوست", callback_data="telegram_735")
            btn11 = InlineKeyboardButton("مشاهدات تلي- مستقبلية - 20 بوست", callback_data="telegram_736")
            btn12 = InlineKeyboardButton("مشاهدات تلي- مستقبلية - 100 بوست", callback_data="telegram_737")
            btn13 = InlineKeyboardButton("مشاهدات تلي- أخر 5 بوست", callback_data="telegram_738")
            btn14 = InlineKeyboardButton("مشاهدات تلي- أخر 5 بوست", callback_data="telegram_739")
            btn15 = InlineKeyboardButton("مشاهدات تلي- أخر 5 بوست", callback_data="telegram_740")
            btn16 = InlineKeyboardButton("مشاهدات تلي- أخر 10 بوست", callback_data="telegram_741")
            btn17 = InlineKeyboardButton("مشاهدات تلي- أخر 10 بوست", callback_data="telegram_742")
            btn18 = InlineKeyboardButton("مشاهدات تلي- أخر 20 بوست", callback_data="telegram_743")
            btn19 = InlineKeyboardButton("مشاهدات تلي- أخر 100 بوست", callback_data="telegram_745")
            btn20 = InlineKeyboardButton("أعضاء تيليجرام 🇨🇳 صينيين - مناسب للقنوات العامة", callback_data="telegram_355")
            btn21 = InlineKeyboardButton("اعضاء قناة تليكرام - بدون تعويض - نزول عالي", callback_data="telegram_725")
            btn22 = InlineKeyboardButton("اعضاء قناة تليكرام - بدون تعويض - نزول عالي", callback_data="telegram_726")
            btn23 = InlineKeyboardButton("تليكرام - تفاعلات برمز {💋}", callback_data="telegram_767")
            btn24 = InlineKeyboardButton("تليكرام - تفاعلات برمز {❤️}", callback_data="telegram_769")
            btn25 = InlineKeyboardButton("تليكرام - تفاعلات برمز {🔥}", callback_data="telegram_759")
            btn26 = InlineKeyboardButton("تليكرام - تفاعلات برمز {🤩}", callback_data="telegram_764")
            btn27 = InlineKeyboardButton("تليكرام - تفاعلات برمز {😱}", callback_data="telegram_765")
            btn28 = InlineKeyboardButton("تليكرام - تفاعلات برمز {🤣}", callback_data="telegram_763")
            btn29 = InlineKeyboardButton("تليكرام - تفاعلات بوست تليكرام 👎💩🤮🤔🤯😁😢🤬 - سريع", callback_data="telegram_629")
            btn30 = InlineKeyboardButton("تليكرام تفاعلات ايجابية 👍🤩🎉🔥❤️🥰👏🏻🥳😍❤️‍🔥💯", callback_data="telegram_713")
            btn31 = InlineKeyboardButton("خدمة تعزيز قناة تيليجرام 💎 | تفعيل ميزة القصص Story ضمان 1 يوم", callback_data="telegram_631")
            btn32 = InlineKeyboardButton("خدمة تعزيز قناة تيليجرام 💎 | تفعيل ميزة القصص Story ضمان 1 يوم", callback_data="telegram_632")
            btn33 = InlineKeyboardButton("مشاهدات ستوري تليكرام - سريع", callback_data="telegram_638")
            btn34 = InlineKeyboardButton("اعضاء تليكرام بريميوم ضمان 7 أيام", callback_data="telegram_750")
            btn35 = InlineKeyboardButton("اعضاء تليكرام بريميوم ضمان 15-30 يوم", callback_data="telegram_751")
            btn36 = InlineKeyboardButton("اعضاء تليكرام بريميوم ضمان 30-60 يوم", callback_data="telegram_752")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")
            
            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn12, btn13, btn14, btn15, btn16, btn17, btn18, btn19, btn20, btn21, btn22, btn23, btn24, btn25, btn26, btn27, btn28, btn29, btn30, btn31, btn32, btn33, btn34, btn35, btn36, btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : تليكرام\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== يوتيوب =====================
        elif call.data == "rashek_youtube":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("مشاهدات يوتيوب | ٢٠ ألف مشاهدة يوميًا | - تعويض 30 يوم", callback_data="youtube_624")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")
            
            markup.add(btn1, btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : يوتيوب\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== كيك =====================
        elif call.data == "rashek_kick":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين 👤 كيك (بدون ضمان) الأرخص 🎁", callback_data="kick_8861")
            btn2 = InlineKeyboardButton("مشاهدات 👁 كيك ( ضمان 30 يوم) 🚀", callback_data="kick_8347")
            btn3 = InlineKeyboardButton("مشاهدات 👁 كيك كليب ( بدون ضمان ) 🚀", callback_data="kick_8356")
            btn4 = InlineKeyboardButton("تصويت كيك 📊 استطلاع رأي(ضمان 30 يوم)🚀", callback_data="kick_8350")
            btn5 = InlineKeyboardButton("مشاهدات 👁 كيك بث مباشر ( 5 دقيقة ) 🚀", callback_data="kick_8367")
            btn6 = InlineKeyboardButton("مشاهدات 👁 كيك بث مباشر ( 10 دقيقة ) 🚀", callback_data="kick_8366")
            btn7 = InlineKeyboardButton("مشاهدات 👁 كيك بث مباشر ( 15 دقيقة ) 🚀", callback_data="kick_8357")
            btn8 = InlineKeyboardButton("مشاهدات 👁 كيك بث مباشر ( 30 دقيقة ) 🚀", callback_data="kick_8358")
            btn9 = InlineKeyboardButton("مشاهدات 👁 كيك بث مباشر ( 45 دقيقة ) 🚀", callback_data="kick_8359")
            btn10 = InlineKeyboardButton("مشاهدات 👁 كيك بث مباشر ( 60 دقيقة ) 🚀", callback_data="kick_8360")
            btn11 = InlineKeyboardButton("مشاهدات 👁 كيك بث مباشر ( 90 دقيقة ) 🚀", callback_data="kick_8368")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")

            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : كيك\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== كواي =====================
        elif call.data == "rashek_kwai":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين 👤 كواي ( بدون ضمان ) الأرخص 🎁", callback_data="kwai_5420")
            btn2 = InlineKeyboardButton("لايكات 🤎 كواي ( ضمان 30 يوم ) 🚀", callback_data="kwai_2157")
            btn3 = InlineKeyboardButton("مشاركات ♻️ كواي ( بدون ضمان) 🚀", callback_data="kwai_5440")
            btn4 = InlineKeyboardButton("تعليقات💬كواي عرب مخصص(ضمان 30يوم)🚀", callback_data="kwai_5416")
            btn5 = InlineKeyboardButton("لايكات 🤎 كواي بث مباشر ( عرب) 🚀", callback_data="kwai_8369")
            btn6 = InlineKeyboardButton("مشاركات ♻️ كواي بث مباشر ( عرب) 🚀", callback_data="kwai_8370")
            btn7 = InlineKeyboardButton("مشاهدات 👁 كواي 🇪🇬 ( بدون ضمان ) 🚀", callback_data="kwai_5438")
            btn8 = InlineKeyboardButton("مشاهدات 👁 كواي 🇱🇧 ( بدون ضمان ) 🚀", callback_data="kwai_5493")
            btn9 = InlineKeyboardButton("مشاهدات 👁 كواي 🇮🇶 ( بدون ضمان ) 🚀", callback_data="kwai_5499")
            btn10 = InlineKeyboardButton("مشاهدات 👁 كواي 🇹🇷 ( بدون ضمان ) 🚀", callback_data="kwai_5421")
            btn11 = InlineKeyboardButton("مشاهدات 👁 كواي 🇸🇦 ( بدون ضمان ) 🚀", callback_data="kwai_5484")
            btn12 = InlineKeyboardButton("مشاهدات 👁 كواي 🇰🇼 ( بدون ضمان ) 🚀", callback_data="kwai_5486")
            btn13 = InlineKeyboardButton("مشاهدات 👁 كواي 🇶🇦 ( بدون ضمان ) 🚀", callback_data="kwai_5495")
            btn14 = InlineKeyboardButton("مشاهدات 👁 كواي 🇴🇲 ( بدون ضمان ) 🚀", callback_data="kwai_5494")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")

            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn12, btn13, btn14, btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : كواي\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== سبوتيفاي =====================
        elif call.data == "rashek_spotify":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين 👤 سبوتيفاي ( مدى الحياة ) 🚀", callback_data="spotify_4641")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")

            markup.add(btn1, btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : سبوتيفاي\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== تويتر =====================
        elif call.data == "rashek_twitter":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين 👤 تويتر ( بدون ضمان ) 🚀", callback_data="twitter_998")
            btn2 = InlineKeyboardButton("لايكات 🤎 تويتر ( بدون ضمان ) 🚀", callback_data="twitter_7761")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")

            markup.add(btn1, btn2, btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : تويتر\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== تويتش =====================
        elif call.data == "rashek_twitch":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين 👤 تويتش ( ضمان 15 يوم ) 🚀", callback_data="twitch_2252")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")

            markup.add(btn1, btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : تويتش\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== تروفو =====================
        elif call.data == "rashek_trovo":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("متابعين 👤 تروفو ( جودة جيدة ) 🚀", callback_data="trovo_7289")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")

            markup.add(btn1, btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : تروفو\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== واتساب =====================
        elif call.data == "rashek_whatsapp":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("اعضاء 👤 واتساب ( بدون ضمان ) 🚀", callback_data="whatsapp_7335")
            btn2 = InlineKeyboardButton("استطلاع رأي 📊 واتساب ( خيار A ) 🚀", callback_data="whatsapp_5634")
            btn3 = InlineKeyboardButton("استطلاع رأي 📊 واتساب ( خيار B ) 🚀", callback_data="whatsapp_8015")
            btn4 = InlineKeyboardButton("استطلاع رأي 📊 واتساب ( خيار C ) 🚀", callback_data="whatsapp_5636")
            btn5 = InlineKeyboardButton("استطلاع رأي 📊 واتساب ( خيار D ) 🚀", callback_data="whatsapp_8021")
            btn6 = InlineKeyboardButton("تفاعل ( 👍 ) واتساب ( منشور قناة ) 🚀", callback_data="whatsapp_8612")
            btn7 = InlineKeyboardButton("تفاعل ( ❤️ ) واتساب ( منشور قناة ) 🚀", callback_data="whatsapp_8613")
            btn8 = InlineKeyboardButton("تفاعل ( 😂 ) واتساب ( منشور قناة ) 🚀", callback_data="whatsapp_8614")
            btn9 = InlineKeyboardButton("تفاعل ( 😲 ) واتساب ( منشور قناة ) 🚀", callback_data="whatsapp_8615")
            btn10 = InlineKeyboardButton("تفاعل ( 😢 ) واتساب ( منشور قناة ) 🚀", callback_data="whatsapp_8616")
            btn11 = InlineKeyboardButton("تفاعل ( 👍 ❤️ 🔥 🎉 😁 ) واتساب( منشور قناة ) 🚀", callback_data="whatsapp_8618")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger")

            markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>🤩 | مرحباً بك في قسم : واتساب\n🔰 | اختر الخدمة المطلوبة : 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== هدايا وجوائز =====================
        elif call.data == "gifts":
            markup = InlineKeyboardMarkup(row_width=2)
            btn1 = InlineKeyboardButton("دعم قنوات تليجرام 👤", callback_data="tgsup_menu")
            btn2 = InlineKeyboardButton("نجوم تليجرام ⭐️", callback_data="stars_shop")
            btn4 = InlineKeyboardButton("قنوات تليجرام 🧊", callback_data="soon")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            
            markup.row(btn1, btn2)
            markup.row(btn4)
            markup.row(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>- اهـلآ بك في قسم الخدمات ♥️\n- يمكنك شراء الخدمات مقابل نقاطك بالبوت🤩</b>", parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== دعم قنوات تليجرام (نقاط) =====================
        elif call.data == "tgsup_menu":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("2 عضو 👤 = 2000 نقطة (تجربة)", callback_data="tgsup_pts_2"))
            markup.row(InlineKeyboardButton("100 عضو 👤 = 20000 نقطة", callback_data="tgsup_pts_100"))
            markup.row(InlineKeyboardButton("200 عضو 👤 = 40000 نقطة", callback_data="tgsup_pts_200"))
            markup.row(InlineKeyboardButton("300 عضو 👤 = 60000 نقطة", callback_data="tgsup_pts_300"))
            markup.row(InlineKeyboardButton("الدفع بالنجوم ⭐️", callback_data="tgsup_stars_menu"))
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="gifts", style="danger"))

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>- اهـلآ بك في قسم دعم قنوات تليجرام 👤\n"
                     "- سنضع قناتك كأشتراك اجباري بالبوت ⚜️</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== دعم قنوات تليجرام (نجوم) =====================
        elif call.data == "tgsup_stars_menu":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("100 عضو 👤 = 75 نجمة ⭐️", url=INVOICE_LINKS.get("tgsupport_100", "https://t.me")))
            markup.row(InlineKeyboardButton("200 عضو 👤 = 130 نجمة ⭐️", url=INVOICE_LINKS.get("tgsupport_200", "https://t.me")))
            markup.row(InlineKeyboardButton("300 عضو 👤 = 200 نجمة ⭐️", url=INVOICE_LINKS.get("tgsupport_300", "https://t.me")))
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="tgsup_menu", style="danger"))

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>- اهـلآ بك في قسم دعم قنوات تليجرام 👤\n"
                     "- سنضع قناتك كأشتراك اجباري بالبوت ⚜️</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== شراء دعم قنوات تليجرام بالنقاط =====================
        elif call.data.startswith("tgsup_pts_"):
            members = int(call.data.split("_")[2])
            price_map = {2: 2000, 100: 20000, 200: 40000, 300: 60000}
            price = price_map.get(members)
            user_id = call.from_user.id

            current_points = get_user_points(user_id)
            if current_points < price:
                await call.answer("❌ رصيدك غير كافٍ!", show_alert=True)
                return

            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('UPDATE users SET points = points - ? WHERE user_id = ?', (price, user_id))
            conn.commit()
            conn.close()

            purchase_number = add_purchase(user_id, f"{members} عضو (دعم قنوات تليجرام)", 0, price, 'pending')
            add_completed_service(f"{members} عضو", user_id)

            await call.answer()
            await context.bot.send_message(
                user_id,
                f"<b>✅ وصل الشراء الخاص بك:\n"
                f"🤩 الخدمة: {members} عضو 👤\n"
                f"💸 الكلفة: {price} نقطة 💎\n"
                f"🔎 رقم الخدمة: {purchase_number}\n"
                f"💎 رصيدك الجديد: {get_user_points(user_id)} نقطة\n"
                f"★ شكراً لاستخدامك بوت متجر النخبة ♥️</b>",
                parse_mode='HTML'
            )
            await context.bot.send_message(
                user_id,
                "<b>- يرجى رفع البوت ادمن في قناتك ❗️\n"
                "- اعطي للبوت ميزة دعوة المستخدمين ❗️\n"
                "- يرجى ارسال أي رساله من القناة للبوت ✅️</b>",
                parse_mode='HTML'
            )

            context.user_data['tg_support_request'] = {
                'members': members,
                'price': price,
                'currency': 'points',
                'purchase_number': purchase_number
            }

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"✅️ عملية شراء جديدة (دعم قنوات تليجرام - نقاط) ✅️\n"
                        f"🤩 الخدمة: {members} عضو 👤\n"
                        f"💸 السعر : {price} نقطة\n"
                        f"🔎 رقم الخدمة: {purchase_number}\n"
                        f"🆔️ المشتري : <code>{user_id}</code>\n"
                        f"🕐 التاريخ : {datetime.now().strftime('%Y/%m/%d %H:%M')}"
                    )
                except:
                    pass
        
        # ===================== نجوم تليجرام =====================
        elif call.data == "stars_shop":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("15 نجمة ⭐️ = 7000 نقطة", callback_data="buy_stars_15"))
            markup.row(InlineKeyboardButton("25 نجمة ⭐️ = 12000 نقطة", callback_data="buy_stars_25"))
            markup.row(InlineKeyboardButton("50 نجمة ⭐️ = 20000 نقطة", callback_data="buy_stars_50"))
            markup.row(InlineKeyboardButton("75 نجمة ⭐️ = 30000 نقطة", callback_data="buy_stars_75"))
            markup.row(InlineKeyboardButton("100 نجمة ⭐️ = 40000 نقطة", callback_data="buy_stars_100"))
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="gifts", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>- اهـلآ بك في قسم النجوم ⭐️\n- يـرجى اختيار عدد النجوم التي تريدها 🤩</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== شراء نجوم =====================
        elif call.data.startswith("buy_stars_"):
            user_id = call.from_user.id
            stars_options = {
                "buy_stars_15": {"stars": 15, "price": 7000, "name": "15 نجمة"},
                "buy_stars_25": {"stars": 25, "price": 12000, "name": "25 نجمة"},
                "buy_stars_50": {"stars": 50, "price": 20000, "name": "50 نجمة"},
                "buy_stars_75": {"stars": 75, "price": 30000, "name": "75 نجمة"},
                "buy_stars_100": {"stars": 100, "price": 40000, "name": "100 نجمة"}
            }
            option = stars_options.get(call.data)
            if not option:
                return
            
            current_points = get_user_points(user_id)
            if current_points < option["price"]:
                await call.answer(f"❌ نقاطك غير كافية!", show_alert=True)
                return
            
            pending_purchases[user_id] = {
                'type': 'stars',
                'stars': option['stars'],
                'price': option['price'],
                'name': option['name']
            }
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.row(
                InlineKeyboardButton("✅ اشتري", callback_data="confirm_purchase"),
                InlineKeyboardButton("❌ لا", callback_data="cancel_purchase")
            )
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"<b>هل تريد شراء الخدمة؟</b>\n\n"
                     f"<b>الخدمة: {option['name']} ⭐️</b>\n"
                     f"<b>السعر: {option['price']} نقطة 💎</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== تأكيد شراء النجوم =====================
        elif call.data == "confirm_purchase":
            user_id = call.from_user.id
            pending = pending_purchases.get(user_id)
            if not pending:
                await call.answer("لا توجد عملية شراء معلقة!", show_alert=True)
                return
            
            current_points = get_user_points(user_id)
            if current_points < pending['price']:
                await call.answer(f"❌ نقاطك غير كافية!", show_alert=True)
                del pending_purchases[user_id]
                return
            
            update_points_remove(user_id, pending['price'])
            purchase_number = add_purchase(user_id, pending['name'], pending['stars'], pending['price'], 'pending')
            add_completed_service(pending['name'], user_id)
            
            await call.answer("تم الشراء ✅️", show_alert=False)
            
            await context.bot.send_message(
                user_id,
                f"<b>✅ وصل الشراء الخاص بك:\n"
                f"🤩 الخدمة: {pending['name']} ⭐️\n"
                f"💸 الكلفة: {pending['price']} نقطة\n"
                f"🔎 رقم الخدمة: {purchase_number}\n"
                f"💎 رصيدك الجديد: {get_user_points(user_id)} نقطة\n"
                f"- قم بتحويل وصل الشراء للدعم الفني ليتم تسليمك: @{SUPPORT_USERNAME}\n"
                f"⚠️ بدون وصل الشراء لا يمكن تسليمك!\n"
                f"★ شكراً لاستخدامك بوت متجر النخبة ♥️</b>",
                parse_mode='HTML'
            )
            
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"✅️ عملية شراء جديدة (نجوم) ✅️\n"
                        f"🤩 الخدمة: {pending['name']} ⭐️\n"
                        f"💸 السعر : {pending['price']} نقطة\n"
                        f"🔎 رقم الخدمة: {purchase_number}\n"
                        f"🆔️ المشتري : <code>{user_id}</code>\n"
                        f"🕐 التاريخ : {datetime.now().strftime('%Y/%m/%d %H:%M')}",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            del pending_purchases[user_id]
            
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("15 نجمة ⭐️ = 7000 نقطة", callback_data="buy_stars_15"))
            markup.row(InlineKeyboardButton("25 نجمة ⭐️ = 12000 نقطة", callback_data="buy_stars_25"))
            markup.row(InlineKeyboardButton("50 نجمة ⭐️ = 20000 نقطة", callback_data="buy_stars_50"))
            markup.row(InlineKeyboardButton("75 نجمة ⭐️ = 30000 نقطة", callback_data="buy_stars_75"))
            markup.row(InlineKeyboardButton("100 نجمة ⭐️ = 40000 نقطة", callback_data="buy_stars_100"))
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="gifts", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>- اهـلآ بك في قسم النجوم ⭐️\n- يـرجى اختيار عدد النجوم التي تريدها 🤩</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== إلغاء شراء النجوم =====================
        elif call.data == "cancel_purchase":
            user_id = call.from_user.id
            if user_id in pending_purchases:
                del pending_purchases[user_id]
            
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("15 نجمة ⭐️ = 7000 نقطة", callback_data="buy_stars_15"))
            markup.row(InlineKeyboardButton("25 نجمة ⭐️ = 12000 نقطة", callback_data="buy_stars_25"))
            markup.row(InlineKeyboardButton("50 نجمة ⭐️ = 20000 نقطة", callback_data="buy_stars_50"))
            markup.row(InlineKeyboardButton("75 نجمة ⭐️ = 30000 نقطة", callback_data="buy_stars_75"))
            markup.row(InlineKeyboardButton("100 نجمة ⭐️ = 40000 نقطة", callback_data="buy_stars_100"))
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="gifts", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>- اهـلآ بك في قسم النجوم ⭐️\n- يـرجى اختيار عدد النجوم التي تريدها 🤩</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== نشر اعلان =====================
        elif call.data == "publish_ad":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("لمدة 1 ساعة 🕐 = 30000 نقطة", callback_data="ad_points_1"))
            markup.row(InlineKeyboardButton("لمدة 2 ساعة 🕐 = 60000 نقطة", callback_data="ad_points_2"))
            markup.row(InlineKeyboardButton("لمدة 3 ساعة 🕐 = 90000 نقطة", callback_data="ad_points_3"))
            markup.row(InlineKeyboardButton("لمدة 4 ساعة 🕐 = 120000 نقطة", callback_data="ad_points_4"))
            markup.row(InlineKeyboardButton("لمدة 5 ساعة 🕐 = 150000 نقطة", callback_data="ad_points_5"))
            markup.row(InlineKeyboardButton("اعلان مدفوع ⭐️", callback_data="ad_paid"))
            markup.row(
                InlineKeyboardButton("شروط الإعلان 📛", callback_data="ad_terms_points"),
                InlineKeyboardButton("قنوات النشر ☑️", callback_data="ad_channels_points")
            )
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="- اهـلآ بك في قسم نشر اعلان 📢\n- سينشر الإعلان في قنوات البوت ♥️\n- يجب اتباع شروط نشر الإعلان 📛",
                reply_markup=markup
            )
        
        # ===================== شروط الإعلان =====================
        elif call.data in ("ad_terms_points", "ad_terms_paid"):
            origin = "ad_paid" if call.data == "ad_terms_paid" else "publish_ad"
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data=origin, style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>📢 شروط الإعلان في متجر النخبة</b>\n\n"
                     "<b>يرجى قراءة الشروط قبل طلب نشر إعلانك:</b>\n\n"
                     "<b>━━━━━━━━━━━━━━</b>\n\n"
                     "<b>📝 يجب إرسال الإعلان كاملًا وجاهزًا للنشر، مع الرابط أو اليوزر الصحيح إن وجد.</b>\n\n"
                     "<b>🚫 يُمنع نشر أي إعلان يحتوي على:</b>\n"
                     "<b>• محتوى مخالف أو غير لائق</b>\n"
                     "<b>• روابط سبام أو احتيال</b>\n"
                     "<b>• محتوى طائفي أو يحرض على الكراهية</b>\n"
                     "<b>• مشاهد قتل أو عنف أو ما شابه</b>\n"
                     "<b>• نشر أدوات اختراق، تهكير، ملفات ضارة أو أي محتوى متعلق بالهكر والاختراق</b>\n"
                     "<b>• أي شيء يخالف سياسات تيليجرام</b>\n\n"
                     "<b>✅ يُسمح بنشر:</b>\n"
                     "<b>• القنوات الترفيهية</b>\n"
                     "<b>• القنوات التعليمية</b>\n"
                     "<b>• المشاريع والخدمات العامة والمحتوى المناسب</b>\n\n"
                     "<b>🔗 يرجى التأكد من صحة الرابط أو اليوزر المرسل قبل تأكيد الطلب.</b>\n\n"
                     "<b>📣 البوت دوره يقتصر على نشر الإعلان فقط، ولا يتحمل أي مسؤولية عن أي تعامل أو اتفاق يتم بعد الدخول إلى الإعلان.</b>\n\n"
                     "<b>⚠️ اذا تم رفض إعلانك من قبل الإدارة لم يتم التعويض ابداً 📛</b>\n"
                     "<b>رفض الإعلان يتم في حالة مخالفة شروط الإعلان</b>\n\n"
                     "<b>⏳ يتم تنفيذ الإعلانات حسب ترتيب الطلبات، وقد يختلف وقت النشر حسب الضغط.</b>\n\n"
                     "<b>❌ بعد قبول الإعلان أو بدء تنفيذه لا يمكن الإلغاء أو استرجاع النقاط أو النجوم.</b>\n\n"
                     "<b>🛠️ الإدارة تحتفظ بحق رفض أو حذف أي إعلان غير مناسب أو مخالف للشروط دون إشعار مسبق.</b>\n\n"
                     "<b>━━━━━━━━━━━━━━</b>\n\n"
                     "<b>✅ بمجرد إرسال إعلانك أو تأكيد الطلب، فهذا يعني موافقتك الكاملة على جميع الشروط المذكورة أعلاه.</b>\n\n"
                     "<b>شكرًا لاختياركم متجر النخبة 🤍</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== قنوات النشر =====================
        elif call.data in ("ad_channels_points", "ad_channels_paid"):
            origin = "ad_paid" if call.data == "ad_channels_paid" else "publish_ad"
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data=origin, style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>☑️ قنوات النشر ☑️</b>\n"
                     "<b>سيتم نشر إعلانك في القنوات التالية :</b>\n\n"
                     "<b>• قناة متجر النخبة (@NN32J) .</b>\n"
                     "<b>• قناة اكتمال الطلبات (@NNL38) مع التثبيت .</b>\n"
                     "<b>• قناة توزيع النقاط (@NN72D) .</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== اعلان مدفوع =====================
        elif call.data == "ad_paid":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("لمدة 1 ساعة 🕐 = 1 نجمة ⭐️", url=INVOICE_LINKS.get("ad_paid_1", "https://t.me")))
            markup.row(InlineKeyboardButton("لمدة 2 ساعة 🕐 = 1 نجمة ⭐️", url=INVOICE_LINKS.get("ad_paid_2", "https://t.me")))
            markup.row(InlineKeyboardButton("لمدة 3 ساعة 🕐 = 1 نجمة ⭐️", url=INVOICE_LINKS.get("ad_paid_3", "https://t.me")))
            markup.row(InlineKeyboardButton("لمدة 4 ساعة 🕐 = 1 نجمة ⭐️", url=INVOICE_LINKS.get("ad_paid_4", "https://t.me")))
            markup.row(InlineKeyboardButton("لمدة 5 ساعة 🕐 = 1 نجمة ⭐️", url=INVOICE_LINKS.get("ad_paid_5", "https://t.me")))
            markup.row(
                InlineKeyboardButton("شروط الإعلان 📛", callback_data="ad_terms_paid"),
                InlineKeyboardButton("قنوات النشر ☑️", callback_data="ad_channels_paid")
            )
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="publish_ad", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="- اهـلآ بك في قسم نشر اعلان 📢\n- سينشر الإعلان في قنوات البوت ♥️\n- يجب اتباع شروط نشر الإعلان 📛",
                reply_markup=markup
            )
        
        # ===================== شراء اعلان بالنقاط =====================
        elif call.data.startswith("ad_points_"):
            user_id = call.from_user.id
            ad_options = {
                "ad_points_1": {"hours": 1, "price": 30000, "name": "اعلان لمدة 1 ساعة"},
                "ad_points_2": {"hours": 2, "price": 60000, "name": "اعلان لمدة 2 ساعة"},
                "ad_points_3": {"hours": 3, "price": 90000, "name": "اعلان لمدة 3 ساعة"},
                "ad_points_4": {"hours": 4, "price": 120000, "name": "اعلان لمدة 4 ساعة"},
                "ad_points_5": {"hours": 5, "price": 150000, "name": "اعلان لمدة 5 ساعة"}
            }
            option = ad_options.get(call.data)
            if not option:
                return
            
            current_points = get_user_points(user_id)
            if current_points < option["price"]:
                await call.answer(f"❌ نقاطك غير كافية!", show_alert=True)
                return
            
            context.user_data['ad_purchase'] = option
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.row(
                InlineKeyboardButton("✅ اشتري", callback_data="confirm_ad_purchase"),
                InlineKeyboardButton("❌ لا", callback_data="cancel_ad_purchase")
            )
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"<b>هل تريد شراء الخدمة؟</b>\n\n"
                     f"<b>الخدمة: {option['name']} 🕐</b>\n"
                     f"<b>السعر: {option['price']} نقطة 💎</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== تأكيد شراء اعلان =====================
        elif call.data == "confirm_ad_purchase":
            user_id = call.from_user.id
            ad_data = context.user_data.get('ad_purchase')
            if not ad_data:
                await call.answer("لا توجد عملية شراء معلقة!", show_alert=True)
                return
            
            current_points = get_user_points(user_id)
            if current_points < ad_data['price']:
                await call.answer(f"❌ نقاطك غير كافية!", show_alert=True)
                del context.user_data['ad_purchase']
                return
            
            update_points_remove(user_id, ad_data['price'])
            purchase_number = add_purchase(user_id, ad_data['name'], 0, ad_data['price'], 'pending')
            add_completed_service(ad_data['name'], user_id)
            
            await call.answer("تم الشراء ✅️", show_alert=False)
            
            await context.bot.send_message(
                user_id,
                f"<b>✅ وصل الشراء الخاص بك:\n"
                f"🤩 الخدمة: {ad_data['name']} 🕐\n"
                f"💸 الكلفة: {ad_data['price']} نقطة\n"
                f"🔎 رقم الخدمة: {purchase_number}\n"
                f"💎 رصيدك الجديد: {get_user_points(user_id)} نقطة\n"
                f"★ شكراً لاستخدامك بوت متجر النخبة ♥️</b>",
                parse_mode='HTML'
            )
            
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"✅️ عملية شراء جديدة (اعلان) ✅️\n"
                        f"🤩 الخدمة: {ad_data['name']} 🕐\n"
                        f"💸 السعر : {ad_data['price']} نقطة\n"
                        f"🔎 رقم الخدمة: {purchase_number}\n"
                        f"🆔️ المشتري : <code>{user_id}</code>\n"
                        f"🕐 التاريخ : {datetime.now().strftime('%Y/%m/%d %H:%M')}",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            await context.bot.send_message(
                user_id,
                "<b>يرجى ارسال الرساله الذي تريد الإعلان عنها ✅️</b>",
                parse_mode='HTML'
            )
            
            context.user_data['ad_waiting'] = {
                'purchase_number': purchase_number,
                'hours': ad_data['hours'],
                'price': ad_data['price'],
                'name': ad_data['name'],
                'currency': 'points'
            }
            
            del context.user_data['ad_purchase']
            
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("لمدة 1 ساعة 🕐 = 30000 نقطة", callback_data="ad_points_1"))
            markup.row(InlineKeyboardButton("لمدة 2 ساعة 🕐 = 60000 نقطة", callback_data="ad_points_2"))
            markup.row(InlineKeyboardButton("لمدة 3 ساعة 🕐 = 90000 نقطة", callback_data="ad_points_3"))
            markup.row(InlineKeyboardButton("لمدة 4 ساعة 🕐 = 120000 نقطة", callback_data="ad_points_4"))
            markup.row(InlineKeyboardButton("لمدة 5 ساعة 🕐 = 150000 نقطة", callback_data="ad_points_5"))
            markup.row(InlineKeyboardButton("اعلان مدفوع ⭐️", callback_data="ad_paid"))
            markup.row(
                InlineKeyboardButton("شروط الإعلان 📛", callback_data="ad_terms_points"),
                InlineKeyboardButton("قنوات النشر ☑️", callback_data="ad_channels_points")
            )
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="- اهـلآ بك في قسم نشر اعلان 📢\n- سينشر الإعلان في قنوات البوت ♥️\n- يجب اتباع شروط نشر الإعلان 📛",
                reply_markup=markup
            )
        
        # ===================== إلغاء شراء اعلان =====================
        elif call.data == "cancel_ad_purchase":
            user_id = call.from_user.id
            if 'ad_purchase' in context.user_data:
                del context.user_data['ad_purchase']
            
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("لمدة 1 ساعة 🕐 = 30000 نقطة", callback_data="ad_points_1"))
            markup.row(InlineKeyboardButton("لمدة 2 ساعة 🕐 = 60000 نقطة", callback_data="ad_points_2"))
            markup.row(InlineKeyboardButton("لمدة 3 ساعة 🕐 = 90000 نقطة", callback_data="ad_points_3"))
            markup.row(InlineKeyboardButton("لمدة 4 ساعة 🕐 = 120000 نقطة", callback_data="ad_points_4"))
            markup.row(InlineKeyboardButton("لمدة 5 ساعة 🕐 = 150000 نقطة", callback_data="ad_points_5"))
            markup.row(InlineKeyboardButton("اعلان مدفوع ⭐️", callback_data="ad_paid"))
            markup.row(
                InlineKeyboardButton("شروط الإعلان 📛", callback_data="ad_terms_points"),
                InlineKeyboardButton("قنوات النشر ☑️", callback_data="ad_channels_points")
            )
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="rashek_services", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="- اهـلآ بك في قسم نشر اعلان 📢\n- سينشر الإعلان في قنوات البوت ♥️\n- يجب اتباع شروط نشر الإعلان 📛",
                reply_markup=markup
            )
        
        # ===================== موافقة اعلان =====================
        elif call.data.startswith("approve_ad_"):
            admin_id = call.from_user.id
            if admin_id not in ADMIN_IDS:
                await call.answer("هذا الأمر للأدمن فقط!", show_alert=True)
                return
            
            ad_id = int(call.data.split("_")[2])
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('SELECT user_id, ad_text, duration_hours FROM ads WHERE id = ? AND status = "pending"', (ad_id,))
            ad = c.fetchone()
            if not ad:
                await call.answer("هذا الإعلان لم يعد موجوداً!", show_alert=True)
                conn.close()
                return
            
            user_id, ad_text, duration_hours = ad
            c.execute('UPDATE ads SET status = "approved", approved_at = ? WHERE id = ?', 
                      (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ad_id))
            conn.commit()
            conn.close()
            
            ad_message = f"{ad_text}\n\n<b>#اعلان</b>"
            
            try:
                await context.bot.send_message("@NN32J", ad_message, parse_mode='HTML')
                await context.bot.send_message("@NNL38", ad_message, parse_mode='HTML')
                await context.bot.send_message("@NN72D", ad_message, parse_mode='HTML')
            except Exception as e:
                print(f"❌ خطأ في نشر الإعلان: {e}")
            
            await context.bot.edit_message_text(
                call.message.chat.id,
                call.message.message_id,
                "<b>✅ تمت الموافقة على الإعلان ✅️</b>\n\n<b>تم نشر الإعلان في القنوات بنجاح</b>",
                parse_mode='HTML'
            )
            
            await context.bot.send_message(
                user_id,
                f"<b>✅ تمت الموافقة على إعلانك ✅️</b>\n\n"
                f"<b>⏰ المدة: {duration_hours} ساعة</b>\n"
                f"<b>📢 تم نشر إعلانك في قنوات البوت.</b>\n\n"
                f"<b>★ شكراً لاستخدامك متجر النخبة ♥️</b>",
                parse_mode='HTML'
            )
        
        # ===================== رفض اعلان =====================
        elif call.data.startswith("reject_ad_"):
            admin_id = call.from_user.id
            if admin_id not in ADMIN_IDS:
                await call.answer("هذا الأمر للأدمن فقط!", show_alert=True)
                return
            
            ad_id = int(call.data.split("_")[2])
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('UPDATE ads SET status = "rejected" WHERE id = ?', (ad_id,))
            conn.commit()
            conn.close()
            
            await context.bot.edit_message_text(
                call.message.chat.id,
                call.message.message_id,
                "<b>❌ تم رفض الإعلان ❌️</b>",
                parse_mode='HTML'
            )
        
        # ===================== جمع النقاط =====================
        elif call.data == "collect":
            markup = InlineKeyboardMarkup(row_width=2)
            btn_game = InlineKeyboardButton("اكتب واربح ✍", callback_data="play_game")
            btn_daily = InlineKeyboardButton("الهدية اليومية 🎁", callback_data="daily_gift")
            btn_invite = InlineKeyboardButton("رابط الدعوة 🔗", callback_data="invite_link")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            
            markup.row(btn_game, btn_daily)
            markup.row(btn_invite)
            markup.row(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>اهلآ بك في قسم تجميع النقاط 💎\nيمكنك تجميع النقاط من خلال :\nالهدية اليومية 🎁\nاكتب واربح ✍\nرابط الدعوة 🔗</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== الهدية اليومية =====================
        elif call.data == "daily_gift":
            user_id = call.from_user.id
            if not can_claim_daily(user_id):
                remaining = get_time_remaining_daily(user_id)
                if remaining:
                    hours, minutes = remaining
                    await call.answer(f"⚜️ لقد حصلت على هديتك بالفعل !\n⚜️ يمكنك الحصول عليها مره اخرى بعد {hours} ساعة و {minutes} دقيقة", show_alert=True)
                else:
                    await call.answer("⚜️ لقد حصلت على هديتك بالفعل !\n⚜️ تتوفر الهدية اليومية غداً", show_alert=True)
                return
            
            random_numbers = [random.randint(5, 30) for _ in range(4)]
            final_points = random_numbers[3]
            
            update_points_add(user_id, final_points)
            update_daily(user_id)
            log_daily_gift(user_id, final_points)
            
            for num in random_numbers:
                await context.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"🎁 تجربة حظك 🎁 {num}"
                )
                await asyncio.sleep(0.8)
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back_to_collect", style="danger")
            markup.add(btn_back)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"لقد حصلت على {final_points} نقطة ♥️",
                reply_markup=markup
            )
        
        # ===================== اكتب واربح =====================
        elif call.data == "play_game":
            user_id = call.from_user.id
            if not can_play_game(user_id):
                next_time = get_next_game_time(user_id)
                if next_time:
                    remaining = next_time - datetime.now()
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    await call.answer(f"⚜️ لقد كتبت الجملة اليوم!\n⚜️ يمكنك المحاولة مره اخرى بعد {hours} ساعة و {minutes} دقيقة", show_alert=True)
                else:
                    await call.answer("⚜️ لقد كتبت الجملة اليوم!\n⚜️ حاول غداً", show_alert=True)
                return
            
            context.user_data['awaiting_write_win'] = True
            context.user_data['write_win_user_id'] = user_id
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back_to_collect", style="danger")
            markup.add(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="اكتب جملة ⚜️ :\n\n( احب متجر النخبة )",
                reply_markup=markup
            )
        
        # ===================== رابط الدعوة =====================
        elif call.data == "invite_link":
            user_id = call.from_user.id
            bot_username = (await context.bot.get_me()).username
            link = f"https://t.me/{bot_username}?start={user_id}"
            total = get_total_invites(user_id)
            top_users = get_top_inviters()
            emojis = ["🥇", "🥈", "🥉"]
            top_text = ""
            for i, (uid, count) in enumerate(top_users):
                if i < 3:
                    top_text += f"{emojis[i]} <code>{uid}</code> : {count}\n"
            if not top_text:
                top_text = "لا يوجد مشاركات بعد"
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_copy = InlineKeyboardButton(
                "نسخ رابط الدعوة",
                copy_text=CopyTextButton(text=link),
            )
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back_to_collect", style="danger")
            markup.add(btn_copy)
            markup.add(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"<b>• شارك رابط الدعوة الخاص بك ♥️</b>\n\n"
                     f"- مقابل كل دعوة ستحصل على {POINTS_PER_REFERRAL} نقطة 💎\n\n"
                     f"- رابط الدعوة الخاص بك :\n"
                     f"<a href='{link}'>{link}</a>\n\n"
                     f"🔗 لقد دعوت : <code>{total}</code> عضو \n"
                     f"💰 مكافأة كل عضو : {POINTS_PER_REFERRAL} نقطة \n\n"
                     f"• الأكثر مشاركة لرابط الدعوة 🏆\n\n{top_text}",
                parse_mode='HTML',
                reply_markup=markup,
                disable_web_page_preview=True
            )
        
        # ===================== شحن النقاط =====================
        elif call.data == "recharge":
            markup = InlineKeyboardMarkup(row_width=1)
            
            btn_stars = InlineKeyboardButton("الشحن بالنجوم ⭐️", callback_data="recharge_stars")
            btn_crypto = InlineKeyboardButton("الشحن بالعملات الرقمية ☑️", callback_data="recharge_crypto")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            
            markup.row(btn_stars)
            markup.row(btn_crypto)
            markup.row(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>اهلا بك في قسم الشحن 💰\n- يرجى اختيار طريقة الشحن التي تريدها 🤩</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== شحن بالنجوم (مع رابط) =====================
        elif call.data == "recharge_stars":
            markup = InlineKeyboardMarkup(row_width=4)
            
            markup.row(
                InlineKeyboardButton("1 ⭐️", url=INVOICE_LINKS.get("star_1")),
                InlineKeyboardButton("2 ⭐️", url=INVOICE_LINKS.get("star_2")),
                InlineKeyboardButton("3 ⭐️", url=INVOICE_LINKS.get("star_3")),
                InlineKeyboardButton("4 ⭐️", url=INVOICE_LINKS.get("star_4"))
            )
            markup.row(
                InlineKeyboardButton("5 ⭐️", url=INVOICE_LINKS.get("star_5")),
                InlineKeyboardButton("10 ⭐️", url=INVOICE_LINKS.get("star_10")),
                InlineKeyboardButton("20 ⭐️", url=INVOICE_LINKS.get("star_20")),
                InlineKeyboardButton("30 ⭐️", url=INVOICE_LINKS.get("star_30"))
            )
            markup.row(
                InlineKeyboardButton("40 ⭐️", url=INVOICE_LINKS.get("star_40")),
                InlineKeyboardButton("50 ⭐️", url=INVOICE_LINKS.get("star_50"))
            )
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="recharge", style="danger"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>- اهـلا بك في قسم الشحن بالنجوم ⭐️\n- يـرجى اختيار عدد النقاط التي تريدها 🤩\n\nكل نجمة ⭐️ = 200 نقطة 💎</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== شحن بالعملات الرقمية =====================
        elif call.data == "recharge_crypto":
            markup = InlineKeyboardMarkup(row_width=1)
            btn1 = InlineKeyboardButton("Gram ( تون سابقًا )", callback_data="crypto_ton")
            btn2 = InlineKeyboardButton("USDT ( BEP20 )", callback_data="crypto_usdtbep20")
            btn3 = InlineKeyboardButton("USDT ( TRC20 )", callback_data="crypto_usdttrc20")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="recharge", style="danger")
            
            markup.add(btn1, btn2, btn3, btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>💰 | اسعار النقاط في متجر النخبة \n\n"
                     "- $1 = 10000 نقطة 💎 \n"
                     "- $2 = 20000 نقطة 💎\n"
                     "- $3 = 30000 نقطة 💎\n"
                     "- $4 = 40000 نقطة 💎\n"
                     "- $5 = 50000 نقطة 💎\n"
                     "- $10 = 100000 نقطة 💎\n"
                     "- $20 = 200000 نقطة 💎\n"
                     "- $50 = 500000 نقطة 💎\n"
                     "- $150 = 1500000 نقطة 💎\n"
                     "• يمكنك شحن حتى 100M نقطة 🤩\n\n"
                     "غير مسؤليين عن التحويلات الخاطئة❗️\n"
                     "- - - - - - - - - - - - - - - - - - - - - - - - - - - - -\n"
                     "طرق الدفع المتوفرة حاليآ : زين العراق ( الأثير )\n\n"
                     "الشحن اليدوي عن طريق الدعم : @NN25LL</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== اختيار عملة رقمية =====================
        # ===================== تأكيد الدفع - بدء انتظار رقم العملية =====================
        elif call.data == "crypto_confirm_paid":
            user_id = call.from_user.id
            currency_key = context.user_data.get('crypto_currency_key')
            currency = CRYPTO_NAMES.get(currency_key, currency_key)
            expected_amount = context.user_data.get('crypto_expected_amount')

            if not currency_key or expected_amount is None:
                await call.answer("انتهت صلاحية هذه العملية، يرجى البدء من جديد", show_alert=True)
                return

            context.user_data['waiting_crypto_txid'] = True

            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="recharge_crypto", style="danger")
            markup.add(btn_back)

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"<b>💰 الشحن بـ {currency}</b>\n\n"
                     f"<b>📩 أرسل الآن رقم العملية (TxID / Hash) الخاص بتحويلك</b>",
                parse_mode='HTML',
                reply_markup=markup
            )

        elif call.data.startswith("crypto_") and not call.data.startswith("crypto_paid_"):
            user_id = call.from_user.id
            currency_key = call.data.replace("crypto_", "")
            currency = CRYPTO_NAMES.get(currency_key, currency_key)
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="recharge_crypto", style="danger")
            markup.add(btn_back)
            
            ton_rate_line = f"\n<b>كل {TON_RATE} تون = 1$</b>\n" if currency_key == "ton" else ""

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"<b>💰 الشحن بـ {currency}</b>\n\n"
                     f"<b>أرسل المبلغ الذي تريد شحنه بالدولار</b>\n"
                     f"<b>مثال: 1</b>\n"
                     f"{ton_rate_line}\n"
                     f"<b>كل 1$ = {POINTS_PER_USD} نقطة 💎</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
            
            context.user_data['waiting_crypto_amount'] = True
            context.user_data['crypto_currency_key'] = currency_key
        
        # ===================== مشترياتي =====================
        elif call.data == "my_purchases":
            user_id = call.from_user.id
            purchases = get_user_purchases(user_id, source_filter='gifts')
            total = len(purchases)
            
            if total == 0:
                markup = InlineKeyboardMarkup(row_width=1)
                btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
                markup.add(btn_back)
                await context.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="لم تقم بشراء اي خدمة !",
                    reply_markup=markup
                )
                return
            
            text = f"<b>عدد مشترياتك ✅ : {total}</b>\n\n"
            
            for i, purchase in enumerate(purchases, 1):
                service_name, stars, price, purchase_number, date, status, service_id, link, quantity, provider_order_id, profit, source = purchase
                date_short = date.split()[0].replace('-', '/')
                display_name = service_name
                
                if "شحن" in service_name:
                    match = re.search(r'شحن (\d+) نقطة', service_name)
                    if match:
                        points_num = match.group(1)
                        display_name = f"شحن {points_num} نقطة 💎"
                elif "لمدة" in service_name and "ساعة" in service_name:
                    match = re.search(r'لمدة (\d+) ساعة', service_name)
                    if match:
                        hours = match.group(1)
                        display_name = f"اعلان لمدة {hours} ساعة 🕐"
                elif "عضو" in service_name:
                    match = re.search(r'(\d+) عضو', service_name)
                    if match:
                        members = match.group(1)
                        display_name = f"{members} عضو 👤"
                elif "نجمة" in service_name or "⭐️" in service_name:
                    clean_name = service_name.replace("⭐️", "").strip()
                    display_name = f"{clean_name} ⭐️"
                elif "رقم تليجرام" in service_name:
                    display_name = "رقم تليجرام 📱"
                elif "قناة" in service_name:
                    display_name = "قناة تليجرام 🧊"
                elif "تبرع" in service_name:
                    display_name = "تبرع 💙"
                
                text += f"{i}/ {display_name} - {date_short}\n"
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            markup.add(btn_back)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='HTML',
                reply_markup=markup
            )
        
        # ===================== معلومات حسابي =====================
        elif call.data == "my_info":
            user_id = call.from_user.id
            points = get_user_points(user_id)
            total_invites = get_total_invites(user_id)
            total_transfers = get_total_transfers(user_id)
            daily_count = get_daily_count(user_id)
            game_count = get_game_count(user_id)
            
            info_text = (
                f"<b>معلومات حسابي 💳</b>\n\n"
                f"🆔 ايديك : <code>{user_id}</code>\n"
                f"💎 نقاطك : {points}\n"
                f"👥 عدد دعواتك : {total_invites}\n"
                f"♻️ عدد تحويلاتك : {total_transfers}\n"
                f"🎁 عدد الهدايا اليومية : {daily_count}\n"
                f"🎮 عدد المرات التي لعبت بها : {game_count}"
            )
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            markup.add(btn_back)
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=info_text,
                reply_markup=markup,
                parse_mode="HTML"
            )
        
        # ===================== استخدام الكود =====================
        elif call.data == "use_code":
            user_id = call.from_user.id
            await call.answer()
            
            code_reply_sent[user_id] = False
            
            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            markup.add(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>يرجى ارسال الكود</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
            
            context.user_data['waiting_for_code'] = True
            context.user_data['code_user_id'] = user_id
        
        # ===================== رجوع =====================
        elif call.data == "back_to_collect":
            context.user_data['awaiting_write_win'] = False
            markup = InlineKeyboardMarkup(row_width=2)
            btn_game = InlineKeyboardButton("اكتب واربح ✍", callback_data="play_game")
            btn_daily = InlineKeyboardButton("الهدية اليومية 🎁", callback_data="daily_gift")
            btn_invite = InlineKeyboardButton("رابط الدعوة 🔗", callback_data="invite_link")
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
            
            markup.row(btn_game, btn_daily)
            markup.row(btn_invite)
            markup.row(btn_back)
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>اهلآ بك في قسم تجميع النقاط 💎\nيمكنك تجميع النقاط من خلال :\nالهدية اليومية 🎁\nاكتب واربح ✍\nرابط الدعوة 🔗</b>", parse_mode="HTML",
                reply_markup=markup
            )
        
        # ===================== تحديثات البوت (قنوات البوت) =====================
        elif call.data == "bot_updates":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.row(InlineKeyboardButton("اكتمال الطلبات 🏆", url="https://t.me/NNL38"))
            markup.row(InlineKeyboardButton("توزيع النقاط 💎", url="https://t.me/NN72D"))
            markup.row(InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger"))

            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="<b>قنوات البوت الرسمية ⚜️</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # ===================== رجوع للقائمة الرئيسية =====================
        elif call.data == "back":
            user_id = call.from_user.id
            points = get_user_points(user_id)
            total_services = get_total_services()
            
            welcome_text = (
                f"اهـلاَ بك عزيزي في متجر النخبة - Store\n"
                f"المتجر يوفر لك جميع الميزات المميزة \n"
                f"نقاطك 💎 | {points}\n"
                f"ايديك 🆔️ | `{user_id}`"
            )
            
            markup = InlineKeyboardMarkup(row_width=2)
            
            btn_rashek = InlineKeyboardButton("خدمات رشق 🛒", callback_data="rashek_services", style="success")
            btn1 = InlineKeyboardButton("هدايا وجوائز ⭐️", callback_data="gifts")
            btn2 = InlineKeyboardButton("تجميع النقاط 💎", callback_data="collect")
            btn3 = InlineKeyboardButton("تحويل النقاط ♻️", callback_data="transfer")
            btn4 = InlineKeyboardButton("استخدام الكود 💳", callback_data="use_code")
            btn5 = InlineKeyboardButton("مشترياتي 🛍", callback_data="my_purchases")
            btn6 = InlineKeyboardButton("معلومات حسابي 🤖", callback_data="my_info")
            btn7 = InlineKeyboardButton("شحن النقاط 💰", callback_data="recharge")
            btn_terms = InlineKeyboardButton("شروط البوت 📛", callback_data="terms_of_use", style="danger")
            btn8 = InlineKeyboardButton("اكتمال الطلبات 🏆", url="https://t.me/NNL38")
            btn_my_orders = InlineKeyboardButton("طلباتي 🗓", callback_data="my_orders", style="primary")
            btn_check_order = InlineKeyboardButton("فحص الطلب 🔍", callback_data="check_order", style="primary")
            btn_updates = InlineKeyboardButton("تحديثات البوت 🚀", callback_data="bot_updates", style="primary")
            btn_api = InlineKeyboardButton("واجهة ( API )", callback_data="noop", style="primary")
            btn10 = InlineKeyboardButton(f"عدد الخدمات المكتملة : {total_services} ✅️", callback_data="noop", style="success")
            
            markup.row(btn_rashek)
            markup.row(btn1)
            markup.row(btn2, btn3)
            markup.row(btn4, btn5)
            markup.row(btn6, btn7)
            markup.row(btn_my_orders, btn_check_order)
            markup.row(btn8, btn_terms)
            markup.row(btn_updates, btn_api)
            markup.row(btn10)
            
            if user_id in ADMIN_IDS:
                markup.row(InlineKeyboardButton("لوحة الأدمن 👑", callback_data="admin_panel", style="success"))
            
            await context.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=welcome_text,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        
        # ===================== تحويل النقاط =====================
        elif call.data == "transfer":
            await call.answer("♻️ تحويل النقاط", show_alert=True)
        
        # ===================== لا شيء =====================
        elif call.data == "noop":
            await call.answer()

        # ===================== إلغاء طلب دعم قناة معلّق (فوروارد) =====================
        elif call.data == "cancel_channel_support_request":
            context.user_data.pop('tg_support_request', None)
            context.user_data.pop('group_support_request', None)
            await call.answer("✅ تم إلغاء الطلب", show_alert=True)
        
        # ===================== قريباً =====================
        elif call.data == "soon":
            await call.answer("🚧 قريباً سيتم تفعيل هذه الخدمة", show_alert=True)
        
        # ===================== 💰 إدارة الرصيد والنقاط =====================
        # ===================== موافقة/رفض دعم قنوات تليجرام =====================
        elif call.data.startswith("approve_tgsup_"):
            purchase_number = int(call.data.split("_")[2])
            row = get_tg_channel_support_request_by_purchase(purchase_number)
            if not row:
                await call.answer("❌ الطلب غير موجود أو انحذف.", show_alert=True)
                return
            req_id, target_user_id, channel_username, channel_id, members, price, currency, status = row

            if status != 'pending':
                await call.answer("❌ تم التعامل مع هذا الطلب مسبقاً.", show_alert=True)
                return

            invite_link = None
            try:
                invite = await context.bot.create_chat_invite_link(
                    chat_id=channel_id,
                    name=f"دعم قنوات تليجرام - طلب {purchase_number}"
                )
                invite_link = invite.invite_link
                set_tg_request_invite_link(req_id, invite_link)
            except Exception as e:
                print(f"⚠️ تعذر إنشاء رابط دعوة خاص للقناة {channel_username}: {e}")
                await call.answer("⚠️ تعذر إنشاء رابط الدعوة - راجع رسالة التنبيه", show_alert=True)
                try:
                    await context.bot.send_message(
                        call.from_user.id,
                        f"<b>⚠️ تعذر إنشاء رابط دعوة للقناة @{channel_username} (طلب {purchase_number}).\n"
                        f"تأكد أن البوت أدمن بالقناة وعنده صلاحية دعوة المستخدمين، ثم أعد المحاولة (اضغط موافقة مرة أخرى).</b>",
                        parse_mode='HTML'
                    )
                except Exception:
                    pass
                return

            added = add_force_sub_channel(channel_username, channel_id, invite_link)
            update_tg_channel_support_status(req_id, 'approved', call.from_user.id)

            await call.answer("✅ تمت الموافقة")
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None
                )
            except:
                pass

            try:
                await context.bot.send_message(
                    target_user_id,
                    f"<b>✅ تمت الموافقة على طلبك!\n"
                    f"قناتك @{channel_username} أصبحت اشتراك اجباري بالبوت الآن ⚜️</b>",
                    parse_mode='HTML'
                )
            except:
                pass

            if not added:
                try:
                    await context.bot.send_message(
                        call.from_user.id,
                        f"⚠️ ملاحظة: القناة @{channel_username} كانت مضافة مسبقاً بقائمة الاشتراك الإجباري."
                    )
                except:
                    pass

        elif call.data.startswith("reject_tgsup_"):
            purchase_number = int(call.data.split("_")[2])
            row = get_tg_channel_support_request_by_purchase(purchase_number)
            if not row:
                await call.answer("❌ الطلب غير موجود أو انحذف.", show_alert=True)
                return
            req_id, target_user_id, channel_username, channel_id, members, price, currency, status = row

            if status != 'pending':
                await call.answer("❌ تم التعامل مع هذا الطلب مسبقاً.", show_alert=True)
                return

            update_tg_channel_support_status(req_id, 'rejected', call.from_user.id)

            await call.answer("❌ تم الرفض")
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None
                )
            except:
                pass

            try:
                await context.bot.send_message(
                    target_user_id,
                    f"<b>❌ تم رفض طلبك الخاص بدعم قناتك @{channel_username}.\n"
                    f"تواصل مع الدعم لمعرفة التفاصيل.</b>",
                    parse_mode='HTML'
                )
            except:
                pass

        elif call.data.startswith("approve_grpsup_"):
            purchase_number = int(call.data.split("_")[2])
            row = get_group_channel_support_request_by_purchase(purchase_number)
            if not row:
                await call.answer("❌ الطلب غير موجود أو انحذف.", show_alert=True)
                return
            req_id, target_user_id, channel_username, channel_id, members, price, currency, status = row

            if status != 'pending':
                await call.answer("❌ تم التعامل مع هذا الطلب مسبقاً.", show_alert=True)
                return

            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None
                )
            except:
                pass

            already_active = bool(get_group_force_sub_channels())
            if already_active:
                # في قناة فعالة حاليًا -> هاد الطلب يروح آخر الطابور بحسب أسبقية موافقة الأدمن
                update_group_channel_support_status(req_id, 'queued', call.from_user.id)
                await call.answer("✅ تمت الموافقة - أُضيف للطابور")
                try:
                    await context.bot.send_message(
                        target_user_id,
                        f"<b>✅ تمت الموافقة على طلبك!\n"
                        f"قناتك @{channel_username} أُضيفت لطابور الاشتراك الإجباري بكروب @{GROUP_SUPPORT_USERNAME}.\n"
                        f"بيتم تفعيلها تلقائيًا فور انتهاء دور القناة الحالية 🕐</b>",
                        parse_mode='HTML'
                    )
                except:
                    pass
            else:
                ok = await activate_group_request(
                    context.bot,
                    (req_id, target_user_id, channel_username, channel_id, members, price, currency),
                    admin_id=call.from_user.id
                )
                if ok:
                    await call.answer("✅ تمت الموافقة والتفعيل")
                else:
                    update_group_channel_support_status(req_id, 'queued', call.from_user.id)
                    await call.answer("⚠️ تمت الموافقة لكن تعذر إنشاء رابط الدعوة - راجع رسالة التنبيه", show_alert=True)

        elif call.data.startswith("reject_grpsup_"):
            purchase_number = int(call.data.split("_")[2])
            row = get_group_channel_support_request_by_purchase(purchase_number)
            if not row:
                await call.answer("❌ الطلب غير موجود أو انحذف.", show_alert=True)
                return
            req_id, target_user_id, channel_username, channel_id, members, price, currency, status = row

            if status != 'pending':
                await call.answer("❌ تم التعامل مع هذا الطلب مسبقاً.", show_alert=True)
                return

            update_group_channel_support_status(req_id, 'rejected', call.from_user.id)

            await call.answer("❌ تم الرفض")
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None
                )
            except:
                pass

            try:
                await context.bot.send_message(
                    target_user_id,
                    f"<b>❌ تم رفض طلبك الخاص بدعم قناتك @{channel_username}.\n"
                    f"تواصل مع الدعم لمعرفة التفاصيل.</b>",
                    parse_mode='HTML'
                )
            except:
                pass

        elif call.data == "grpverify_check":
            user_id = call.from_user.id
            channel_username, channel_id, invite_link = get_current_group_force_sub_channel()

            subscribed = await check_user_subscription(context.bot, user_id, channel_id)

            if subscribed:
                await call.answer("تم التحقق بنجاح، يمكنك التحدث الآن ✅️", show_alert=True)
                pending_group_force_sub_warnings.pop(user_id, None)
                await delete_force_sub_message_with_animation(
                    context.bot, call.message.chat.id, call.message.message_id, final_text="✅"
                )
            else:
                await call.answer("عليك الاشتراك بقناة الكروب أولًا ❗️", show_alert=True)

        elif call.data.startswith("verify_sub_"):
            user_id = call.from_user.id
            channel_id = call.data.split("_")[2]
            
            if await check_user_subscription(context.bot, user_id, channel_id):
                await call.answer("تم التحقق بنجاح، يمكنك التحدث الآن ✅️", show_alert=True)
                try:
                    await context.bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
            else:
                await call.answer("عليك الاشتراك بقناة الكروب أولًا ❗️", show_alert=True)
    
    except BadRequest as e:
        harmless = (
            "message is not modified" in str(e).lower()
            or "query is too old" in str(e).lower()
            or "query id is invalid" in str(e).lower()
        )
        if not harmless:
            print(f"❌ خطأ: {e}")
            try:
                await call.answer("حدث خطأ، حاول مرة أخرى", show_alert=True)
            except:
                pass
    except Exception as e:
        print(f"❌ خطأ: {e}")
        try:
            await call.answer("حدث خطأ، حاول مرة أخرى", show_alert=True)
        except:
            pass

# ===================== معالج استقبال الدفع الناجح (نجوم تليجرام) =====================
async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    try:
        user_id = message.from_user.id
        payment = message.successful_payment
        payload = payment.invoice_payload
        
        # ===== شحن النقاط =====
        if payload.startswith("recharge_"):
            parts = payload.split("_")
            stars = int(parts[1])
            points = int(parts[2])
            
            new_points = update_points_add(user_id, points)
            
            await context.bot.send_message(
                user_id,
                f"<b>✅ تم شحن حسابك بنجاح!\n"
                f"⭐️ {stars} نجمة = {points} نقطة\n"
                f"💎 رصيدك الجديد: {new_points} نقطة\n\n"
                f"★ شكراً لاستخدامك متجر النخبة ♥️</b>",
                parse_mode="HTML"
            )
            
            # إشعار للأدمن
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"💰 شحن جديد (نجوم)\n"
                        f"👤 المستخدم: {user_id}\n"
                        f"⭐️ {stars} نجمة = {points} نقطة"
                    )
                except:
                    pass
        
        # ===== دعم قنوات تليجرام - دفع بالنجوم =====
        elif payload.startswith("tgsupport_"):
            parts = payload.split("_")
            members = int(parts[1])
            stars = int(parts[2])

            purchase_number = add_purchase(user_id, f"{members} عضو (دعم قنوات تليجرام)", stars, 0, 'pending')
            add_completed_service(f"{members} عضو", user_id)

            await context.bot.send_message(
                user_id,
                f"<b>✅ وصل الشراء الخاص بك:\n"
                f"🤩 الخدمة: {members} عضو 👤\n"
                f"💸 الكلفة: {stars} نجمة ⭐️\n"
                f"🔎 رقم الخدمة: {purchase_number}\n"
                f"💎 رصيدك الجديد: {get_user_points(user_id)} نقطة\n"
                f"★ شكراً لاستخدامك بوت متجر النخبة ♥️</b>",
                parse_mode='HTML'
            )
            await context.bot.send_message(
                user_id,
                "<b>- يرجى رفع البوت ادمن في قناتك ❗️\n"
                "- اعطي للبوت ميزة دعوة المستخدمين ❗️\n"
                "- يرجى ارسال أي رساله من القناة للبوت ✅️</b>",
                parse_mode='HTML'
            )

            context.user_data['tg_support_request'] = {
                'members': members,
                'price': stars,
                'currency': 'stars',
                'purchase_number': purchase_number
            }

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"✅️ عملية شراء جديدة (دعم قنوات تليجرام - نجوم) ✅️\n"
                        f"🤩 الخدمة: {members} عضو 👤\n"
                        f"💸 السعر : {stars} نجمة ⭐️\n"
                        f"🔎 رقم الخدمة: {purchase_number}\n"
                        f"🆔️ المشتري : <code>{user_id}</code>\n"
                        f"🕐 التاريخ : {datetime.now().strftime('%Y/%m/%d %H:%M')}",
                        parse_mode='HTML'
                    )
                except:
                    pass

        # ===== إعلان مدفوع بالنجوم (دفع حقيقي عبر تيليجرام) =====
        elif payload.startswith("adpaid_"):
            parts = payload.split("_")
            hours = int(parts[1])
            stars = int(parts[2])
            ad_name = f"اعلان مدفوع لمدة {hours} ساعة"

            purchase_number = add_purchase(user_id, ad_name, stars, 0, 'pending')
            add_completed_service(ad_name, user_id)

            await context.bot.send_message(
                user_id,
                f"<b>✅ تم الدفع بنجاح!\n"
                f"🤩 الخدمة: {ad_name} 🕐\n"
                f"💸 الكلفة: {stars} نجمة ⭐️\n"
                f"🔎 رقم الخدمة: {purchase_number}\n"
                f"★ شكراً لاستخدامك بوت متجر النخبة ♥️</b>",
                parse_mode='HTML'
            )

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"✅️ عملية شراء جديدة (اعلان مدفوع بالنجوم) ✅️\n"
                        f"🤩 الخدمة: {ad_name} 🕐\n"
                        f"💸 السعر : {stars} نجمة ⭐️\n"
                        f"🔎 رقم الخدمة: {purchase_number}\n"
                        f"🆔️ المشتري : <code>{user_id}</code>\n"
                        f"🕐 التاريخ : {datetime.now().strftime('%Y/%m/%d %H:%M')}",
                        parse_mode='HTML'
                    )
                except:
                    pass

            await context.bot.send_message(
                user_id,
                "<b>يرجى ارسال الرساله الذي تريد الإعلان عنها ✅️</b>",
                parse_mode='HTML'
            )

            context.user_data['ad_waiting'] = {
                'purchase_number': purchase_number,
                'hours': hours,
                'price': stars,
                'name': ad_name,
                'currency': 'stars'
            }
                
    except Exception as e:
        print(f"❌ خطأ في معالجة الدفع: {e}")

# ===================== معالج الرسائل النصية =====================
async def handle_group_force_sub_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يمنع أي عضو غير مشترك بقناة الاشتراك الإجباري الحالية (قناة مدفوعة فعالة بالطابور،
    أو القناة الافتراضية لو ما في قناة فعالة) من التحدث بكروب دعم قناتك بالكروب.
    """
    message = update.message
    if message is None or message.from_user is None:
        return

    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        return

    channel_username, channel_id, invite_link = get_current_group_force_sub_channel()

    try:
        subscribed = await check_user_subscription(context.bot, user_id, channel_id)
    except Exception:
        return  # لا نعاقب المستخدم بسبب خطأ مؤقت بالفحص

    if subscribed:
        return

    # لو في رسالة اشتراك إجباري سابقة معلقة لنفس العضو، احذفها بتأثير انتقالي قبل إرسال الجديدة
    old_pending = pending_group_force_sub_warnings.pop(user_id, None)
    if old_pending:
        old_chat_id, old_message_id = old_pending
        asyncio.create_task(
            delete_force_sub_message_with_animation(context.bot, old_chat_id, old_message_id, final_text="🔄")
        )

    try:
        await message.delete()
    except Exception:
        pass

    url = invite_link if invite_link else f"https://t.me/{channel_username}"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.row(_PTBInlineKeyboardButton("📢 اضغط هنا للاشتراك بالقناة", url=url))
    markup.row(_PTBInlineKeyboardButton("✅ تحقق", callback_data="grpverify_check"))

    mention = f"<a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>"
    text = (
        f"٭ مرحبًا عزيزي {mention} 👾\n\n"
        f"- عليك الاشتراك في قناة الكروب لكي يمكنك التكلم.\n\n"
        f"اشترك ومن ثم اضغط على الزر 💕"
    )

    try:
        sent = await context.bot.send_message(
            message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )
        pending_group_force_sub_warnings[user_id] = (sent.chat_id, sent.message_id)
    except Exception:
        pass


def format_package_price(price, currency):
    if not price:
        return "مجاناً 🎁"
    if currency == 'stars':
        return f"{price} ⭐️"
    if currency == 'points':
        return f"{price} نقطة"
    return f"{price} {currency}"


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """يمسك أي استثناء غير متوقع بأي معالج بالبوت ويبلغ الأدمن بدل ما يختفي بصمت بالـ console."""
    tb_string = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    print(f"❌ [UNHANDLED ERROR] {tb_string}")

    short_tb = tb_string[-3000:]
    error_text = (
        f"<b>❌ صار خطأ غير متوقع بالبوت</b>\n\n"
        f"<code>{short_tb}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, error_text, parse_mode='HTML')
        except Exception:
            try:
                await context.bot.send_message(admin_id, f"❌ صار خطأ غير متوقع بالبوت:\n\n{short_tb}")
            except Exception:
                pass


async def complete_tg_support_request(bot, req_id, buyer_id, channel_username, channel_id, members, price, currency, stored_invite_link):
    if stored_invite_link:
        try:
            await bot.revoke_chat_invite_link(chat_id=channel_id, invite_link=stored_invite_link)
        except Exception as e:
            print(f"⚠️ تعذر تعطيل رابط الدعوة للقناة {channel_username}: {e}")

    try:
        remove_force_sub_channel(channel_id)
    except Exception as e:
        print(f"❌ فشل حذف القناة {channel_username} من الاشتراك الإجباري: {e}")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"❌ اكتملت باقة @{channel_username} لكن فشل حذفها من قائمة الاشتراك الإجباري:\n{e}"
                )
            except Exception:
                pass

    try:
        update_tg_channel_support_status(req_id, 'completed', None)
    except Exception as e:
        print(f"❌ فشل تحديث حالة الطلب {req_id}: {e}")

    try:
        await bot.send_message(
            buyer_id,
            f"<b>تم اكمال الاشتراك الإجباري ✅️\n"
            f"لقد حصلت على {members} عضو 👤\n"
            f"يوزر القناة : @{channel_username}\n"
            f"اسم الباقة : {members} عضو 👤\n"
            f"سعر الباقة : {format_package_price(price, currency)}</b>",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"❌ فشل إرسال إشعار الاكتمال للمشتري {buyer_id}: {e}")

    try:
        for uid in list(pending_global_force_sub_prompts.keys()):
            await refresh_or_clear_global_force_sub_prompt(bot, uid)
    except Exception as e:
        print(f"⚠️ فشل تحديث الأزرار العالقة: {e}")


async def complete_group_support_request(bot, req_id, buyer_id, channel_username, channel_id, members, price, currency, stored_invite_link):
    if stored_invite_link:
        try:
            await bot.revoke_chat_invite_link(chat_id=channel_id, invite_link=stored_invite_link)
        except Exception as e:
            print(f"⚠️ تعذر تعطيل رابط الدعوة للقناة {channel_username}: {e}")

    try:
        remove_group_force_sub_channel(channel_id)
    except Exception as e:
        print(f"❌ فشل حذف القناة {channel_username} من الاشتراك الإجباري بالكروب: {e}")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"❌ اكتملت باقة @{channel_username} لكن فشل حذفها من الاشتراك الإجباري بالكروب:\n{e}"
                )
            except Exception:
                pass

    try:
        update_group_channel_support_status(req_id, 'completed', None)
    except Exception as e:
        print(f"❌ فشل تحديث حالة الطلب {req_id}: {e}")

    try:
        await bot.send_message(
            buyer_id,
            f"<b>تم اكمال الاشتراك الإجباري ✅️\n"
            f"لقد حصلت على {members} عضو 👤\n"
            f"يوزر القناة : @{channel_username}\n"
            f"اسم الباقة : {members} عضو 👤\n"
            f"سعر الباقة : {format_package_price(price, currency)}</b>",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"❌ فشل إرسال إشعار الاكتمال للمشتري {buyer_id}: {e}")

    try:
        for uid, (warn_chat_id, warn_message_id) in list(pending_group_force_sub_warnings.items()):
            try:
                await delete_force_sub_message_with_animation(bot, warn_chat_id, warn_message_id, final_text="🔄")
            except Exception:
                pass
        pending_group_force_sub_warnings.clear()
    except Exception as e:
        print(f"⚠️ فشل تنظيف الأزرار العالقة: {e}")

    try:
        await activate_next_group_channel_if_needed(bot)
    except Exception as e:
        print(f"❌ فشل تفعيل القناة التالية بالطابور: {e}")


async def process_support_join_credit(bot, channel_id, user_id, link_url=None, source="unknown"):
    """
    نقطة دخول موحّدة لاحتساب انضمام عضو لحملة دعم (تليجرام أو كروب) - يستخدمها مسار
    الإشعارات (push/chat_member) ومسار الفحص المباشر (pull/get_chat_member) بنفس الوقت،
    مع حماية كاملة من الاحتساب المكرر عبر جدول support_request_joined_users.
    يرجع True لو انطبق على حملة نشطة (بغض النظر لو كان أول احتساب أو مكرر).
    """
    # ===== دعم قنوات تليجرام =====
    if link_url:
        req = get_active_tg_request_by_invite_link(link_url)
        stored_invite_link = link_url
    else:
        req = get_active_tg_request_by_channel_id(channel_id)
        stored_invite_link = req[8] if req else None

    if req:
        req_id, buyer_id, channel_username, req_channel_id, members, joined_count, price, currency = req[0], req[1], req[2], req[3], req[4], req[5], req[6], req[7]
        is_new = credit_join_if_new('tg', req_id, user_id)
        print(f"🔧 [JOIN DEBUG][{source}] tg_support_request مطابق (id={req_id}) | مستخدم جديد لهاي الجولة؟ {is_new}")
        if is_new:
            new_count = increment_tg_request_joined(req_id)
            print(f"🔧 [JOIN DEBUG][{source}] العداد بعد الزيادة: {new_count} / {members}")
            if new_count >= members:
                await complete_tg_support_request(bot, req_id, buyer_id, channel_username, req_channel_id, members, price, currency, stored_invite_link)
        return True

    # ===== دعم قناتك بالكروب =====
    if link_url:
        grp_req = get_active_group_request_by_invite_link(link_url)
        stored_grp_invite_link = link_url
    else:
        grp_req = get_active_group_request_by_channel_id(channel_id)
        stored_grp_invite_link = grp_req[8] if grp_req else None

    if grp_req:
        req_id, buyer_id, channel_username, req_channel_id, members, joined_count, price, currency = grp_req[0], grp_req[1], grp_req[2], grp_req[3], grp_req[4], grp_req[5], grp_req[6], grp_req[7]
        is_new = credit_join_if_new('group', req_id, user_id)
        print(f"🔧 [JOIN DEBUG][{source}] group_support_request مطابق (id={req_id}) | مستخدم جديد لهاي الجولة؟ {is_new}")
        if is_new:
            new_count = increment_group_request_joined(req_id)
            print(f"🔧 [JOIN DEBUG][{source}] العداد بعد الزيادة: {new_count} / {members}")
            if new_count >= members:
                await complete_group_support_request(bot, req_id, buyer_id, channel_username, req_channel_id, members, price, currency, stored_grp_invite_link)
        return True

    return False


async def handle_tgsup_channel_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يتتبع انضمام الأعضاء عبر رابط دعوة دعم قنوات تليجرام / دعم قناتك بالكروب المخصص.
    عند وصول العدد للحد المطلوب: يعطّل الرابط ويحذف القناة من الاشتراك الإجباري المناسب تلقائياً.
    """
    cmu = update.chat_member
    if cmu is None:
        return

    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status
    print(f"🔧 [JOIN DEBUG] chat_member تحديث وصل | chat={cmu.chat.id} ({cmu.chat.username}) | user={cmu.new_chat_member.user.id} | old_status={old_status} | new_status={new_status}")

    joined_statuses = ('member', 'restricted')
    if new_status not in joined_statuses or old_status in joined_statuses:
        print(f"🔧 [JOIN DEBUG] تجاهلت التحديث - مو انضمام جديد (old={old_status}, new={new_status})")
        return

    joining_user_id = cmu.new_chat_member.user.id
    joined_chat = cmu.chat

    # ===== حذف رسالة الاشتراك الإجباري تلقائيًا فور اشتراك العضو فعليًا بالقناة الحالية (بدون ضغط زر) =====
    try:
        cur_username, cur_channel_id, _ = get_current_group_force_sub_channel()
        matches_current = bool(
            (joined_chat.username and joined_chat.username.lower() == cur_username.lower())
            or str(cur_channel_id) == str(joined_chat.id)
        )
        if matches_current:
            pending = pending_group_force_sub_warnings.pop(joining_user_id, None)
            if pending:
                warn_chat_id, warn_message_id = pending
                await delete_force_sub_message_with_animation(
                    context.bot, warn_chat_id, warn_message_id, final_text="✅"
                )
    except Exception:
        pass

    invite_link_obj = cmu.invite_link
    raw_link_url = invite_link_obj.invite_link if invite_link_obj else None
    is_public_channel = bool(joined_chat.username)

    # القنوات العامة: تيليجرام غير موثوق بإرفاق invite_link الصحيح (أحيانًا يرفق رابط قديم/منتهي من انضمام سابق،
    # وأحيانًا ما يرفق شي إطلاقًا) -> نتجاهل قيمة الرابط كليًا ونعتمد فقط على القناة نفسها.
    # القنوات الخاصة: invite_link موثوق دايمًا -> نعتمد عليه للمطابقة الدقيقة.
    if is_public_channel:
        link_url = None
        print(f"🔧 [JOIN DEBUG] قناة عامة (@{joined_chat.username}) - رح أتجاهل قيمة invite_link (لو انرفقت) وأدور بالقناة نفسها" + (f" | الرابط اللي رفقه تيليجرام (متجاهَل): {raw_link_url}" if raw_link_url else ""))
    else:
        link_url = raw_link_url
        if link_url:
            print(f"🔧 [JOIN DEBUG] قناة خاصة - الرابط المستخدم بالانضمام: {link_url}")
        else:
            print(f"🔧 [JOIN DEBUG] قناة خاصة بس ماكو invite_link بالتحديث - راح يتجاهل الانضمام")

    # ===== احتساب الانضمام (تليجرام / كروب) عبر الدالة الموحّدة =====
    await process_support_join_credit(context.bot, joined_chat.id, joining_user_id, link_url=link_url, source="push")


async def handle_forwarded_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يستقبل أي نوع من رسائل التوجيه من القناة (نص، صورة، فيديو، ملف، صوت...)
    ويكمل خطوات دعم قنوات تليجرام بغض النظر عن نوع محتوى الرسالة الموجهة.
    مسجّلة بـ group=-1 حتى تعمل قبل بقية المعالجات وتلتقط أي نوع فوروارد.
    """
    message = update.message
    print(f"🔧 [FORWARD DEBUG] استلمت رسالة موجهة من user_id={message.from_user.id if message else None} | "
          f"tg_support_request موجود؟ {'tg_support_request' in context.user_data} | "
          f"group_support_request موجود؟ {'group_support_request' in context.user_data}")

    if message is None:
        return

    if 'tg_support_request' in context.user_data:
        pending_key = 'tg_support_request'
    elif 'group_support_request' in context.user_data:
        pending_key = 'group_support_request'
    else:
        return

    is_group_flow = (pending_key == 'group_support_request')
    request = context.user_data[pending_key]
    user_id = message.from_user.id

    origin = getattr(message, 'forward_origin', None)
    if not origin or getattr(origin, 'type', None) != 'channel':
        cancel_markup = InlineKeyboardMarkup(row_width=1)
        cancel_markup.add(InlineKeyboardButton("❌ إلغاء الطلب", callback_data="cancel_channel_support_request"))
        await context.bot.send_message(
            user_id,
            "❌ يرجى إرسال رسالة من القناة (توجيه/فوروارد) وليس من محادثة عادية",
            reply_markup=cancel_markup
        )
        raise ApplicationHandlerStop

    chat = origin.chat

    channel_username = chat.username or str(chat.id)
    channel_id = str(chat.id)

    permissions = await check_bot_admin_status(channel_id, context.bot)
    is_admin = permissions['is_admin']
    can_invite = permissions['can_invite']

    if is_admin and can_invite:
        if is_group_flow:
            add_group_channel_support_request(
                user_id, channel_username, channel_id,
                request['members'], request['price'], request['currency'], request['purchase_number']
            )
            approve_prefix, reject_prefix = "approve_grpsup_", "reject_grpsup_"
        else:
            add_tg_channel_support_request(
                user_id, channel_username, channel_id,
                request['members'], request['price'], request['currency'], request['purchase_number']
            )
            approve_prefix, reject_prefix = "approve_tgsup_", "reject_tgsup_"

        await context.bot.send_message(
            user_id,
            "<b>تم اكمال جميع الخطوات ✅️\nالمتبقي هوه موافقة الأدمن 🕐</b>",
            parse_mode='HTML'
        )

        user_info = get_user_info(user_id)
        admin_message = (
            f"<b>طلب موافقة جديد ✅️\n"
            f"المستخدم : {user_info['first_name']}\n"
            f"يوزرة: @{user_info['username']}\n"
            f"يوزر القناة : @{channel_username}\n"
            f"اسم الباقة : {request['members']} عضو\n"
            f"سعرها : {request['price']} {'نجمة ⭐️' if request['currency'] == 'stars' else 'نقطة'}\n"
            f"هل تريد الموافقة ؟</b>"
        )
        admin_keyboard = InlineKeyboardMarkup(row_width=2)
        admin_keyboard.row(
            InlineKeyboardButton("موافقة ✅️", callback_data=f"{approve_prefix}{request['purchase_number']}"),
            InlineKeyboardButton("رفض ❌️", callback_data=f"{reject_prefix}{request['purchase_number']}")
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, admin_message, parse_mode='HTML', reply_markup=admin_keyboard)
            except:
                pass

        del context.user_data[pending_key]

    elif is_admin and not can_invite:
        cancel_markup = InlineKeyboardMarkup(row_width=1)
        cancel_markup.add(InlineKeyboardButton("❌ إلغاء الطلب", callback_data="cancel_channel_support_request"))
        await message.reply_text(
            "<b>- اعطي للبوت ميزة دعوة المستخدمين ❗️\n"
            "- يرجى ارسال أي رساله من القناة للبوت ✅️</b>",
            parse_mode='HTML',
            reply_markup=cancel_markup
        )
    elif can_invite and not is_admin:
        cancel_markup = InlineKeyboardMarkup(row_width=1)
        cancel_markup.add(InlineKeyboardButton("❌ إلغاء الطلب", callback_data="cancel_channel_support_request"))
        await message.reply_text(
            "<b>- يرجى رفع البوت ادمن في قناتك ❗️\n"
            "- يرجى ارسال أي رساله من القناة للبوت ✅️</b>",
            parse_mode='HTML',
            reply_markup=cancel_markup
        )
    else:
        cancel_markup = InlineKeyboardMarkup(row_width=1)
        cancel_markup.add(InlineKeyboardButton("❌ إلغاء الطلب", callback_data="cancel_channel_support_request"))
        await message.reply_text(
            "<b>- يرجى رفع البوت ادمن في قناتك ❗️\n"
            "- اعطي للبوت ميزة دعوة المستخدمين ❗️\n"
            "- يرجى ارسال أي رساله من القناة للبوت ✅️</b>",
            parse_mode='HTML',
            reply_markup=cancel_markup
        )

    raise ApplicationHandlerStop


def normalize_arabic_text(text):
    text = text.strip()
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'\s+', ' ', text)
    return text

WRITE_WIN_PHRASE = "احب متجر النخبة"
WRITE_WIN_POINTS = 15

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.edited_message
    if message is None or message.from_user is None or not message.text:
        return
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in ADMIN_IDS and is_user_banned(user_id):
        return

    # ===== اكتب واربح =====
    if context.user_data.get('awaiting_write_win', False):
        if normalize_arabic_text(text) == normalize_arabic_text(WRITE_WIN_PHRASE):
            context.user_data['awaiting_write_win'] = False
            update_game_date(user_id)
            new_points = update_points_add(user_id, WRITE_WIN_POINTS)
            log_game_played(user_id, WRITE_WIN_POINTS)

            markup = InlineKeyboardMarkup(row_width=1)
            btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back_to_collect", style="danger")
            markup.add(btn_back)

            await message.reply_text(
                f"لقد حصلت على {WRITE_WIN_POINTS} نقطة ✅️",
                reply_markup=markup
            )
        else:
            await message.reply_text("يرجى كتابة الجملة بشكل صحيح ❌️")
        return

    # ===== إدخال مبلغ الشحن بالعملات الرقمية =====
    if context.user_data.get('waiting_crypto_amount', False):
        currency_key = context.user_data.get('crypto_currency_key')
        currency = CRYPTO_NAMES.get(currency_key, currency_key)
        wallet = CRYPTO_WALLETS.get(currency_key)

        try:
            usd_amount = float(text.replace(',', '.'))
        except ValueError:
            await message.reply_text("❌ أرسل رقم صحيح فقط (مثال: 5 أو 10.5)")
            return

        if usd_amount < 1:
            await message.reply_text("❌ أقل مبلغ للشحن هو 1$")
            return
        if usd_amount > 10000:
            await message.reply_text("❌ أكبر مبلغ للشحن هو 10000$ (100M نقطة)")
            return

        points = int(usd_amount * POINTS_PER_USD)

        if currency_key == "ton":
            crypto_amount = round(usd_amount * TON_RATE, 4)
            amount_line = f"<b>💵 المبلغ بالتون : {crypto_amount} TON = {points} نقطة 💎</b>\n\n"
        else:
            crypto_amount = usd_amount
            amount_line = f"<b>💵 المبلغ: {usd_amount}$ = {points} نقطة 💎</b>\n\n"

        context.user_data['waiting_crypto_amount'] = False
        context.user_data['crypto_expected_amount'] = crypto_amount
        context.user_data['crypto_usd_amount'] = usd_amount
        context.user_data['crypto_expected_points'] = points

        markup = InlineKeyboardMarkup(row_width=1)
        btn_paid = InlineKeyboardButton("✅ تم الدفع", callback_data="crypto_confirm_paid")
        btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="recharge_crypto", style="danger")
        markup.add(btn_paid, btn_back)

        await message.reply_text(
            f"<b>💰 الشحن بـ {currency}</b>\n\n"
            f"{amount_line}"
            f"<b>📌 أرسل المبلغ إلى المحفظة التالية:</b>\n<code>{wallet}</code>\n\n"
            f"<b>غير مسؤليين عن التحويلات الخاطئة❗️</b>\n\n"
            f"<b>📩 بعد إتمام التحويل، اضغط زر 'تم الدفع' ثم أرسل رقم العملية (TxID)</b>",
            parse_mode='HTML',
            reply_markup=markup
        )
        return

    # ===== إدخال رقم العملية (TxID) للتحقق التلقائي (محاولة واحدة فقط) =====
    if context.user_data.get('waiting_crypto_txid', False):
        currency_key = context.user_data.get('crypto_currency_key')
        currency = CRYPTO_NAMES.get(currency_key, currency_key)
        expected_amount = context.user_data.get('crypto_expected_amount')
        expected_points = context.user_data.get('crypto_expected_points')
        txid = text.strip()

        # الخروج من حالة الانتظار فورًا - محاولة واحدة فقط لكل ضغطة "تم الدفع"
        context.user_data['waiting_crypto_txid'] = False

        retry_markup = InlineKeyboardMarkup(row_width=1)
        retry_markup.add(InlineKeyboardButton("✅ تم الدفع", callback_data="crypto_confirm_paid"))
        retry_markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="recharge_crypto", style="danger"))

        if len(txid) < 10:
            await message.reply_text("رقم العملية غير صحيح أو غير موجود ❌️", reply_markup=retry_markup)
            return

        if is_crypto_txid_used(txid):
            await message.reply_text("رقم العملية غير صحيح أو غير موجود ❌️", reply_markup=retry_markup)
            return

        checking_msg = await message.reply_text("⏳ جاري التحقق من العملية على الشبكة...")

        success, result = await asyncio.to_thread(
            verify_crypto_transaction, currency_key, txid, expected_amount
        )

        if not success:
            await checking_msg.edit_text("رقم العملية غير صحيح أو غير موجود ❌️")
            await message.reply_text("اضغط 'تم الدفع' لإعادة المحاولة برقم عملية جديد.", reply_markup=retry_markup)
            return

        saved = save_crypto_transaction(txid, user_id, currency_key, expected_amount, expected_points)
        if not saved:
            await checking_msg.edit_text("رقم العملية غير صحيح أو غير موجود ❌️")
            await message.reply_text("اضغط 'تم الدفع' لإعادة المحاولة برقم عملية جديد.", reply_markup=retry_markup)
            return

        new_balance = update_points_add(user_id, expected_points)
        add_purchase(user_id, f"شحن {currency}", 0, expected_points, status='completed',
                     source='crypto_recharge', profit=0)

        usd_amount = context.user_data.get('crypto_usd_amount', expected_amount)

        context.user_data.pop('crypto_currency_key', None)
        context.user_data.pop('crypto_expected_amount', None)
        context.user_data.pop('crypto_usd_amount', None)
        context.user_data.pop('crypto_expected_points', None)

        markup = InlineKeyboardMarkup(row_width=1)
        btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger")
        markup.add(btn_back)

        await checking_msg.edit_text(
            f"✅ تم التحقق من الدفع بنجاح!\n\n"
            f"💰 المبلغ: {usd_amount}$\n"
            f"💎 النقاط المضافة: {expected_points}\n"
            f"🏦 رصيدك الحالي: {new_balance} نقطة\n\n"
            f"★ شكراً لاستخدامك متجر النخبة ♥️"
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"<b>💰 عملية شحن عملات رقمية مؤكدة تلقائيًا</b>\n\n"
                    f"<b>👤 المستخدم: <code>{user_id}</code></b>\n"
                    f"<b>💵 العملة: {currency}</b>\n"
                    f"<b>💰 المبلغ: {usd_amount}$</b>\n"
                    f"<b>💎 النقاط: {expected_points}</b>\n"
                    f"<b>🔗 رقم العملية: <code>{txid}</code></b>",
                    parse_mode='HTML'
                )
            except:
                pass
        return

    # ===== فحص الطلب (إدخال رقم الطلب) =====
    if context.user_data.get('waiting_check_order', False):
        context.user_data['waiting_check_order'] = False
        if not text.isdigit():
            await message.reply_text("❌ يجب إرسال رقم الطلب فقط (أرقام).")
            return
        purchase_number = int(text)
        order = get_purchase_by_number(purchase_number, user_id=user_id)

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("الرجوع 🔙", callback_data="back", style="danger"))

        if not order:
            await message.reply_text("❌ لم يتم العثور على طلب بهذا الرقم على حسابك.", reply_markup=markup)
            return

        (o_user_id, service_name, stars, price, p_number, date, status,
         service_id, link, quantity, provider_order_id, profit, source) = order

        status_text = "اكتمل الطلب بنجاح !" if status == 'completed' else status
        try:
            dt = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
            date_display = format_order_date(dt)
        except Exception:
            date_display = date

        await message.reply_text(
            f"<b>تفاصيل الطلب :\n\n"
            f"🛒 | الخدمة : {service_name}\n"
            f"🔰 | الكمية : {quantity}\n"
            f"💰 | السعر : {price} نقطة \n"
            f"📅 | تاريخ الطلب : {date_display}\n"
            f"🔗 | رابط الطلب : {link or '—'}\n"
            f"✅️ | حالة الطلب : {status_text}</b>",
            parse_mode='HTML',
            reply_markup=markup
        )
        return

    # ===== إعدادات عامة (setting_edit_*) =====
    if context.user_data.get('awaiting_setting_key'):
        key = context.user_data.pop('awaiting_setting_key')
        if user_id not in ADMIN_IDS:
            return
        set_setting(key, text)
        await message.reply_text(f"✅ تم تحديث الإعداد بنجاح.\n\nالقيمة الجديدة:\n{text}")
        return

    # ===== عمليات الرصيد/النقاط/النجوم =====
    if context.user_data.get('balance_action'):
        action = context.user_data.pop('balance_action')
        if user_id not in ADMIN_IDS:
            return
        parts = text.split()
        try:
            if action in ("admin_add_balance", "admin_remove_balance"):
                target_id, amount = int(parts[0]), int(parts[1])
                conn = sqlite3.connect('bot_database.db')
                c = conn.cursor()
                delta = amount if action == "admin_add_balance" else -amount
                c.execute('UPDATE users SET points = points + ? WHERE user_id = ?', (delta, target_id))
                conn.commit()
                conn.close()
                log_admin_action(user_id, message.from_user.first_name or "أدمن", action, target_user=target_id, value=str(amount))
                await message.reply_text(f"✅ تم {'إضافة' if delta > 0 else 'خصم'} {amount} نقطة للمستخدم {target_id}")
                try:
                    await context.bot.send_message(target_id, f"💎 تم {'إضافة' if delta > 0 else 'خصم'} {amount} نقطة من رصيدك من قبل الإدارة.")
                except Exception:
                    pass

            elif action == "admin_transfer_balance":
                from_id, to_id, amount = int(parts[0]), int(parts[1]), int(parts[2])
                conn = sqlite3.connect('bot_database.db')
                c = conn.cursor()
                c.execute('UPDATE users SET points = points - ? WHERE user_id = ?', (amount, from_id))
                c.execute('UPDATE users SET points = points + ? WHERE user_id = ?', (amount, to_id))
                conn.commit()
                conn.close()
                log_admin_action(user_id, message.from_user.first_name or "أدمن", action, target_user=to_id, value=f"{amount} من {from_id}")
                await message.reply_text(f"✅ تم تحويل {amount} نقطة من {from_id} إلى {to_id}")

            elif action in ("admin_add_stars", "admin_remove_stars"):
                target_id, amount = int(parts[0]), int(parts[1])
                conn = sqlite3.connect('bot_database.db')
                c = conn.cursor()
                delta = amount if action == "admin_add_stars" else -amount
                c.execute('UPDATE users SET stars = stars + ? WHERE user_id = ?', (delta, target_id))
                conn.commit()
                conn.close()
                log_admin_action(user_id, message.from_user.first_name or "أدمن", action, target_user=target_id, value=str(amount))
                await message.reply_text(f"✅ تم {'إضافة' if delta > 0 else 'خصم'} {amount} نجمة للمستخدم {target_id}")
        except (ValueError, IndexError):
            await message.reply_text("❌ صيغة غير صحيحة، تأكد من الأرقام وأعد المحاولة.")
        return

    # ===== إضافة وسيلة دفع =====
    if context.user_data.get('awaiting_payment_add', False):
        context.user_data['awaiting_payment_add'] = False
        if user_id not in ADMIN_IDS:
            return
        if '|' not in text:
            await message.reply_text("❌ الصيغة غير صحيحة، استخدم: الاسم | التفاصيل")
            return
        name, details = [p.strip() for p in text.split('|', 1)]
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('INSERT INTO payment_methods (name, details, sort_order, status) VALUES (?, ?, 0, 1)', (name, details))
        conn.commit()
        conn.close()
        await message.reply_text(f"✅ تم إضافة وسيلة الدفع: {name}")
        return

    # ===== إنشاء كوبون =====
    if context.user_data.get('awaiting_coupon_create', False):
        context.user_data['awaiting_coupon_create'] = False
        if user_id not in ADMIN_IDS:
            return
        try:
            code, points, max_uses = [p.strip() for p in text.split('|')]
            code = code.upper()
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('INSERT INTO coupons (code, points, max_uses, used_count, created_date, status) VALUES (?, ?, ?, 0, ?, 1)',
                      (code, int(points), int(max_uses), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            conn.close()
            await message.reply_text(f"✅ تم إنشاء الكوبون: {code}")
        except (ValueError, sqlite3.IntegrityError):
            await message.reply_text("❌ صيغة غير صحيحة أو الكود مستخدم مسبقًا.\nاستخدم: الكود | النقاط | عدد الاستخدامات")
        return

    # ===== بحث عن طلب =====
    if context.user_data.get('awaiting_order_search', False):
        context.user_data['awaiting_order_search'] = False
        if user_id not in ADMIN_IDS:
            return
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        if text.isdigit():
            c.execute('SELECT id, user_id, service_name, price, status, date FROM purchases WHERE id = ? OR user_id = ? ORDER BY id DESC LIMIT 15', (text, text))
        else:
            c.execute('SELECT id, user_id, service_name, price, status, date FROM purchases WHERE service_name LIKE ? ORDER BY id DESC LIMIT 15', (f'%{text}%',))
        rows = c.fetchall()
        conn.close()
        if not rows:
            await message.reply_text("❌ لا توجد نتائج مطابقة.")
            return
        result_text = "🔍 نتائج البحث:\n\n"
        for pid, uid, sname, price, status, d in rows:
            result_text += f"#{pid} | 👤{uid} | {sname} | 💎{price} | {status} | {d}\n"
        await message.reply_text(result_text)
        return

    # ===== إلغاء طلب =====
    if context.user_data.get('awaiting_cancel_order_id', False):
        context.user_data['awaiting_cancel_order_id'] = False
        if user_id not in ADMIN_IDS:
            return
        if not text.isdigit():
            await message.reply_text("❌ يجب إرسال رقم صحيح.")
            return
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('UPDATE purchases SET status = "cancelled" WHERE id = ?', (int(text),))
        conn.commit()
        conn.close()
        await message.reply_text(f"✅ تم إلغاء الطلب #{text}")
        return

    # ===== تعليم طلب كمكتمل يدويًا =====
    if context.user_data.get('awaiting_manual_delivery_id', False):
        context.user_data['awaiting_manual_delivery_id'] = False
        if user_id not in ADMIN_IDS:
            return
        if not text.isdigit():
            await message.reply_text("❌ يجب إرسال رقم صحيح.")
            return
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('UPDATE purchases SET status = "completed" WHERE id = ?', (int(text),))
        conn.commit()
        conn.close()
        await message.reply_text(f"✅ تم تعليم الطلب #{text} كمكتمل يدويًا")
        return

    # ===== إضافة خدمة =====
    if context.user_data.get('awaiting_service_add', False):
        context.user_data['awaiting_service_add'] = False
        if user_id not in ADMIN_IDS:
            return
        try:
            name, category, provider_service_id, price = [p.strip() for p in text.split('|')]
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('''INSERT INTO services (service_id, name, category, provider_service_id, price, status)
                         VALUES (?, ?, ?, ?, ?, 1)''',
                      (provider_service_id, name, category, provider_service_id, int(price)))
            conn.commit()
            conn.close()
            await message.reply_text(f"✅ تم إضافة الخدمة: {name}")
        except ValueError:
            await message.reply_text("❌ صيغة غير صحيحة.\nاستخدم: الاسم | التصنيف | رقم خدمة المزود | السعر")
        return

    # ===== إضافة مزود =====
    if context.user_data.get('awaiting_provider_add', False):
        context.user_data['awaiting_provider_add'] = False
        if user_id not in ADMIN_IDS:
            return
        try:
            name, api_url, api_key = [p.strip() for p in text.split('|')]
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('INSERT INTO providers (name, api_url, api_key, status, priority) VALUES (?, ?, ?, 1, 0)', (name, api_url, api_key))
            conn.commit()
            conn.close()
            await message.reply_text(f"✅ تم إضافة المزود: {name}")
        except ValueError:
            await message.reply_text("❌ صيغة غير صحيحة.\nاستخدم: الاسم | رابط API | مفتاح API")
        return

    # ===== الإذاعة (نص/صورة/فيديو/مستهدفة) =====
    if context.user_data.get('awaiting_broadcast_content', False):
        context.user_data['awaiting_broadcast_content'] = False
        if user_id not in ADMIN_IDS:
            return

        mode = context.user_data.pop('broadcast_mode', 'admin_broadcast_text')

        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('SELECT user_id FROM users')
        all_users = [row[0] for row in c.fetchall()]
        conn.close()

        content = text
        sent, failed = 0, 0
        context.bot_data['broadcast_stop'] = False

        await message.reply_text(f"📣 بدأت الإذاعة لـ {len(all_users)} مستخدم...")

        for uid in all_users:
            if context.bot_data.get('broadcast_stop'):
                break
            try:
                await context.bot.send_message(uid, content)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)

        log_admin_action(user_id, message.from_user.first_name or "أدمن", "broadcast", value=f"{mode}", result=f"نجح: {sent} / فشل: {failed}")
        await message.reply_text(f"✅ انتهت الإذاعة\n\nتم الإرسال: {sent}\nفشل: {failed}")
        return

    # ===== استعادة نسخة احتياطية =====
    if context.user_data.get('awaiting_backup_file', False) and message.document:
        context.user_data['awaiting_backup_file'] = False
        if user_id not in ADMIN_IDS:
            return
        file = await context.bot.get_file(message.document.file_id)
        await file.download_to_drive('bot_database.db')
        await message.reply_text("✅ تم استعادة النسخة الاحتياطية بنجاح. يفضّل إعادة تشغيل البوت الآن.")
        return

    # ===== إضافة مستخدم يدويًا (للأدمن) =====
    if context.user_data.get('waiting_add_user_id', False):
        if user_id not in ADMIN_IDS:
            return
        context.user_data['waiting_add_user_id'] = False

        if not text.isdigit():
            await message.reply_text("❌ يجب إرسال رقم ID صحيح.")
            return

        target_id = int(text)
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('SELECT user_id FROM users WHERE user_id = ?', (target_id,))
        exists = c.fetchone()
        if exists:
            conn.close()
            await message.reply_text("⚠️ هذا المستخدم موجود بالفعل بقاعدة البيانات.")
            return

        c.execute('''INSERT INTO users (user_id, points, is_banned, join_date, last_active, username, first_name)
                     VALUES (?, 0, 0, ?, ?, NULL, NULL)''',
                  (target_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        await message.reply_text(f"✅ تم إنشاء حساب جديد للمستخدم <code>{target_id}</code>", parse_mode='HTML')
        return

    # ===== استقبال الكمية وحساب السعر =====
    if context.user_data.get('awaiting_smm_quantity', False):
        context.user_data['awaiting_smm_quantity'] = False

        if not text.isdigit() or int(text) <= 0:
            await message.reply_text("❌ يجب إرسال رقم صحيح للكمية.")
            return

        quantity = int(text)
        min_order = context.user_data.get('smm_min_order', 1)
        max_order = context.user_data.get('smm_max_order', 1000000)
        if quantity < min_order or quantity > max_order:
            await message.reply_text(f"❌ الكمية يجب أن تكون بين {min_order} و {max_order}.")
            context.user_data['awaiting_smm_quantity'] = True
            return

        price_per_1000 = context.user_data.get('smm_price_per_1000', 0)
        total_price = round((price_per_1000 / 1000) * quantity)

        current_points = get_user_points(user_id)
        if current_points < total_price:
            await message.reply_text(f"❌ رصيدك غير كافٍ!\nالسعر المطلوب: {total_price} نقطة\nرصيدك الحالي: {current_points} نقطة")
            context.user_data.pop('smm_service_id', None)
            context.user_data.pop('smm_price_per_1000', None)
            return

        context.user_data['smm_quantity'] = quantity
        context.user_data['smm_total_price'] = total_price
        context.user_data['awaiting_smm_link'] = True
        await message.reply_text(f"💎 التكلفة الإجمالية: {total_price} نقطة\n\n🔗 أرسل الآن رابط الحساب/المنشور المطلوب تنفيذ الخدمة عليه:")
        return

    # ===== استقبال الرابط وعرض ملخص التأكيد =====
    if context.user_data.get('awaiting_smm_link', False):
        context.user_data['awaiting_smm_link'] = False
        context.user_data['smm_link'] = text

        quantity = context.user_data.get('smm_quantity')
        total_price = context.user_data.get('smm_total_price')

        markup = InlineKeyboardMarkup(row_width=2)
        markup.row(
            InlineKeyboardButton("✅ تأكيد الطلب", callback_data="smm_confirm", style="success"),
            InlineKeyboardButton("❌ إلغاء", callback_data="smm_cancel", style="danger")
        )

        await message.reply_text(
            f"<b>📋 ملخص الطلب</b>\n\n"
            f"🔗 الرابط: {text}\n"
            f"🔢 الكمية: {quantity}\n"
            f"💎 التكلفة: {total_price} نقطة\n\n"
            f"هل تريد تأكيد الطلب؟",
            parse_mode='HTML',
            reply_markup=markup
        )
        return

    # ===== إضافة قناة اشتراك إجباري (للأدمن) =====
    if context.user_data.get('awaiting_force_sub_channel', False):
        if user_id not in ADMIN_IDS:
            return
        context.user_data['awaiting_force_sub_channel'] = False

        try:
            chat = await context.bot.get_chat(text)
        except Exception:
            await message.reply_text("❌ لم أستطع الوصول للقناة. تأكد من المعرف/الـ ID وأن البوت مضاف لها كأدمن.")
            return

        channel_id = chat.id
        username = f"@{chat.username}" if chat.username else (chat.title or text)

        try:
            me = await context.bot.get_me()
            member = await context.bot.get_chat_member(channel_id, me.id)
            is_admin = member.status in ['administrator', 'creator']
        except Exception:
            is_admin = False

        added = add_force_sub_channel(username, channel_id)
        if not added:
            await message.reply_text("⚠️ هذه القناة مضافة مسبقًا.")
            return

        warn = "" if is_admin else "\n\n⚠️ تنبيه: البوت ليس أدمن في هذه القناة، لن يعمل التحقق حتى يُمنح صلاحية الأدمن."
        await message.reply_text(f"✅ تم إضافة القناة: {username}{warn}")
        return

    # ===== تعيين عدد الانضمامات لقناة إجبارية (حذف تلقائي عند الوصول للعدد) =====
    if context.user_data.get('awaiting_fsub_target', False):
        context.user_data['awaiting_fsub_target'] = False
        if user_id not in ADMIN_IDS:
            return

        channel_id = context.user_data.pop('fsub_target_channel_id', None)
        channel_username = context.user_data.pop('fsub_target_channel_username', 'القناة')

        if not channel_id:
            await message.reply_text("❌ انتهت صلاحية الطلب، افتح إدارة القنوات الإجبارية وحاول من جديد.")
            return

        try:
            target = int(text)
            if target <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("❌ أرسل رقم صحيح أكبر من 0.")
            return

        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=channel_id, name=f"هدف {target} عضو", member_limit=target
            )
        except Exception as e:
            await message.reply_text(
                f"❌ تعذّر إنشاء رابط الدعوة: {e}\n"
                f"تأكد أن البوت أدمن بالقناة وعنده صلاحية دعوة المستخدمين."
            )
            return

        req_id = add_tg_channel_support_request(user_id, channel_username, channel_id, target, 0, 'FREE', 0)
        set_tg_request_invite_link(req_id, invite.invite_link)
        update_tg_channel_support_status(req_id, 'approved', user_id)

        await message.reply_text(
            f"<b>✅ تم تعيين الهدف: {target} عضو للقناة {channel_username}</b>\n"
            f"🔗 رابط الدعوة الخاص: {invite.invite_link}\n\n"
            f"بمجرد ما يوصل عدد المنضمين عبر هذا الرابط للعدد المطلوب، بتنحذف القناة تلقائيًا من الاشتراك الإجباري.",
            parse_mode='HTML'
        )
        return

    # ===== ضبط مدة النشر التلقائي لكود نقاط =====
    if context.user_data.get('awaiting_autopost_interval', False):
        context.user_data['awaiting_autopost_interval'] = False
        if user_id not in ADMIN_IDS:
            return

        try:
            minutes = int(text)
            if minutes <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("❌ أرسل رقم صحيح أكبر من 0 (بالدقائق).")
            return

        set_setting('autopost_interval_minutes', minutes)
        scheduled = schedule_autopost_job(context.application, minutes)

        if scheduled:
            await message.reply_text(
                f"✅ تم تفعيل النشر التلقائي كل {minutes} دقيقة بقناة @{AUTOPOST_CHANNEL}.\n"
                f"أول نشرة رح تطلع خلال ثوان."
            )
        else:
            await message.reply_text(
                "⚠️ تم حفظ الإعداد، لكن جدولة المهمة فشلت (job_queue غير مفعّل بالبيئة).\n"
                "لازم تثبّت: pip install \"python-telegram-bot[job-queue]\" وتعيد تشغيل البوت."
            )
        return

    # ===== استخدام كود نقاط =====
    if context.user_data.get('awaiting_coupon_redeem', False):
        context.user_data['awaiting_coupon_redeem'] = False

        code = text.strip().upper()
        coupon = get_coupon_by_code(code)

        if not coupon:
            await message.reply_text("❌ الكود غير صحيح.")
            return

        coupon_id, coupon_points, max_uses, used_count, status = coupon

        if status != 1:
            await message.reply_text("❌ هذا الكود غير فعّال حاليًا.")
            return
        if used_count >= max_uses:
            await message.reply_text("❌ انتهت الاستخدامات المسموحة لهذا الكود.")
            return
        if has_user_redeemed_coupon(coupon_id, user_id):
            await message.reply_text("❌ لقد استخدمت هذا الكود مسبقًا.")
            return

        redeem_coupon(coupon_id, user_id)
        new_points = update_points_add(user_id, coupon_points)

        await message.reply_text(
            f"<b>✅ تم شحن {coupon_points} نقطة بنجاح!\n"
            f"💎 رصيدك الجديد: {new_points} نقطة</b>",
            parse_mode='HTML'
        )
        return

    # ===== البحث عن مستخدم (للأدمن) =====
    if context.user_data.get('waiting_search_user', False):
        if user_id not in ADMIN_IDS:
            return
        
        search_term = text
        
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        
        try:
            if text.startswith('@'):
                username = text[1:]
                c.execute('SELECT user_id, username, first_name, points, balance, stars, is_banned, join_date, last_active, total_purchases FROM users WHERE username LIKE ?', (f'%{username}%',))
            elif text.isdigit():
                c.execute('SELECT user_id, username, first_name, points, balance, stars, is_banned, join_date, last_active, total_purchases FROM users WHERE user_id = ?', (int(text),))
            else:
                c.execute('SELECT user_id, username, first_name, points, balance, stars, is_banned, join_date, last_active, total_purchases FROM users WHERE first_name LIKE ?', (f'%{text}%',))
        except:
            c.execute('SELECT user_id, username, first_name, points, balance, stars, is_banned, join_date, last_active, total_purchases FROM users WHERE username LIKE ?', (f'%{text}%',))
        
        results = c.fetchall()
        conn.close()
        
        if not results:
            await context.bot.send_message(
                user_id,
                f"❌ لم يتم العثور على مستخدم: {text}"
            )
            del context.user_data['waiting_search_user']
            return
        
        text_result = f"<b>🔍 نتائج البحث عن: {text}</b>\n\n"
        for user in results:
            uid, username, name, points, balance, stars, banned, join_date, last_active, purchases = user
            status = "🚫 محظور" if banned else "✅ نشط"
            text_result += (
                f"<b>━━━━━━━━━━━━━━</b>\n"
                f"🆔 <code>{uid}</code>\n"
                f"👤 {name or 'مستخدم'}\n"
                f"📛 @{username or 'لا يوجد'}\n"
                f"💎 النقاط: {points}\n"
                f"💰 الرصيد: {balance}\n"
                f"⭐ النجوم: {stars}\n"
                f"📦 المشتريات: {purchases}\n"
                f"📅 التسجيل: {join_date or 'غير معروف'}\n"
                f"🕐 آخر نشاط: {last_active or 'غير معروف'}\n"
                f"📌 الحالة: {status}\n"
            )
        
        markup = InlineKeyboardMarkup(row_width=2)
        btn_actions = InlineKeyboardButton("⚙️ عمليات", callback_data=f"admin_user_actions_{uid}")
        btn_back = InlineKeyboardButton("الرجوع 🔙", callback_data="admin_users_menu", style="danger")
        markup.row(btn_actions)
        markup.row(btn_back)
        
        await context.bot.send_message(
            user_id,
            text_result,
            parse_mode='HTML',
            reply_markup=markup
        )
        
        del context.user_data['waiting_search_user']
        return
    
    # ===== إضافة أدمن (للأدمن) =====
    if context.user_data.get('waiting_add_admin', False):
        if user_id not in ADMIN_IDS:
            return

        try:
            target_user = int(text.strip())
        except ValueError:
            await context.bot.send_message(user_id, "❌ آيدي غير صحيح! أرسل رقم آيدي المستخدم فقط.\n\nمثال: 123456789")
            return

        if target_user in ADMIN_IDS:
            await context.bot.send_message(user_id, f"⚠️ المستخدم {target_user} أدمن أصلاً.")
            del context.user_data['waiting_add_admin']
            return

        try:
            await context.bot.get_chat(target_user)
        except Exception:
            await context.bot.send_message(
                user_id,
                f"❌ الآيدي {target_user} مش حساب تليجرام حقيقي (تعذّر العثور عليه)!\nلم يتم إضافته كأدمن."
            )
            return

        add_extra_admin(target_user)
        log_action(user_id, "أدمن", "add_admin", target_user, "", 'success')

        await context.bot.send_message(user_id, f"✅ تمت إضافة {target_user} كأدمن جديد بنجاح.")
        try:
            await context.bot.send_message(
                target_user,
                "<b>👑 تمت ترقيتك لأدمن بالبوت!\nصار عندك صلاحية استخدام /admin ولوحة تحكم الأدمن.</b>",
                parse_mode='HTML'
            )
        except Exception:
            pass

        del context.user_data['waiting_add_admin']
        return

    # ===== إضافة نقاط (للأدمن) =====
    if context.user_data.get('waiting_add_points', False):
        if user_id not in ADMIN_IDS:
            return
        
        try:
            parts = text.split()
            
            if len(parts) != 2:
                await context.bot.send_message(
                    user_id,
                    "❌ صيغة غير صحيحة!\n"
                    "أرسل: ايدي_المستخدم عدد_النقاط\n\n"
                    "مثال: 123456789 1000"
                )
                return
            
            target_user = int(parts[0])
            points = int(parts[1])
            
            if points <= 0:
                await context.bot.send_message(user_id, "❌ عدد النقاط يجب أن يكون أكبر من 0!")
                return
            
            # تحقق إن الآيدي حساب تليجرام حقيقي قبل ما نكتب أي نقطة بقاعدة البيانات
            # (يمنع حالات عكس الترتيب زي: كتابة "50000 7094462233" وقصدك العكس)
            try:
                await context.bot.get_chat(target_user)
            except Exception:
                await context.bot.send_message(
                    user_id,
                    f"❌ الآيدي {target_user} مش حساب تليجرام حقيقي (تعذّر العثور عليه)!\n"
                    f"تأكد من الترتيب: <b>آيدي_المستخدم</b> أولاً ثم <b>عدد_النقاط</b>.\n"
                    f"مثال: 123456789 1000\n\n"
                    f"لم تتم إضافة أي نقطة.",
                    parse_mode='HTML'
                )
                return
            
            new_points = update_points_add(target_user, points)
            
            await context.bot.send_message(
                user_id,
                f"✅ تم إضافة {points} نقطة للمستخدم {target_user}\n"
                f"💎 رصيده الجديد: {new_points} نقطة"
            )
            
            log_action(user_id, "أدمن", "add_points", target_user, f"{points} نقطة", 'success')
            
            try:
                await context.bot.send_message(
                    target_user,
                    f"<b>تمت عملية إضافة نقاط ✅️\n"
                    f"تمت إضافة {points} نقطة من الإدارة !</b>",
                    parse_mode='HTML'
                )
            except Exception as notify_error:
                await context.bot.send_message(
                    user_id,
                    f"⚠️ تمت إضافة النقاط بنجاح بقاعدة البيانات، لكن تعذّر إرسال إشعار للمستخدم {target_user}.\n"
                    f"السبب: {notify_error}\n"
                    f"(غالبًا المستخدم لم يبدأ محادثة مع البوت بعد /start أو حظر البوت)"
                )
            
            del context.user_data['waiting_add_points']
            
        except ValueError:
            await context.bot.send_message(
                user_id,
                "❌ يرجى إدخال أرقام صحيحة!\n"
                "استخدم: addpoints <ايدي المستخدم> <عدد النقاط>"
            )
        except Exception as e:
            await context.bot.send_message(
                user_id,
                f"❌ حدث خطأ: {e}\n"
                "تأكد من الصيغة: addpoints <ايدي المستخدم> <عدد النقاط>"
            )
        return
    
    # ===== خصم نقاط (للأدمن) =====
    if context.user_data.get('waiting_remove_points', False):
        if user_id not in ADMIN_IDS:
            return
        
        try:
            parts = text.split()
            
            if len(parts) != 2:
                await context.bot.send_message(
                    user_id,
                    "❌ صيغة غير صحيحة!\n"
                    "أرسل: ايدي_المستخدم عدد_النقاط\n\n"
                    "مثال: 123456789 500"
                )
                return
            
            target_user = int(parts[0])
            points = int(parts[1])
            
            if points <= 0:
                await context.bot.send_message(user_id, "❌ عدد النقاط يجب أن يكون أكبر من 0!")
                return
            
            try:
                await context.bot.get_chat(target_user)
            except Exception:
                await context.bot.send_message(
                    user_id,
                    f"❌ الآيدي {target_user} مش حساب تليجرام حقيقي (تعذّر العثور عليه)!\n"
                    f"تأكد من الترتيب: <b>آيدي_المستخدم</b> أولاً ثم <b>عدد_النقاط</b>.\n"
                    f"مثال: 123456789 500",
                    parse_mode='HTML'
                )
                return
            
            current_points = get_user_points(target_user)
            if current_points < points:
                await context.bot.send_message(
                    user_id,
                    f"❌ رصيد المستخدم {target_user} غير كافٍ!\n"
                    f"💎 رصيده الحالي: {current_points} نقطة"
                )
                return
            
            new_points = update_points_remove(target_user, points)
            
            await context.bot.send_message(
                user_id,
                f"✅ تم خصم {points} نقطة من المستخدم {target_user}\n"
                f"💎 رصيده الجديد: {new_points} نقطة"
            )
            
            log_action(user_id, "أدمن", "remove_points", target_user, f"{points} نقطة", 'success')
            
            try:
                await context.bot.send_message(
                    target_user,
                    f"<b>⛔ تم خصم {points} نقطة من حسابك!</b>\n"
                     f"<b>💎 رصيدك الجديد: {new_points} نقطة</b>",
                    parse_mode='HTML'
                )
            except:
                pass
            
            del context.user_data['waiting_remove_points']
            
        except ValueError:
            await context.bot.send_message(
                user_id,
                "❌ يرجى إدخال أرقام صحيحة!\n"
                "أرسل: ايدي_المستخدم عدد_النقاط"
            )
        except Exception as e:
            await context.bot.send_message(
                user_id,
                f"❌ حدث خطأ: {e}\n"
                "تأكد من الصيغة: ايدي_المستخدم عدد_النقاط"
            )
        return

    # ===== حظر / فك حظر مستخدم (للأدمن) =====
    if context.user_data.get('waiting_ban_user', False):
        context.user_data['waiting_ban_user'] = False
        if user_id not in ADMIN_IDS:
            return

        if not text.isdigit():
            await message.reply_text("❌ يجب إرسال ايدي المستخدم فقط (أرقام).")
            return

        target_id = int(text)

        if target_id in ADMIN_IDS:
            await message.reply_text("❌ لا يمكن حظر أحد الأدمنية.")
            return

        currently_banned = is_user_banned(target_id)
        set_user_ban(target_id, not currently_banned)

        if currently_banned:
            log_admin_action(user_id, message.from_user.first_name or "أدمن", "unban_user", target_user=target_id)
            await message.reply_text(f"✅ تم فك الحظر عن المستخدم {target_id}")
        else:
            log_admin_action(user_id, message.from_user.first_name or "أدمن", "ban_user", target_user=target_id)
            await message.reply_text(f"✅ تم حظر المستخدم {target_id}")
            try:
                await context.bot.send_message(target_id, "🚫 تم حظرك من استخدام هذا البوت من قبل الإدارة.")
            except:
                pass
        return
    
    
    # ===== انتظار الكود =====
    if context.user_data.get('waiting_for_code', False) and context.user_data.get('code_user_id') == user_id:
        context.user_data['waiting_for_code'] = False
        code_entered = text.strip().upper()

        coupon = get_coupon_by_code(code_entered)
        if not coupon:
            await context.bot.send_message(user_id, "❌ كود غير صحيح!\nحاول مرة أخرى")
            return

        coupon_id, coupon_points, max_uses, used_count, status = coupon

        if status != 1:
            await context.bot.send_message(user_id, "❌ لقد انتهت صلاحية هذا الكود!")
            return
        if used_count >= max_uses:
            await context.bot.send_message(user_id, "❌ لقد انتهت صلاحية هذا الكود!")
            return
        if has_user_redeemed_coupon(coupon_id, user_id):
            await context.bot.send_message(user_id, "❌ لقد استخدمت هذا الكود بالفعل!")
            return

        redeem_coupon(coupon_id, user_id)
        new_points = update_points_add(user_id, coupon_points)

        await context.bot.send_message(
            user_id,
            f"✅ تم تفعيل الكود بنجاح!\n🎁 لقد حصلت على {coupon_points} نقطة\n💎 رصيدك الجديد: {new_points} نقطة"
        )
        return
    
    # ===== انتظار رابط الخدمة المجانية =====
    if context.user_data.get('awaiting_free_link', False):
        context.user_data['awaiting_free_link'] = False
        context.user_data['free_link'] = text
        context.user_data['waiting_free_quantity'] = True

        service_name = context.user_data.get('free_service_name', 'خدمة مجانية')
        min_order = context.user_data.get('free_min', 1)
        max_order = context.user_data.get('free_max', 1000000)
        await context.bot.send_message(
            user_id,
            f"💎| اسم الخدمة : {service_name}\n"
            f"💎| السعر : لكل 1000⇐ 0 نقطة\n"
            f"⚡| اقل طلب : {min_order}\n"
            f"🚀| اكبر طلب : {max_order}\n\n"
            f"🔰| ارسل العدد الذي تريدة !"
        )
        return

    # ===== انتظار العدد للخدمة المجانية =====
    if context.user_data.get('waiting_free_quantity', False):
        try:
            quantity = int(text)
            min_order = context.user_data.get('free_min', 1)
            max_order = context.user_data.get('free_max', 1000000)
            if quantity < min_order or quantity > max_order:
                await context.bot.send_message(
                    user_id,
                    f"🛑| يجب أن تكون الكمية بين {min_order} و {max_order}\n"
                    f"🔰| يرجى إرسال العدد مرة أخرى :"
                )
                return
            
            service_name = context.user_data.get('free_service_name', 'خدمة مجانية')
            link = context.user_data.get('free_link', '—')
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.row(
                InlineKeyboardButton("✅ تأكيد", callback_data="confirm_free_order"),
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel_free_order")
            )
            
            await context.bot.send_message(
                user_id,
                f"<b>✅ تم استلام العدد!</b>\n\n"
                f"<b>🛒 الخدمة: {service_name}</b>\n"
                f"<b>🔗 الرابط: {link}</b>\n"
                f"<b>📊 العدد: {quantity}</b>\n"
                f"<b>💰 السعر: 0 نقطة (مجاني)</b>\n\n"
                f"<b>هل تريد تأكيد الطلب؟</b>",
                parse_mode='HTML',
                reply_markup=markup
            )
            
            context.user_data['free_quantity'] = quantity
            
        except ValueError:
            await context.bot.send_message(user_id, "❌ يرجى إرسال عدد صحيح!")
        
        del context.user_data['waiting_free_quantity']
        return
    
    # ===== انتظار نص الإعلان =====
    if 'ad_waiting' in context.user_data:
        ad_data = context.user_data['ad_waiting']
        
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('INSERT INTO ads (user_id, ad_text, duration_hours, price, currency, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (user_id, text, ad_data['hours'], ad_data['price'], ad_data['currency'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'pending'))
        ad_id = c.lastrowid
        conn.commit()
        conn.close()
        
        await context.bot.send_message(
            user_id,
            "<b>✅ تم استلام إعلانك بنجاح!</b>\n\n"
            "<b>📢 سيتم مراجعته من قبل المشرفين وسيتم نشره بعد الموافقة.</b>",
            parse_mode='HTML'
        )
        
        price_unit = "نجمة ⭐️" if ad_data.get('currency') == 'stars' else "نقطة"

        admin_keyboard = InlineKeyboardMarkup(row_width=2)
        admin_keyboard.row(
            InlineKeyboardButton("رفض ❌️", callback_data=f"reject_ad_{ad_id}"),
            InlineKeyboardButton("موافقة ✅️", callback_data=f"approve_ad_{ad_id}")
        )
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"<b>📢 إعلان جديد ينتظر الموافقة 📢</b>\n\n"
                    f"<b>👤 المستخدم: <code>{user_id}</code></b>\n"
                    f"<b>🆔 الايدي: <code>{user_id}</code></b>\n"
                    f"<b>⏰ المدة: {ad_data['hours']} ساعة</b>\n"
                    f"<b>💰 السعر: {ad_data['price']} {price_unit}</b>\n"
                    f"<b>📝 نص الإعلان:</b>\n<code>{text}</code>\n\n"
                    f"<b>هل تريد الموافقة على هذا الإعلان؟</b>",
                    parse_mode='HTML',
                    reply_markup=admin_keyboard
                )
            except:
                pass
        
        del context.user_data['ad_waiting']
        return

# ===================== معالج الصور (للعملات الرقمية) =====================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    
    if context.user_data.get('waiting_payment_screenshot', False):
        currency = context.user_data.get('crypto_currency', 'غير معروف')
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    caption=f"<b>💰 طلب شحن جديد</b>\n\n"
                            f"<b>👤 المستخدم: <code>{user_id}</code></b>\n"
                            f"<b>💵 العملة: {currency}</b>\n"
                            f"<b>📅 التاريخ: {datetime.now().strftime('%Y/%m/%d %H:%M')}</b>\n\n"
                            f"<b>📩 يرجى مراجعة الإيداع وإضافة النقاط</b>\n"
                            f"<b>🔹 لإضافة النقاط استخدم الأمر:</b>\n"
                            f"<code>addpoints {user_id} (عدد النقاط)</code>",
                    parse_mode='HTML'
                )
            except:
                pass
        
        await context.bot.send_message(
            user_id,
            f"<b>✅ تم استلام صورتك!</b>\n\n"
             f"<b>⏳ سيتم مراجعة طلبك من قبل المشرفين</b>\n"
             f"<b>📩 سيتم إضافة النقاط بعد التأكيد</b>\n\n"
             f"<b>★ شكراً لاستخدامك متجر النخبة ♥️</b>",
            parse_mode='HTML'
        )
        
        del context.user_data['waiting_payment_screenshot']
        del context.user_data['crypto_currency']
        del context.user_data['waiting_crypto_payment']

# ===================== معالج تأكيد الدفع المسبق (إلزامي لأي دفع نجوم) =====================
async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # يجب الرد خلال 10 ثوانٍ وإلا تفشل عملية الدفع تلقائيًا من طرف تيليجرام
    await update.pre_checkout_query.answer(ok=True)

# ===================== معالج حظر/فتح البوت من قبل المستخدم =====================
async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result is None or result.chat.type != "private":
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    user = result.from_user

    if new_status == "kicked" and old_status != "kicked":
        username_display = f"@{user.username}" if user.username else "لا يوجد يوزر"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"<b>🚫 قام مستخدم بحظر البوت</b>\n\n"
                    f"<b>الاسم: {user.first_name or user.id}</b>\n"
                    f"<b>يوزرة: {username_display}</b>\n"
                    f"<b>🆔 الايدي: <code>{user.id}</code></b>",
                    parse_mode='HTML'
                )
            except:
                pass

# ===================== تشغيل البوت =====================
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر عام لإلغاء أي طلب/عملية معلّقة عالقة بجلسة المستخدم (مثل انتظار فوروارد قناة أو أي خطوة أخرى)."""
    context.user_data.clear()
    await update.message.reply_text("✅ تم إلغاء أي طلب أو خطوة معلّقة. اضغط /start للعودة للقائمة الرئيسية.")


async def post_init(application: Application):
    print("✅ البوت يعمل...")
    await create_invoice_links(application.bot)

    saved_interval = get_setting('autopost_interval_minutes', '')
    if saved_interval:
        try:
            schedule_autopost_job(application, int(saved_interval))
            print(f"✅ تم استعادة جدولة النشر التلقائي كل {saved_interval} دقيقة")
        except Exception as e:
            print(f"⚠️ تعذّرت استعادة جدولة النشر التلقائي: {e}")

def main():
    persistence = PicklePersistence(filepath="bot_persistence.pickle")
    application = ApplicationBuilder().token(TOKEN).persistence(persistence).post_init(post_init).build()
    application.add_error_handler(global_error_handler)
    print("🆕🆕🆕 نسخة الكود: تشخيص التوجيه v2 (لو ما شفت هذا السطر، فأنت تشغّل ملف غلط) 🆕🆕🆕")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(handle_buttons))
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_payment))
    application.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(handle_tgsup_channel_member_update, ChatMemberHandler.CHAT_MEMBER))

    # ملاحظة: telebot الأصلي كان يشغّل كل المعالجات المطابقة معًا (بدون توقف عند أول تطابق)،
    # لذلك نسجل معالجات النص الثلاثة في مجموعات (groups) مختلفة لمحاكاة نفس السلوك بدقة.
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO | filters.VOICE | filters.ANIMATION) & ~filters.COMMAND,
        handle_forwarded_channel_message
    ), group=-1)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_text), group=0)

    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(
        filters.Chat(username=GROUP_SUPPORT_USERNAME) & filters.TEXT & ~filters.COMMAND,
        handle_group_force_sub_messages
    ))

    print("✅ Polling شغال...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()