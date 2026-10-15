# Design: Проверяемая перепаковка данных

## Context

`repack` — операция сохранения данных и их формата. Stream путь сохраняет исходные
байты распакованного payload; native путь сохраняет значения, порядок, типы и
значимые metadata, меняя сжатие и разрешённые параметры физического layout.

Нынешняя реализация смешивает выбор стратегии, запись и публикацию, а ORC/Avro
используют conversion path с inference. Подробные подтверждения: [research.md](research.md).

Отдельной действующей repack spec нет; добавляется `data-repacking`. Shared writer
и JSON output пересекаются с существующими changes, поэтому следует расширять
общий механизм вместо третьего независимого слоя записи.

## Goals / Non-Goals

Goals:

- Успех означает verified preservation и завершённую publication либо явно
  сообщённый no-op/dry-run; partial output никогда не публикуется.
- Потоковая работа с большими данными; bounded transfer/batch memory и видимые
  ограничения encoder/decoder, scratch и времени.
- Более качественное сжатие выбирается измерением и не ухудшает baseline вслепую.
- CLI/API сохраняют существующие аргументы, default max и format-preserving назначение.

Non-goals первой поставки:

- Удалённые URI, stdin/stdout для binary repack, recursive archive optimization,
  lossy transforms, изменение порядка строк, auto CSV → Parquet.
- Перенос всего filerepack или обязательные новые native tools.
- Обещание crash durability/сохранения ownership, ACL, ADS, которые не обеспечивает
  обычный `os.replace()`. Атомарная видимость и fsync durability — разные контракты.

## Decisions

### 1. Общий lifecycle с отдельным preservation contract

```text
detect + resolve options + inspect source/destination
  → stage candidate beside destination
  → write + close all resources
  → independently verify structure and preservation
  → recheck source/candidate/destination generation
  → evaluate growth and savings policy
  → restore metadata + atomic publish, or discard candidate
  → return typed outcome
```

Выделить небольшой общий atomic-file target из `common/writer.py`, пригодный для
RecordSink, DuckDB COPY и repack native/byte writers. Контракт принимает writer
callback/target, поддерживает deferred commit и abort. Record output продолжает
использовать `RecordSink`/`emit_records`; byte/native repack использует общий target.

Нельзя направлять exact native repack через нынешний `RecordSink.write_batch()`:
там `normalize_for_json()` и dict records — это путь преобразования, не гарантия
исходных logical types/metadata. Encoder пишет только в stage, final target
публикует общий механизм. Не создавать parallel handwritten output helpers.

Модели — dataclasses: `RepackOptions`, `RepackPlan`, `RepackResult`. Вначале достаточно
функций для четырёх adapters; registry/protocol вводить по фактической необходимости.
Публичный `Repacker.repack(fromfile, tofile=None, options=None)` сохраняет текущий
dict return с добавленными полями; typed result сериализуется на этой границе.

### 2. Paths, metadata и concurrent modification

- Явные одинаковые пути и relative/absolute aliases определять по `samefile` для
  существующих файлов и canonical path fallback; всегда stage, даже для distinct OUTPUT.
- In-place symlink и source с несколькими hard links отвергать до работы: replacement
  меняет смысл ссылок. Distinct output из такого источника допустим с source guards.
- Destination symlink/non-regular file отвергать; существующий обычный OUTPUT
  сохраняет совместимое поведение intentional replacement, но защищается snapshot.
- Snapshot: stat identity/generation и checksum; проверять source и existing destination
  повторно рядом с commit. Сохранять mode/mtime и поддерживаемые xattrs;
  невозможность выполнить заявленный metadata contract запрещает публикацию.
- Bind verification к конкретному кандидату; проверка generation/digest не должна
  разрешать публикацию изменённого после verification файла.
- Закрывать ресурсы через ExitStack/context managers; encoder close/finalize errors
  являются ошибкой операции; сохранять исходную причину при cleanup failures.
- Проверки уменьшают риск concurrent modification, но не обещают невозможный
  portable filesystem compare-and-swap против произвольного writer в последней
  инструкции перед rename. Эту границу явно документировать.

### 3. Выбор стратегии и возможностей до записи

- Разделить compression envelope и data format; codecs определять независимо от
  успешности datatype detection. Magic/суффикс сверять; неоднозначность — ошибка,
  не silent raw fallback после любого исключения.
- Для streams остаётся iterabledata registry. Capability table отражает read/write,
  реальные диапазоны level, profile, threads и metadata support каждого backend.
- Aliases `gzip/gz`, `zstandard/zstd/zst`, `brotli/br` разрешать по контексту:
  native Avro `zstandard` не то же имя, что outer `zst`.
- Начальный контракт ZIP/7z: explicit unsupported до stage, с указанием отдельной
  archive задачи. Проверить magic, чтобы raw wrapping архивов не выглядело их repack.
- Native Parquet → `.parquet.gz` первоначально отвергать с объяснением: требуется
  отдельный outer-wrapper mode. Сжатый `.parquet.gz` как вход можно перепаковать
  только как stream, сохранив точные байты внутреннего Parquet.
- Смена внешнего codec требует distinct OUTPUT с согласованным суффиксом;
  plain CSV с `--compression` тоже требует подходящий OUTPUT. Native codec changes
  внутри `.parquet/.orc/.avro` не требуют изменения имени.
- Формат OUTPUT не может менять data format; для этого есть `convert`.
- Unsupported level больше не игнорируется: применить проверенный capability
  или выдать ValidationError до записи. Missing dependency — DependencyError с
  реальным install hint, codec/data errors — UndatumError, системные — exit 3.

### 4. Проверка форматов

Streams:

- SHA-256 и длина распакованных bytes источника, вычисляемые во время передачи;
  независимое повторное decode candidate, проверка полного EOF/trailer/checksum.
- Не парсить CSV/JSONL: сохранить BOM, CRLF, quoting, пустые строки и произвольные bytes.
- Конкатенированные members/frames, empty payload и truncated streams — отдельные тесты.
- Стабильный gzip header: не включать имя tempfile; контролировать mtime и сохранять
  заявленные значимые header fields либо явно отказаться от unsupported headers.

Parquet:

- Создавать writer по исходной Arrow schema (из serialized metadata, с fallback
  на `pf.schema_arrow`) до batch iteration: zero-row file остаётся
  валидным с той же schema/metadata; `ParquetFile` закрывать context manager-ом.
- Original version, field IDs, nullability, decimal precision/scale, timestamps/timezone,
  nested/list conventions, schema/file metadata проверять после записи.
- Сравнивать physical и logical schemas; INT96/integer decimals/sorting declarations,
  encryption/external chunks сохранять проверенным путём или сообщать unsupported.
- Batch-aligned equality для разных group sizes; порядок/число строк; для floats
  сохранять signed zero/NaN payload по bit patterns, включая nested values.
- Считать допустимыми документированные изменения compression/statistics/layout;
  не объявлять byte equality всего Parquet, который закономерно переписывается.
- Работать по row groups с controlled pre_buffer/use_threads; batch count не равен
  hard byte cap. Настраивать row-group size отдельно от transfer batch size;
  не собирать неограниченный исходный row group в RAM для сохранения layout.

ORC:

- Заменить generic convert на typed pyorc reader/writer с original schema и user
  metadata; оценить Arrow stripe путь как альтернативу по fidelity fixtures.
- Проверять typed rows/schema/metadata независимо. Decimal/timestamps/nested nulls
  и empty file обязательны. Если backend не сохраняет variant/metadata — отказ.
- Ошибка final batch должна доходить до caller; частично записанный файл discard.

Avro:

- Предпочтительный путь — recompression исходных encoded OCF blocks: сохранить
  exact `avro.schema` bytes, custom metadata, record counts/order, sync marker и
  union branch encodings; менять только `avro.codec` и compression envelope blocks.
- Поддержать используемые текущей командой codecs только с проверенным reader/writer;
  проверять block lengths/sync/EOF и typed native read-back.
- Проверить, можно ли обеспечить этот контракт через iterabledata; иначе небольшой
  dedicated adapter. Избегать schema inference и record coercion через JSON/string.

### 5. Размер, dry-run и результат

Optimization = то же representation: raw/native data format и тот же outer codec.
Default `allow_grow=False`, `min_savings=0`; кандидат принимается только при строго
меньшем размере и выполненном threshold. `--min-savings` измеряется в процентах
от physical source size; `(input_size-candidate_size)/input_size*100`.
Нулевой physical source size имеет savings percent null, не деление на ноль.

- In-place rejected candidate: исходник остаётся; status `unchanged`, reason `no_benefit`.
- Distinct OUTPUT с тем же representation: при no-benefit атомарно скопировать
  оригинал в запрошенный OUTPUT. Это сохраняет существование ожидаемого pipeline
  artifact; report показывает candidate size отдельно, `published=true`, `changed=false`.
- Explicit outer-codec migration или raw wrapping: принять verified result даже
  если размер вырос; report честно показывает отрицательную экономию. Нельзя копировать
  gzip source под `.zst`. Явный `min_savings` может отклонить migration без публикации
  с outcome `skipped` и причиной `below_min_savings`.
- `--allow-grow` разрешает рост только размера; preservation остаётся обязательной.
- `--dry-run`: действительно encode+verify candidate и посчитать размеры, но не
  публиковать/не создавать backup; после cleanup INPUT и prior OUTPUT неизменны.
  Это measured dry run, не дешёвая статистическая оценка.

CLI summary показывает original/candidate/final sizes, saved bytes/percent, status,
codec/profile/effective level, elapsed time, verification и publication decision.
`--json` — ровно один `undatum.repack/1` через `common.results.emit()`; progress/logs
в stderr, без ANSI в non-TTY. Текущие result keys сохраняются, но добавить
`input_size`, `candidate_size`, `output_size`, `decoded_bytes`, `status`, `reason_code`,
`published`, `changed`, `savings_bytes`, `savings_percent`, `elapsed_seconds`,
`effective_settings`, `verification`; неоднозначный `bytes_read` не использовать
как physical input size.

Обычные replaced/unchanged/dry-run outcomes — exit 0. Ошибки по действующим
UndatumError codes (1/2/3/4/130). Requested unsupported operation — exit 1 либо
missing dependency exit 2; optional unsuccessful extra encoder trial не проваливает
валидный baseline. CLI `--output/-o` можно добавить как alias к существующему
позиционному OUTPUT с отказом от противоречивых значений.

### 6. Profiles, budgets и последующее улучшение compression

- Переиспользовать `fast|balanced|max` iterabledata; default max оставить. Explicit
  `--level` переопределяет профиль; реально разрешённые codec settings попадают в report.
- Native profiles имеют собственные параметры: ZSTD 19 остаётся standard max;
  22/XZ extreme/strong gzip — отдельный поздний opt-in high-effort режим после benchmarks.
- Soft counters для decoded bytes, scratch, elapsed time и cancellation; пользовательские
  лимиты валидировать до работы. Длинные операции проверяют budget во время loops.
- Для hard native RSS/timeout limits нужен отдельный worker/monitor: один 1 MiB
  Python buffer не ограничивает zstd dictionary, XZ decoder или Parquet column chunk.
  Не обещать hard memory cap там, где есть только проверка batch.nbytes.
- Сначала benchmark, затем threads в zstd/native libraries и optional pigz с
  timeout/cancellation/fallback. External tool discovery ограничить нужными codecs.
- High-effort режим имеет verified baseline и ограниченный набор trials, выбирает
  минимальный валидный output. Неудача дополнительного encoder-а сохраняет baseline;
  изменение source/прерывание операции всегда запрещает публикацию.
- Arrow IPC/Feather — follow-up capability после stable native paths; сохранить
  framing/schema/batch metadata. HDF5/SQLite/ZIP — самостоятельные предложения.

## Migration Plan / Delivery Order

| Поставка | Содержание | Gate для перехода дальше |
|---|---|---|
| PR 1 / P0 | Staging всех OUTPUT, same-path protection, empty Parquet; блокировка небезопасного ORC/Avro path до dedicated adapters; fault tests | Ни одно воспроизведение потери данных не публикуется как успех; failures сохраняют source/destination |
| PR 2 / P0–P1 | Native ORC/Avro, Parquet fidelity verifier, file/source guards/metadata, capability preflight | Typed schemas/values/metadata/order сохраняются или input безопасно отвергается |
| PR 3 / P1 | No-growth/min-savings, dry-run, results/JSON, profiles, ясные ошибки и docs | Outcomes однозначны; pipeline OUTPUT существует при same-representation no-benefit; JSON schema/tests проходят |
| PR 4 / P2 | Resource limits, benchmark harness, tuning batch/row-group/threads | Поведение limits измерено; defaults не ухудшают representative size/RSS/read-back без обоснования |
| Follow-up / P3 | Opt-in verified encoder trials и Arrow/Feather | Каждая новая возможность имеет отдельные fidelity fixtures и измеренный выигрыш |

PR 1 при необходимости временно заменяет ORC/Avro advertised success на безопасный
отказ с explanation; поддержку возвращает PR 2. Это предпочтительнее оставлять
известный data-loss путь активным в промежуточной поставке.

## Validation Strategy

1. Regression suite: все сценарии [research.md](research.md), в том числе explicit
   same path, empty files и сохранность существующего OUTPUT после encoder error.
2. Fault injection: write/finalize/verification/metadata/replace exceptions,
   mutation source/destination/candidate; Ctrl-C; исключение второй cleanup операции.
3. Fidelity: Parquet/ORC/Avro rich types, nulls, dates/tz/decimals, nested schemas,
   NaN/signed-zero, custom/binary metadata; independent reader where available.
4. CLI/API: старые вызовы, positional/option output, profiles/level precedence,
   rejected combinations, JSON stdout/error stderr/exit codes, non-TTY progress.
5. Corpus: CSV/JSONL text/numeric/high-cardinality/random data, tiny and empty files,
   concatenated streams; Parquet/ORC/Avro various schemas, codecs and layouts;
   1 MiB/100 MiB/1 GiB tiers where feasible. Baseline undatum and filerepack run with
   comparable codecs/settings and fidelity requirements; cold and warm runs separated.
6. Metrics: physical size, savings vs original, encode and verify time separately,
   peak process-tree RSS, scratch high water, decode throughput, DuckDB scan time
   for Parquet. Verification costs включать в user-visible total.
7. Gate: correctness first; no accepted same-representation result larger than
   original unless allow-grow. Performance budgets калибровать измерениями,
   не обещать произвольные проценты ускорения или сжатия заранее.
8. At implementation: `make check-all`, mypy on Python 3.10, lower-bound dependency
   tests; regenerate CLI reference/results schemas; run repack doc examples.

## Risks / Trade-offs

- Полная verification добавляет read/decode pass и checksum I/O. Публиковать её
  стоимость отдельно; сохранять default safety, оптимизировать количество проходов.
- Строгая physical fidelity может отказать некоторым валидным файлам. Нужны точные
  reasons и постепенная поддержка, а не незаметное изменение schema.
- Общее выделение target затрагивает RecordSink/DuckDB: отдельные regression checks
  и синхронизация с параллельными изменениями writer.py обязательны.
- No-growth policy меняет прежний always-replace. Explicit allow-grow, changelog
  и semantics отдельного OUTPUT снижают migration cost.
- Совместимость нижней границы PyArrow 16 необходимо проверить для каждого нового
  метода; нельзя незаметно требовать API PyArrow 25 из окружения исследования.
- Resource monitoring/candidate trials не должны превращать маленькую команду в
  универсальный framework; вводить изоляцию и registry только под измеренные задачи.
