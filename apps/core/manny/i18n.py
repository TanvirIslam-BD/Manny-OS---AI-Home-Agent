"""Small multilingual primitives shared by the agent and voice pipeline."""

from __future__ import annotations

import re

LANGUAGE_TAG_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")

MAJOR_LANGUAGES: dict[str, str] = {
    "en": "English",
    "bn": "বাংলা",
    "hi": "हिन्दी",
    "zh": "中文",
    "ja": "日本語",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ar": "العربية",
    "pt": "Português",
    "ru": "Русский",
    "ko": "한국어",
}

FINANCE_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "reminder_created": "Okay, I'll remind you to {title} at {time}.",
        "reminder_needs_time": "When should I remind you to {title}?",
        "budget_status": "You've spent {spent} of {budget}. You have {remaining} remaining.",
        "category_spending": "{category} is your highest category at {amount}.",
        "recurring_payments": "Your next payment is {merchant} at {amount}, due {due_date}.",
        "no_recurring": "You have no upcoming recurring payments in this period.",
        "other_currency_excluded": "Excludes {count} categories recorded in {currencies}.",
    },
    "bn": {
        "reminder_created": "ঠিক আছে, আমি আপনাকে {time}-এ {title} মনে করিয়ে দেব।",
        "reminder_needs_time": "{title} কখন মনে করিয়ে দেব?",
        "budget_status": "আপনি {budget}-এর মধ্যে {spent} খরচ করেছেন। আপনার {remaining} বাকি আছে।",
        "category_spending": "আপনার সর্বোচ্চ খরচের বিভাগ {category}, মোট {amount}।",
        "recurring_payments": "আপনার পরবর্তী পেমেন্ট {merchant}-এ {amount}, পরিশোধের তারিখ {due_date}।",
        "no_recurring": "এই সময়ে আপনার কোনো আসন্ন নিয়মিত পেমেন্ট নেই।",
        "other_currency_excluded": "{currencies}-এ রেকর্ড করা {count}টি বিভাগ এতে অন্তর্ভুক্ত নয়।",
    },
    "hi": {
        "reminder_created": "ठीक है, मैं आपको {time} पर {title} की याद दिलाऊँगा।",
        "reminder_needs_time": "{title} की याद कब दिलाऊँ?",
        "budget_status": "आपने {budget} में से {spent} खर्च किए हैं। आपके पास {remaining} शेष हैं।",
        "category_spending": "आपकी सबसे बड़ी खर्च श्रेणी {category} है, जिसमें {amount} खर्च हुए।",
        "recurring_payments": "आपका अगला भुगतान {merchant} को {amount} है, जिसकी तारीख {due_date} है।",
        "no_recurring": "इस अवधि में आपका कोई आगामी नियमित भुगतान नहीं है।",
        "other_currency_excluded": "{currencies} में दर्ज {count} श्रेणियाँ इसमें शामिल नहीं हैं।",
    },
    "zh": {
        "reminder_created": "好的，我会在 {time} 提醒你{title}。",
        "reminder_needs_time": "你希望我什么时候提醒你{title}？",
        "budget_status": "您的预算为 {budget}，已支出 {spent}，还剩 {remaining}。",
        "category_spending": "您支出最高的类别是 {category}，金额为 {amount}。",
        "recurring_payments": "下一笔付款是向 {merchant} 支付 {amount}，到期日为 {due_date}。",
        "no_recurring": "此期间没有即将发生的定期付款。",
        "other_currency_excluded": "不包含以 {currencies} 记录的 {count} 个类别。",
    },
    "ja": {
        "reminder_created": "わかりました。{time} に{title}をお知らせします。",
        "reminder_needs_time": "{title}はいつお知らせしましょうか？",
        "budget_status": "予算 {budget} のうち {spent} を使用し、残りは {remaining} です。",
        "category_spending": "最も支出が多いカテゴリーは {category} で、{amount} です。",
        "recurring_payments": "次の支払いは {merchant} への {amount} で、期限は {due_date} です。",
        "no_recurring": "この期間に予定されている定期支払いはありません。",
        "other_currency_excluded": (
            "{currencies} で記録された {count} 件のカテゴリーは含まれていません。"
        ),
    },
    "es": {
        "reminder_created": "De acuerdo, te recordaré {title} a las {time}.",
        "reminder_needs_time": "¿Cuándo te recuerdo {title}?",
        "budget_status": "Has gastado {spent} de {budget}. Te quedan {remaining}.",
        "category_spending": "Tu categoría con mayor gasto es {category}, con {amount}.",
        "recurring_payments": "Tu próximo pago es a {merchant} por {amount}, con fecha {due_date}.",
        "no_recurring": "No tienes pagos recurrentes próximos en este período.",
        "other_currency_excluded": "No incluye {count} categorías registradas en {currencies}.",
    },
    "fr": {
        "reminder_created": "D'accord, je vous rappellerai {title} à {time}.",
        "reminder_needs_time": "Quand dois-je vous rappeler {title} ?",
        "budget_status": "Vous avez dépensé {spent} sur {budget}. Il vous reste {remaining}.",
        "category_spending": "Votre catégorie principale est {category}, avec {amount}.",
        "recurring_payments": "Votre prochain paiement est {merchant}, {amount}, dû le {due_date}.",
        "no_recurring": "Vous n'avez aucun paiement récurrent à venir sur cette période.",
        "other_currency_excluded": "Hors {count} catégories enregistrées en {currencies}.",
    },
    "de": {
        "reminder_created": "Alles klar, ich erinnere Sie um {time} an {title}.",
        "reminder_needs_time": "Wann soll ich Sie an {title} erinnern?",
        "budget_status": "Sie haben {spent} von {budget} ausgegeben. {remaining} sind noch übrig.",
        "category_spending": "Ihre höchste Ausgabenkategorie ist {category} mit {amount}.",
        "recurring_payments": (
            "Ihre nächste Zahlung ist {merchant} über {amount}, fällig am {due_date}."
        ),
        "no_recurring": "In diesem Zeitraum stehen keine regelmäßigen Zahlungen an.",
        "other_currency_excluded": "Ohne {count} Kategorien, die in {currencies} erfasst sind.",
    },
    "ar": {
        "reminder_created": "حسنًا، سأذكّرك بـ {title} في {time}.",
        "reminder_needs_time": "متى أذكّرك بـ {title}؟",
        "budget_status": "أنفقت {spent} من أصل {budget}. المتبقي لديك {remaining}.",
        "category_spending": "أعلى فئة إنفاق لديك هي {category} بمبلغ {amount}.",
        "recurring_payments": "دفعتك التالية إلى {merchant} بمبلغ {amount}، وتستحق في {due_date}.",
        "no_recurring": "ليس لديك دفعات دورية قادمة في هذه الفترة.",
        "other_currency_excluded": "لا يشمل {count} فئة مسجلة بعملة {currencies}.",
    },
    "pt": {
        "reminder_created": "Combinado, vou lembrar você de {title} às {time}.",
        "reminder_needs_time": "Quando devo lembrar você de {title}?",
        "budget_status": "Você gastou {spent} de {budget}. Restam {remaining}.",
        "category_spending": "Sua maior categoria de gastos é {category}, com {amount}.",
        "recurring_payments": "Seu próximo pagamento é para {merchant}, {amount}, em {due_date}.",
        "no_recurring": "Você não tem pagamentos recorrentes próximos neste período.",
        "other_currency_excluded": "Não inclui {count} categorias registradas em {currencies}.",
    },
    "ru": {
        "reminder_created": "Хорошо, напомню вам {title} в {time}.",
        "reminder_needs_time": "Когда напомнить вам {title}?",
        "budget_status": "Вы потратили {spent} из {budget}. Осталось {remaining}.",
        "category_spending": "Самая крупная категория расходов — {category}: {amount}.",
        "recurring_payments": "Следующий платеж: {merchant}, {amount}, дата {due_date}.",
        "no_recurring": "В этом периоде нет предстоящих регулярных платежей.",
        "other_currency_excluded": "Не включает {count} категорий, учтённых в {currencies}.",
    },
    "ko": {
        "reminder_created": "알겠습니다. {time}에 {title}을(를) 알려드릴게요.",
        "reminder_needs_time": "{title}을(를) 언제 알려드릴까요?",
        "budget_status": "예산 {budget} 중 {spent}을 사용했고, {remaining}이 남았습니다.",
        "category_spending": "가장 큰 지출 카테고리는 {category}이며, 금액은 {amount}입니다.",
        "recurring_payments": "다음 결제는 {merchant}에 {amount}, 결제일은 {due_date}입니다.",
        "no_recurring": "이 기간에는 예정된 정기 결제가 없습니다.",
        "other_currency_excluded": "{currencies}(으)로 기록된 {count}개 카테고리는 제외되었습니다.",
    },
}


def normalize_language_tag(value: str | None, *, default: str = "en") -> str:
    """Normalize a bounded BCP-47-style tag without accepting control characters."""
    if value is None:
        return default
    candidate = value.strip().replace("_", "-")
    if candidate.casefold() == "auto" or not LANGUAGE_TAG_PATTERN.fullmatch(candidate):
        return default
    parts = candidate.split("-")
    normalized = [parts[0].lower()]
    normalized.extend(part.upper() if len(part) == 2 else part for part in parts[1:])
    return "-".join(normalized)


def base_language(value: str | None) -> str:
    return normalize_language_tag(value).split("-", 1)[0]


def detect_text_language(text: str, hint: str | None = None) -> str:
    """Resolve explicit hints first, then recognize common Unicode scripts locally."""
    if hint and hint.casefold() != "auto":
        return normalize_language_tag(hint)
    for character in text:
        codepoint = ord(character)
        if 0x0980 <= codepoint <= 0x09FF:
            return "bn"
        if 0x0900 <= codepoint <= 0x097F:
            return "hi"
        if 0x3040 <= codepoint <= 0x30FF:
            return "ja"
        if 0xAC00 <= codepoint <= 0xD7AF:
            return "ko"
        if 0x4E00 <= codepoint <= 0x9FFF:
            return "zh"
        if 0x0600 <= codepoint <= 0x06FF:
            return "ar"
        if 0x0400 <= codepoint <= 0x04FF:
            return "ru"
    return "en"


def finance_template(language: str, key: str) -> str:
    catalog = FINANCE_TEMPLATES.get(base_language(language), FINANCE_TEMPLATES["en"])
    return catalog.get(key, FINANCE_TEMPLATES["en"][key])
