# DocQA: эксплуатация после выпуска 2026-09-12

Сайт https://docqa.net, API https://api.docqa.net. Рабочий выпуск —
`/opt/docqa-releases/prod-20260912-storage-ui`, schema0012. Код опубликован в
[ветке codex/production-readiness-audit](https://github.com/Hortenh1x/docqa/tree/codex/production-readiness-audit),
первый коммит реализации `463607a`. Исходники точно этой сборки доступны через
About → Source; SHA-256 архива `c25bc091c55a2fc5a86febade489f71c7e50d45a948ae37570dd13d3446df466`.

Последнее обновление V5: 50 MB оригиналов на личный аккаунт, без лимита количества
файлов; удаление освобождает место, pending/failed тоже считаются. У всех 6 публичных
наборов восстановлены 3 безопасных вопроса. Пояснение о роли показывается у каждого
набора, Google-кнопка находится под Sign in и использует официальный цветной знак.
Проверки: `evidence/storage-ui-2026-09-12/verification.json`.

## Что работает

- Регистрация/подтверждение email/вход/восстановление и вход через Google; документы доступны владельцу
  подтверждённого аккаунта. Гость использует публичные демонстрационные коллекции.
- $0.50 на суткиUTC для account/IP, расход гостя переносится при входе. Один NAT/IP
  имеет общий гостевой лимит. Сброс в00:00UTC. Общего AI cap по решению владельца нет.
- Все9778 старых документов и295856 chunks сохранены; migration0012. Существующие
  readonly корпуса опубликованы явно, прежний общий browser API key отозван.
- Оригиналы находятся в private versioned Oracle Object Storage. Локальный volume —
  проверяемый cache. Приложение не умеет удалять исторические версии в Object Storage.
- Основная БД на132.145.252.110 /10.0.0.136 (AD1), синхронная реплика на10.0.0.26 (AD2).
  Реплика доступна через private network/TLS; публичный PostgreSQL закрыт.
- Если реплика пропала, новые записи ждут её восстановления. Это выбранный режим
  сохранности. Подтверждённая пробная запись пережила выключенный primary и restart
  standby; отсутствие standby действительно блокировало подтверждение commit.
- Ночной полный backup03:00UTC занимает примерно5min с паузой DocQA writers;
  зашифрованная off-host копия03:20UTC. Старые nightly wipe отключены.
- Monitoring включён и проверяет обе машины каждые5min, сообщения идут на
  dmytro.bolibok@gmail.com. Повтор проблемы — не чаще6h, recovery — один раз.
  Проверяются готовность, контейнеры, sync/slot/WAL, диск, свежесть backups и сертификаты.
  Итоговый checkpoint — `evidence/storage-ui-2026-09-12/backup-monitoring.json`: обе машины healthy, cron активен.

Пароль: минимум8 символов, минимум одна буква и одна цифра; регистрация, подтверждение и сброс требуют совпадающий повтор. Google Client ID/Secret уже установлены из предоставленного JSON в локальный и серверный private env. Callback: `https://api.docqa.net/v1/auth/google/callback`. Кнопка и реальная страница Google проверены; завершение входа своим Google-аккаунтом проверяет владелец. Если email уже зарегистрирован, сначала войти паролем, затем **Connect Google** — автоматического объединения нет.

Получение test email в обычный Gmail inbox подтверждено владельцем. Полный live
verify/reset/private-upload acceptance не выводится из этого автоматически; его
отдельное состояние записано в verification.json/application-assessment.md.

## Где искать действующую конфигурацию

На основном VPS:

- Указатель актуального release: `/home/ubuntu/.config/docqa/current-release`.
- Сейчас: `/opt/docqa-releases/prod-20260912-storage-ui`.
- Приватные значения: `/home/ubuntu/.config/docqa/runtime.env` (600). Не публиковать.
- Project `docqa`; overlays **prod → shared-host → synchronous → source**, source последним.
- Operational scripts/logs/status: `/home/ubuntu/.local/share/docqa-ops/`.
- Полные локальные bundles: `/home/ubuntu/backups/docqa-complete/`.
- Restic private config: `/home/ubuntu/.config/docqa-backup/`.
- Monitoring config/status/logs: `/home/ubuntu/.config/docqa-monitor/`.
- Общий ingress: `/opt/ingress/Caddyfile`; он обслуживает также другие приложения.

Для штатного запуска используйте этот набор, а не старый Git checkout `/opt/docqa`:

```bash
DOCQA_CURRENT=$(cat /home/ubuntu/.config/docqa/current-release)
docker compose --env-file /home/ubuntu/.config/docqa/runtime.env -p docqa \
  -f "$DOCQA_CURRENT/docker-compose.prod.yml" \
  -f "$DOCQA_CURRENT/deploy/docker-compose.shared-host.yml" \
  -f "$DOCQA_CURRENT/deploy/docker-compose.synchronous.yml" \
  -f "$DOCQA_CURRENT/deploy/docker-compose.source.yml" ps
```

После выпуска сохраняйте и постоянный контейнер `migrate` на текущем образе. Один
`run --rm migrate` вместе с `up --no-deps` для остальных сервисов оставляет прежний
контейнер миграций: следующий backup при `compose start` может запустить его и не
возобновить writers. Обновляйте `migrate` из того же release; проверяйте его exit0.

Не выключать `synchronous_commit`, не очищать standby names, не удалять volumes.
`python -m deploy.scripts.check_durability` через migrate service выполняет **полное**
чтение оригиналов из S3: использовать после смены topology, не на каждом мониторинге.

## Восстановление

Существующие pre-release образы, configuration backups и original bundles сохранены.
Зашифрованные копии расположены в bucket `docqa-backups`, prefix `restic`. Пароль
шифрования и отдельные credentials также сохранены на рабочем компьютере владельца:

- `~/.config/docqa-ops/keys/restic.password`;
- `~/.config/docqa-ops/backup-credentials.json`;
- `~/.config/docqa-ops/work/RESTIC-RECOVERY.md`;
- разовые encrypted bundles: `~/.config/docqa-ops/backups/`.

Последняя проверенная копия: bundle `20260912T130549Z`, schema0012, restic snapshot
`6c37bf348bbdc80e3083662813e35f43534b65bb44a92d8250b9f7626cf106d0`. Восстановление
байтов из OCI заняло 36.23s: dump, все 9783 файла архива оригиналов, runtime.env,
указатель выпуска и source совпали. SQL import этого нового dump повторно не
выполнялся; прежние SQL restore и локальный migration test учитываются отдельно.
В этот раз backup автоматически возобновил сервисы; постоянный migrate container
соответствует текущему API и завершился с exit0. Оба monitors enabled/healthy.


Это приватные файлы, не Git. Их нужно сохранять независимо от основного VPS.
Восстановление проверяется в новых isolated volumes до переключения трафика.
При аварии primary сначала гарантированно закрыть старому хосту возможность писать,
проверить standby и S3, выполнить manual promotion и создать новую независимую
синхронную реплику **до** открытия записей. Runbook: `deploy/durability.md`.
Промоция production standby при проверке не выполнялась; не заявлен automatic failover.

## Оставшиеся решения владельца

1. Закончить пользовательскую приёмку Google-входа, регистрации/восстановления/своего документа.
2. Для цели нулевой стоимости выбрать [перенос общего A2](../plans/docqa-free-tier-migration-2026-09-12.md).
   Текущий основной A2 уже тарифицируется: за доступную часть сентября OCI показал
   €29.7245 использования; списание с карты/кредиты не проверены. Новая реплика A1
   выбрана в проверенных free пределах. Старый A2 и250GB диск не удалены.
3. Определить сроки хранения исторических данных/копий и применимые сведения оператора,
   подтвердить права на сторонние корпуса. Имя/email/страна опубликованы; почтовый
   адрес не предоставлен, юридическая достаточность немецких реквизитов не заявлена.

Объём DocQA Object Storage ограничен8GB, email90/сутки. Старые копии/принятые документы
автоматически не удаляются; при исчерпании места новые backups/uploads могут не пройти,
а существующие сохраняются. Request counts Object Storage — отдельный free allowance.
Цель «никаких затрат при неограниченном росте» текущая конфигурация не обещает.
