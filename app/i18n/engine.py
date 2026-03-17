"""RetailIQ i18n Engine."""


def get_translated_string(key: str, locale: str = "en", module: str | None = None) -> str:
    """Fetch a translated string by key. Returns key if not found."""
    try:
        from app import db
        from app.models.expansion_models import Translation, TranslationKey

        q = (
            db.session.query(Translation.value)
            .join(TranslationKey, TranslationKey.id == Translation.key_id)
            .filter(TranslationKey.key == key, Translation.locale == locale, Translation.is_approved.is_(True))
        )
        if module:
            q = q.filter(TranslationKey.module == module)
        row = q.first()
        return row[0] if row else key
    except Exception:
        return key
