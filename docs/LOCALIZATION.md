# Dashboard localization

The browser dashboard uses a small, dependency-free localization layer. The display firmware, clock schedule, sensor readings and hardware settings are not translated or modified by this feature.

## Layout

- `web/config/languages.json` — supported languages, default/fallback language, locale file paths and browser storage key.
- `web/locales/pl.json` — Polish dictionary.
- `web/locales/en.json` — English dictionary.
- `web/i18n.js` — browser language selector, dictionary loading, persistence and DOM translation.
- `zegar_app/web_control.py` — serves an allowlisted set of localization JSON files from the existing HTTP API under `/i18n/`.

The language selector is inserted into the dashboard header. The selected language is saved in browser local storage, so it remains selected after refresh. A clean browser profile uses the configured default language. The physical Malina installation keeps Polish as its default.

## Add another language

1. Copy `web/locales/en.json` to a new file, for example `web/locales/de.json`.
2. Translate every key. Keep the key names and interpolation placeholders such as `{version}`, `{count}` and `{error}` unchanged.
3. Add an entry to `languages` in `web/config/languages.json`, including its code, display name, native name and locale file path.
4. Run `python3 scripts/validate-locales.py`.
5. Add the new locale code to the allowlist in `zegar_app/web_control.py` before deploying it to a Raspberry Pi. This prevents arbitrary filesystem paths from being exposed by the API.

Set `defaultLanguage` to change the language used by new browser profiles. Keep `fallbackLanguage` as a complete dictionary; missing translations are treated as validation errors.

## Validation

The normal project check runs the locale validator as part of `./scripts/check.sh`. The validator checks JSON syntax, configured language codes, matching dictionary keys, matching interpolation placeholders and literal translation-key references in the dashboard scripts.

## Scope

The dashboard language is a browser preference and is independent of the language or font used by the LED matrix. Choosing English in a browser does not change the physical clock display or its Polish default configuration.
