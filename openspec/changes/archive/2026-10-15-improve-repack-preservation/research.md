# Сравнение repack в undatum и filerepack

Дата: 2026-10-13. Основной вывод: повышение степени сжатия следует начинать с
гарантий сохранности. В нынешней реализации успешная запись не доказывает, что
данные, типы и метаданные сохранились.

## Источники и границы проверки

- undatum: локальный checkout, HEAD `22c15df279601dbc9acf296507f0358e44c28d48`.
  Исследованы `undatum/cmds/repacker.py`, wrapper `undatum/cli/commands/convert.py`,
  `tests/test_repack.py`, документация, shared writer/results/progress и активные OpenSpec.
- filerepack: `/Users/ibegtin/workspace/ivbeg/filerepack`, HEAD
  `95827f3206d68760819d1a0f21ab9acfcf74313b`, вместе с текущими локальными изменениями.
  `parquet.py`, `candidates.py`, `transactions.py` не имели локального diff при проверке.
  `avro.py`, `columnar.py`, `profiles.py`, `streams.py` имеют незакоммиченные изменения;
  `compression.py` — untracked. Расширенные encoder trials и profile version 4 ниже
  относятся к рабочему дереву, их нельзя автоматически считать возможностями релиза.
- Публично проверены [репозиторий filerepack](https://github.com/ivbeg/filerepack),
  [Parquet writer](https://raw.githubusercontent.com/ivbeg/filerepack/master/filerepack/parquet.py),
  [candidate lifecycle](https://raw.githubusercontent.com/ivbeg/filerepack/master/filerepack/candidates.py),
  [transactions](https://raw.githubusercontent.com/ivbeg/filerepack/master/filerepack/transactions.py).
  Для параметров формата использована
  [документация PyArrow ParquetWriter](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetWriter.html).
  Выводы о коде основаны прежде всего на прочитанных исходниках, а не на README.
- Воспроизведения undatum: `.venv/bin/python`, Python 3.13.7, iterabledata 1.0.21
  из site-packages этого venv, PyArrow 25.0.0. Системный `python` использует другой,
  editable checkout iterabledata; для воспроизведений он намеренно не использовался.
- Проверки выполнялись только на временных данных. Это анализ корректности и
  архитектуры, не полноценный сравнительный performance benchmark.
- Во время анализа появились параллельные изменения в других production files undatum.
  Их не редактировали; при реализации сверить актуальный shared writer и OpenSpec.

## Как работает undatum сейчас

1. CLI принимает один локальный INPUT и необязательный позиционный OUTPUT, `--level`,
   `--compression`, progress и verbose. Возвращаемый `dict` из Repacker wrapper не выводит.
2. `repack()` отвергает URI, проверяет входной путь и определяет формат через
   `iterable.helpers.detect.detect_file_type()`.
3. Несжатые Parquet/ORC/Avro отправляются в native ветку. Остальные входы/выходы с
   кодеком идут в container ветку: override → суффикс OUTPUT → кодек INPUT.
4. Container путь читает распакованный поток блоками по 1 MiB и сразу пишет через
   codec registry iterabledata. Полный распакованный файл на диск не сохраняется.
5. Parquet читается `ParquetFile.iter_batches()`, каждый batch пишется через
   `ParquetWriter.write_batch()`. Default — zstd 19 из iterabledata max profile.
6. ORC/Avro вызывают `iterable.convert.convert()` только с опцией compression:
   исходная schema и metadata явно не передаются. `atomic=False`.
7. Временный sibling создаётся лишь если OUTPUT отсутствует. После записи выполняется
   `os.replace()` без независимой проверки кандидата и экономии. Отдельный OUTPUT
   открывается непосредственно encoder-ом.

Сильные стороны: потоковая byte-preserving модель для обычных контейнеров;
bounded transfer buffer; использование общего codec registry; lazy imports;
явное ограничение локальными файлами; cleanup для обычного implicit in-place пути.
Эти свойства следует сохранить.

## Подтверждённые проблемы

Все строки ниже — результаты отдельных воспроизведений на временных файлах,
кроме явно обозначенных наблюдений по исходникам.

| Приоритет | Сценарий | Фактическое поведение | Причина |
|---|---|---|---|
| P0 | INPUT и явный OUTPUT — один gzip | 32 → 29 байт; успех; decompressed payload стал пустым | `inplace = tofile is None`, строка 94; writer обнуляет читаемый файл |
| P0 | Пустой Parquet, OUTPUT отсутствует | Валидные 335 байт → 0 байт; успех | Writer создаётся только внутри первого batch, строки 343–351; пустой tempfile публикуется |
| P0 | ORC `struct<n:bigint,flag:boolean>` с `(42, True)` | Выход `struct<n:string,flag:string>`, 0 строк, metadata исчезла; успех | Общий convert создаёт строковую schema; ошибка final batch логируется без исключения наверх |
| P0 | Avro с long/boolean и custom metadata, target deflate | `{n:42, flag:true}` → `{n:"42", flag:"True"}`; новая schema/record name/namespace; custom metadata исчезла | Convert выводит nullable-string schema; native serialization identity не сохраняется |
| P0 | Обрезанный gzip → существующий отдельный OUTPUT | `EOFError`, но старый OUTPUT уже уничтожен и заменён 33 байтами частичного результата | Отдельный OUTPUT не staged |
| P1 | Уже компактный gzip in-place | 32 → 57 байт; успех | Нет no-growth policy; gzip header включает длинное временное имя |
| P1 | Обычный mode 0644, implicit in-place | После замены mode 0600 | Публикуется tempfile без восстановления filesystem metadata |
| P1 | Parquet → `output.parquet.gz` | Файл начинается `PAR1`, внешнего gzip нет; успех | Native ветка имеет приоритет над output codec; суффикс игнорируется |
| P1 | Parquet с `sorting_columns` | Sorting declaration исчезает | Параметры физической структуры не переносятся/не проверяются |
| P1 | Parquet с INT96 timestamps | INT96 → INT64 при сохранении Arrow timestamp type | Native path сохраняет логическую schema, не проверяет физическую compatibility |
| P2 | Parquet: 200 000 строк, 2 row groups по 100 000 | Получается 4 row groups | `write_batch()` связывает layout с default batch size 65 536 |
| P1 | Архив `multi.csv.zip` с двумя файлами → gzip | `ValueError: open() requires mode "r" or "w"`; выход создан | ZIPCodec iterabledata не соответствует ожидаемому binary stream API |
| P1 | Архив `multi.zip` → gzip | Успех: gzip оборачивает целиком ZIP, вместо чтения members | Detect без datatype возвращает success=False; repack теряет и codec evidence |

ZIPCodec в установленном iterabledata выбирает `namelist()[0]`. Поэтому просто
исправить его binary-mode вызов недостаточно: после такой починки single-stream
перепаковка может потерять остальные members. В текущем окружении потеря members
не воспроизведена, поскольку операция падает раньше. ZIP/7z требуют отдельного
контракта; до него их нельзя рекламировать как надёжные stream codecs.

Дополнительные наблюдения по исходникам:

- `--compression` может сменить внешний кодек при сохранении старого имени INPUT;
  универсального контроля согласованности suffix/codec нет.
- Уровень не валидируется по возможностям backend до начала записи; ORC/Avro
  документированно игнорируют `--level`, что ограничивает управляемость.
- Container result содержит `profile=max`, но `level=None`, поскольку сообщает
  переданные options, а не реально разрешённые encoder settings.
- `_detect()` подавляет все исключения и возвращает отсутствие codec/datatype:
  ошибка детектора и настоящий raw input неразличимы. Текущий comment про fallback
  extension heuristics не соответствует этому методу.
- Cleanup последовательно закрывает writer/reader; исключение из `writer.close()`
  может помешать закрытию reader и скрыть первоначальную ошибку.
- Нет проверки source generation, политики для ссылок, штатных dry-run/no-growth
  outcomes, machine-readable сводки repack, отдельных budget/benchmark тестов.

Не следует преувеличивать проблемы Parquet: отдельная проверка custom key/value
metadata `external=keep-this` прошла — ключ сохранился через batch schema на
PyArrow 25.0.0. В ней не было потери metadata. Проблема — отсутствие проверяемого
контракта для всего допустимого диапазона schemas и physical representations.

## Что лучше устроено в filerepack

| Аспект | Реализация filerepack | Что взять в undatum |
|---|---|---|
| Жизненный цикл | `candidates.commit_output()` проверяет наличие/структуру кандидата, preservation, размер, dryrun и затем publish | Один commit policy для всех путей repack |
| Размер | `keep_if_larger=True` фактически означает отказ от большего/равного кандидата; min_savings; CLI allow-grow | Ясный `allow_grow=False`, без переноса неоднозначного имени |
| Файлы | `FileSnapshot`, generation + SHA-256; повторная проверка; sibling stage рядом с destination | Guard для источника/назначения, атомарная видимость, metadata preservation |
| Ссылки | In-place symlink/multiple-hardlink отказ; distinct copy допускается | Такой же явный policy до записи |
| Parquet | PyArrow, original schema/version, file metadata, physical+logical checks, aligned batch value comparison | Проверяемая native перепаковка, включая empty и сложные типы |
| Avro | Recompress encoded blocks, schema bytes/metadata/sync/union choices сохранены; native validation | Предпочтительно не десериализовать и не выводить schema из строк |
| ORC | Typed stripe writer, equality schema/values; metadata без preserving writer отвергается | Typed reader/writer с исходной schema; safe refusal при невозможности сохранения |
| Arrow/Feather | Сохраняет IPC framing и batch metadata, проверяет результат | Следующая естественная форматная capability после исправления текущих трёх |
| Отчёт | `RepackOutcome`: status/reason_code/published, source/destination, sizes, elapsed | Dataclasses + `undatum.repack/1`, совместимость со старым return dict |
| Настройки | Профили с provenance; явные False/default overrides не теряются | Explicit option precedence и реально применённые settings |
| Ресурсы | `Budget`, decoded/memory/scratch/time; отдельные workers для native операций | Измеряемые budgets и честное различение soft/hard limits |
| Тесты | Real readers, corruption/fault injection, independent DuckDB read-back | Тестировать публикацию испорченного кандидата, а не только успех encoder-а |

В локальном рабочем дереве filerepack дополнительно есть подбор encoder candidates:
libdeflate/zopfli для небольших gzip, XZ extreme/delta, zstd long/ultra, более
сильные Arrow/ORC настройки. Каждый дополнительный кандидат проверяется и заменяет
baseline только при выигрыше. Это хороший принцип для позднего opt-in режима;
не основание автоматически включать самые дорогие алгоритмы в undatum.

## Что не стоит копировать напрямую

- Stream packers filerepack часто сначала распаковывают весь payload во временный
  файл, затем кодируют. Для больших CSV/JSONL это дополнительный scratch и I/O;
  прямой streaming путь undatum предпочтительнее как default.
- Глобальная шкала compression_level 1–9 filerepack не переносится на zstd, brotli,
  lz4 и native formats. Undatum уже имеет codec-specific профили iterabledata.
- Parquet packer filerepack сейчас выбирает 19/22 по ultra; это не готовый единый
  интерфейс для всех explicit levels. Его row-group layout тоже следует измерять.
- Консервативный отказ filerepack для некоторых physical Parquet/ORC profiles полезен
  как безопасная отправная точка, но не заменяет последующую поддержку их сохранения.
- Broad catch-and-return-None и эвристическое сопоставление человеческого error text
  с reason codes не подходят для CLI exit-code контракта undatum.
- Не переносить весь multimedia/archive framework, tool discovery, prediction cache,
  SQLite/HDF5/Zarr adapters. Это размывает задачу улучшения data repack.
- Максимальный compression level, больший dictionary/window или сортировка записей
  не гарантируют лучший общий результат: учитывать RSS, decoder requirements и
  downstream scan time; изменение порядка строк не допускается.

## Результаты проверки

```text
undatum:
  .venv/bin/python -m pytest tests/test_repack.py -q
  10 passed in 1.71s

filerepack:
  venv/bin/python -m pytest test/test_parquet_preservation.py \
    test/test_data_preservation.py test/test_transactions.py -q
  90 passed, 2 skipped in 3.79s
```

Дополнительный прямой вызов filerepack на таком же 32-byte gzip оставил исходные
байты и размер 32 неизменными: `status=unchanged`, `reason_code=no_benefit`.

Пропуски filerepack: тесты реального второго filesystem `/dev/shm`, недоступного
на этом macOS. Успешные проверки отражают указанное локальное окружение; они не
доказывают абсолютное превосходство всех adapters или всех релизов.

Для повторения опасных сценариев использовать временный каталог и передавать
только его пути в `Repacker.repack()`:

1. Записать `gzip.compress(b'a,b\n1,2\n3,4\n', compresslevel=1, mtime=0)`;
   вызвать `repack(str(path), str(path), {'progress': False})`; сравнить payload.
2. Записать `pq.write_table(pa.table({'n': pa.array([], type=pa.int64())}), path)`;
   вызвать без OUTPUT; повторно открыть Parquet и сравнить schema.
3. Создать ORC через pyorc с `struct<n:bigint,flag:boolean>`, `(42, True)` и
   user metadata; сравнить typed rows/schema после repack с отдельным OUTPUT.
4. Создать Avro через `DataFileWriter` с long/boolean, custom metadata;
   repack с `compression='deflate'`; сравнить original schema/typed records/metadata.
5. Усечь gzip trailer на 7 байт; создать отдельный OUTPUT с контрольным содержимым;
   после ошибки проверить сохранность старого назначения.

План исправлений и расширения возможностей приведён в [design.md](design.md).
