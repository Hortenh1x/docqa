# W-09 — данные, очистка и лицензии

## Дополнение production на 2026-09-12

Ниже сохранён исторический снимок 2026-09-10; открытые инфраструктурные вопросы в нём
не являются текущими блокерами. [Актуальная оценка](../application-assessment.md) и
[операторская передача](operator-handoff-2026-09-12.md) описывают фактический deployment.

- Имя Dmytro Bolibok, email dmytro.bolibok@gmail.com и Germany опубликованы на About.
  Владелец выбрал AGPL-3.0-only; LICENSE/NOTICE и соответствующий точной сборке source
  archive доступны через About. Права на все сторонние корпуса остаются отдельным вопросом.
- Оригиналы9778 документов сохранены и SHA-verified в private versioned Oracle bucket;
  primaryAD1 и sync standbyAD2 используют private TLS. Nightly wipe отключён, прежние
  документы и backups не удаляются автоматически. Off-host restic encrypted backup и
  восстановление байтов проверены; реальные full SQL restore/drill различены в evidence.
- SMTP/SPF/DKIM настроены, владелец подтвердил обычный Gmail inbox. Google включён из
  предоставленного private client JSON; доступны лишь scopes openid/email. Google получает
  запрос входа по выбору пользователя; DocQA сохраняет issuer/subject и проверенный email,
  одноразовое browser-bound state. Google bearer/refresh tokens не сохраняются.
- Новый password contract по прямому выбору владельца: минимум8 code points, буква и
  decimal digit, совпадающее подтверждение. Внешних password breach запросов больше нет.
- Production использует OpenAI embeddings и DeepSeek answers; сведения о передаваемых
  данных доступны в About. Paid tests выполнялись только с synthetic/evaluation данными.
  Договоры, регионы обработки и сроки хранения не считаются одобренными одним техническим тестом.

## Исторический снимок 2026-09-10

Состояние локальной реализации на 2026-09-10. Это инженерный реестр. Владелец отвечает за сервис и разрешил персональные/конфиденциальные документы с доступом только owner; публичный контакт, рынки и условия внешней обработки ещё не предоставлены. Публичные юридические тексты с вымышленными реквизитами не добавлялись.

| Данные / система | Реализованное поведение | Что ещё требует подтверждения |
|---|---|---|
| Оригиналы, documents, chunks | Upload только verified account; personal tenant owner-only; нет nightly wipe/TTL. Durable local fsync или versioned S3+checksum; явное удаление после DB commit сохраняет общие ссылки | Реальный private/encrypted S3, независимость, bucket/version retention и миграция существующих originals; старый cron убрать при выпуске |
| Вопросы/ответы и citations | wipe удаляет queries выбранной коллекции; FK очищает citations. data_version не даёт запросу/генерации подсказок восстановить очищенные строки после завершения | Срок истории запросов к другим коллекциям и последствия обычного удаления документа для прежних ответов |
| Redis replay cache | wipe удаляет все idem-ключи этого tenant (у legacy entries нет collection metadata); compare-and-set не позволяет завершившемуся старому запросу вернуть удалённый ключ. Ошибка purge означает ошибку CLI, требующую retry/alert | Production Redis persistence/копии, подтверждение выполнения purge и исторические остатки. TTL обычного replay — настроенный IDEMPOTENCY_TTL_S (по умолчанию 24 часа) |
| Browser | В account mode cookies Secure/HttpOnly, proof tokens и passwords только в памяти формы; private answers/cache/readers/drafts удаляются при identity change/expiry, fetch/XHR/SSE отменяются across tabs. Ссылка verify/reset очищается из URL | Уже скачанный оригинал/скриншот нельзя дистанционно отозвать. Legacy API-key mode отдельно сохраняет прежние UTC expiry правила |
| HTTP cache | `/v1/` получает private, no-store; UI security headers проверены на локальном контейнере | Заголовки/кэш внешнего ingress и уже опубликованной версии |
| Rate/auth metadata | Email+Argon2id hash, hashed opaque sessions/action tokens, durable auth-attempt counters. HMAC IP (/64 IPv6), reservations и account/IP allocations в PostgreSQL, $0.50/day UTC; guest spend импортируется при login | Сроки старых auth/ledger записей, необходимость и основание хранения, доступ к данным. Глобальный monetary cap исключён владельцем |
| Логи | SQL engines hide_parameters; неожиданные API/DB/worker/provider ошибки сохраняют тип+correlation, без сырых exception payloads; suggestions не логируют вопросы. Docker rotation по объёму | Time-based retention, доступ, старые логи/внешние агенты и реальная доставка alerts |
| Backups | Consistent PostgreSQL+originals snapshot, manifest hashes, fsync до publication, isolated restore through0011 включает accounts/sessions/tokens/queries/spend. Same-host synchronous failover rehearsal прошёл | Зашифрованная off-host копия, реальные independent hosts, retention, provider bucket restore и повторение на фактическом deployment. Доступность допускается жертвовать ради подтверждённых записей |
| Embedding provider | Получает тексты chunks и поисковые вопросы | Фактический поставщик, регион, условия/DPA, допустимость реальных данных |
| Cohere rerank (только при RERANK_PROVIDER=cohere) | Получает поисковый вопрос и до4000 символов каждого отобранного chunk после role filtering | Наличие активного Cohere, регион/условия/DPA/retention и бюджет подтверждает оператор; при none/local этот внешний поток отсутствует |
| LLM provider | Получает вопрос и разрешённые excerpts. Публичные suggested questions получают только открытые excerpts; закрытая подсказка строится из видимого filename | Фактический поставщик/модель/регион/retention, договоры и бюджет. Реальные платные eval не запускались |

Политика nightly wipe на сервере и договоры поставщиков не подтверждены локальными тестами. Данные общего demo tenant не изолированы между посетителями; оператор должен решить, какие реальные данные допустимы и как сообщать об этом посетителю. Вопрос владельцу задан, ответа пока нет.

## Лицензии и происхождение материалов

| Компонент | Установленный факт | Открытое действие |
|---|---|---|
| Python/npm | Декларации лицензий установленных пакетов и lock собраны в [inventory](evidence/implementation-v1/license-inventory.json); dev/runtime различаются | Проверить обязательные notices именно распространяемого артефакта и выбранную лицензию самого приложения; наличие metadata не означает выполненную лицензионную проверку |
| PyMuPDF / MuPDF | Официальная документация описывает выбор [AGPL или коммерческой лицензии](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) | Владелец подтверждает применимый вариант и выполнение его условий. Коммерческая лицензия/публичный corresponding source не подтверждены; нарушение не объявляется установленным |
| Fraunces, Inter, JetBrains Mono | Официальные Google Fonts OFL notices сохранены в ui/public/licenses, включены в Docker image и доступны по /licenses/*.txt | При замене шрифтов/их версии повторить сверку. Sources и hashes записаны в inventory |
| Синтетические корпуса | Генератор scripts/corpus_v2/generate.py описывает fictional company; в репозитории есть исходные документы и manifest | Авторство и право публикации подтверждает владелец. Synthetic intent не является доказательством всех прав |
| Внешние корпуса | docs.md и corpus scripts описывают GitLab Handbook, GovReport, CUAD и FinanceBench. Названия лицензий в docs являются сведениями проекта, а не завершённой проверкой текущих upstream условий и каждого включённого документа | Нужны источник/version, scope разрешения на тексты/аннотации, attribution/notice и право повторной публикации каждого набора. Не переносить лицензию dataset metadata автоматически на все исходные документы |
| Сам DocQA | В проверенном корне не найден отдельный LICENSE | Владелец определяет лицензию/условия использования; агент не назначает её сам |

Проверенные первичные источники шрифтов: [Fraunces](https://raw.githubusercontent.com/google/fonts/main/ofl/fraunces/OFL.txt), [Inter](https://raw.githubusercontent.com/google/fonts/main/ofl/inter/OFL.txt), [JetBrains Mono](https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/OFL.txt). Все три предоставляют SIL OFL 1.1; полные notices сохранены вместе со шрифтами.
