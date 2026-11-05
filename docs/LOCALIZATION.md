# Dashboard localization

The browser dashboard uses a small, dependency-free localization layer. The display firmware, clock schedule, sensor readings and hardware settings are not translated or modified by this feature.

## Layout

- `web/config/languages.json` — supported languages, default/fallback language, locale file paths and browser storage key.
- `web/locales/pl.json` — Polish dictionary.
- `web/locales/en.json` — English dictionary.
- `web/i18n.js` and the embedded runtime in `web/index.html` — browser language selector, dictionary loading, persistence, dynamic DOM translation and configuration-panel refresh.
- `scripts/validate-locales.py` — checks all 89 settings in `zegar.conf.example` have labels in every configured language, in addition to dictionary and placeholder consistency.
- `zegar_app/web_control.py` — serves an allowlisted set of localization JSON files from the existing HTTP API under `/i18n/`.

The language selector is inserted into the dashboard header. The selected language is saved in browser local storage, so it remains selected after refresh. A clean browser profile uses the configured default language. The physical Malina installation keeps Polish as its default. Dashboard text added dynamically (including status messages, precipitation tests, configuration groups, all configuration fields and the matrix-position editor) follows the selected language without reloading the clock service. Search also uses translated setting labels.

## Add another language

1. Copy `web/locales/en.json` to a new file, for example `web/locales/de.json`.
2. Translate every key. Keep the key names and interpolation placeholders such as `{version}`, `{count}` and `{error}` unchanged.
3. Add an entry to `languages` in `web/config/languages.json`, including its code, display name, native name and locale file path.
4. Run `python3 scripts/validate-locales.py`.
5. Add the new locale code to the allowlist in `zegar_app/web_control.py` before deploying it to a Raspberry Pi. This prevents arbitrary filesystem paths from being exposed by the API.

Set `defaultLanguage` to change the language used by new browser profiles. Keep `fallbackLanguage` as a complete dictionary; missing translations are treated as validation errors.

## Validation

The normal project check runs the locale validator as part of `./scripts/check.sh`. The validator checks JSON syntax, configured language codes, matching dictionary keys, matching interpolation placeholders, literal translation-key references, required dashboard UI keys and a translated label for every option in `zegar.conf.example`.

## Scope

The dashboard language is a browser preference and is independent of the language or font used by the LED matrix. Choosing English in a browser does not change the physical clock display or its Polish default configuration.
