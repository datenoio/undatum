# DuckDB, SQLite и другие форматы для repack

Дата проверки: 15 октября 2026 года. Исследование подготовлено до реализации;
DuckDB затем реализован в этом change после согласования пользователем. SQLite
затем реализован в [add-sqlite-repack](../2026-10-15-add-sqlite-repack/proposal.md). Разделы ниже
сохраняют исходные выводы исследования. Результаты проверки DuckDB — в `validation.md`.

## Выводы

1. Для DuckDB следует перенести алгоритм `filerepack/duckdb.py`: read-only источник →
   `COPY FROM DATABASE` в новую базу → `CHECKPOINT` → независимое сравнение каталога
   и типизированных данных → существующая атомарная публикация undatum.
2. Для SQLite реализуемо уплотнение через `VACUUM INTO`. Оно возвращает свободные
   страницы и уменьшает фрагментацию. Включения произвольного кодека сжатия в обычном
   формате SQLite эта операция не предоставляет.
3. Следующие полезные адаптеры: Arrow IPC/Feather v2, затем SQLite, HDF5 и netCDF-4.
   Для Arrow уже существует `add-native-arrow-repack`: создавать дубликат не нужно.
   ZIP-содержащие дата-файлы и Zarr требуют отдельных правил сохранности/публикации.

## Что исследовано локально

- undatum: `undatum/cmds/repacker.py`, `common/repack_types.py`,
  `common/repack_columnar.py`, `common/repack_worker.py`, `common/writer.py`,
  `common/file_snapshot.py`, CLI, результаты и документация команды.
- Активные изменения: реализованный `improve-repack-preservation`, предложения
  `add-native-arrow-repack` и `add-repack-effort-trials`.
- filerepack: `/Users/ibegtin/workspace/ivbeg/filerepack`, HEAD
  `95827f3206d68760819d1a0f21ab9acfcf74313b`; рабочее дерево содержит другие изменения.
  Изучены `filerepack/duckdb.py`, `data.py`, `qgis.py`, `hierarchical.py`, registry,
  dispatch и тесты `test/test_audited_formats.py`.
- SHA-256 исследованных исходников filerepack:
  - `duckdb.py`: `773bfce1f84a1895760ba49ecc370b3a0bef85f4513188a0939b762feef04af2`;
  - `data.py`: `83edc49b50c0a7c9cd1d6bdce39dc78a00dd3f8771dda6a298e9908ab5ebab3c`;
  - `qgis.py`: `0e11b215fa2ac3cae2f4a589d53452f27b346ae042c213d4fa24ce7de037649b`.
- Среда экспериментов: DuckDB 1.5.4, PyArrow 25.0.0, SQLite 3.53.3 в `.venv`;
  дополнительно SQLite 3.51.0 через `/usr/bin/python3`.

Эксперименты создавали базы только во временных каталогах; рабочие базы пользователя
и исходный код filerepack не изменялись. Это проверка механизма на искусственных
примерах, не benchmark реальных наборов данных и не тест ещё отсутствующего адаптера.

## DuckDB: что именно переносить

Официальная документация рекомендует полное копирование в новую базу для компактизации.
Обычный DuckDB `VACUUM` не освобождает место таким способом;
`CHECKPOINT` может частично убрать пространство удалённых строк.
См. [Reclaiming Space](https://duckdb.org/docs/current/operations_manual/footprint_of_duckdb/reclaiming_space).

В filerepack перенос уже организован консервативно:

- Проверяются заголовок `DUCK` на смещении 8, размер входа до 256 MiB и отсутствие `.wal`.
- Источник подключается read-only. Автозагрузка/установка расширений отключены,
  внешний доступ отключается до обработки выражений из базы.
- Копирование выполняется средствами движка, а не через Python-словари записей.
- Проверяются схемы, определения таблиц/индексов, defaults, nullable, типы,
  comments/tags. Views, sequences, macros/functions и custom types отклоняются.
- Сравниваются типизированные Arrow batches с вложенными значениями и битами float.
  Самостоятельный fingerprint дополнительно использует каталог и строковые проекции;
  его недостаточно вместо типизированного сравнения и проверки порядка.
- Есть пределы 1 млн строк, 256 MiB типизированных значений с каждой стороны,
  4 MiB сериализованного каталога. Их нужно явно описать при первоначальном переносе.

Адаптировать нужно алгоритм, оставив атомарную запись, savings policy, dry-run и JSON
за существующим кодом undatum. В частности, возврат `None` при любой ошибке из
filerepack не подходит: undatum должен выдавать понятную типизированную ошибку.

DuckDB выбирает внутреннее сжатие по типам/данным; воссоздание файла может изменить
физическое размещение и выбор кодирования. Это не эквивалент `zstd --level 22`.
См. [Storage Versions and Format](https://duckdb.org/docs/current/internals/storage).

### Проверенный пример

Созданы schema `data`, таблица с `INTEGER PRIMARY KEY`, `VARCHAR`, `DECIMAL(20,5)`,
`TIMESTAMP_NS`, `DOUBLE[]`, NULL, вложенным отрицательным нулём, комментарием и индексом.
В отдельную таблицу записаны 20 000 строк с
`repeat(md5(range::VARCHAR), 32)`, выполнен checkpoint, удалены все строки кроме одной
и выполнен ещё один checkpoint. Затем напрямую вызваны существующие `_rewrite`,
`duckdb_fingerprint` и `verify_duckdb` из filerepack.

| Проверка | Результат |
|---|---|
| Исходный размер | 16 265 216 байт |
| Размер нового файла | 1 323 008 байт |
| Экономия на этом примере | 91,866% |
| Catalog/logical fingerprint | Совпал |
| Независимое типизированное сравнение | Успешно |
| Изменение строки в кандидате | Обнаружено, сравнение вернуло false |
| База с view | Отклонена как неподдерживаемая |
| `undatum Repacker` до этого change на исходной базе | ValidationError: нет поддерживаемого container codec |

В filerepack интеграционные DuckDB fixtures требуют минимум DuckDB 1.4.2 и PyArrow 19;
undatum объявляет более низкие минимальные версии. Сам факт успешного запуска на
1.5.4/25.0.0 не доказывает совместимость с минимумом проекта. Это отдельная обязательная
проверка при реализации; глобально поднимать зависимости без необходимости не следует.

После реализации подтвердились требуемые catalog/COPY/Arrow API на DuckDB 1.3.0 и
PyArrow 16.1.0. Интеграция дополнительно выявила проблему порядка копирования таблиц
с foreign keys в DuckDB 1.5.4: существующая дочерняя таблица может копироваться до
родительской и вызывать ConstraintException. Адаптер undatum отклоняет foreign keys
ещё до staging, не удаляя ограничения. Полная проверка минимальных версий и итоговые
счётчики тестов приведены в `validation.md`.

## SQLite: реализуемость и предлагаемый контракт

### Уплотнение совместимо с обычными SQLite-клиентами

`VACUUM INTO` строит компактную новую базу и оставляет источник без изменений. Это
подходящая основа для staged candidate. Нужно сверять данные и метаданные и применять
обычную savings policy: плотно упакованная база может не уменьшиться.
Документация также допускает изменение неявных `ROWID` при `VACUUM`.
См. [SQLite VACUUM](https://www.sqlite.org/lang_vacuum.html).

Проверять необходимо `sqlite_schema`, таблицы/индексы/триггеры/views, реальные значения
и SQLite storage classes, `rowid`, `sqlite_sequence`, `application_id`, `user_version`,
encoding, foreign keys и `PRAGMA integrity_check`. Для `WITHOUT ROWID` нужен стабильный
обход по ключу. Нельзя подменять значения строковым представлением или запускать
табличные триггеры как при ручном импорте. Virtual tables, неизвестные collations,
генерируемые выражения с внешними функциями и зашифрованные базы требуют явного
отдельного supported profile.

Практичный первый этап: закрытая база без `-wal`, `-shm`, `-journal`, read-only источник,
`VACUUM INTO` кандидата и независимая проверка. Для in-place нужна политика offline,
как в filerepack. Условие отсутствия sidecars не является доказательством, что все
пользователи базы закрыты.

### Для живой базы нужен отдельный путь snapshot

Нельзя копировать только основной `.sqlite` файл при наличии WAL: подтверждённые
транзакции могут находиться в WAL. Правила WAL и read-only работы описаны в
[SQLite WAL](https://sqlite.org/wal.html).

Рекомендуемый следующий этап: SQLite backup API в приватную snapshot-базу, её уплотнение
и публикация только в отдельный OUTPUT. Это меняет понятие источника проверки: сравнивать
нужно с зафиксированным snapshot, а не с продолжающей изменяться live-базой. Текущий
single-file `FileSnapshot` не покрывает такой контракт автоматически.

### Эксперименты с SQLite

| Проверка | Результат |
|---|---|
| База после удаления 1000 BLOB по 2048 байт | 4 116 480 → 12 288 байт, экономия 99,701% |
| `PRAGMA integrity_check` нового файла | `ok` |
| Сохранность значений и `INTEGER PRIMARY KEY` | Подтверждена |
| `VACUUM INTO`, неявные rowid 10, 99, 1000 | Сохранились на SQLite 3.51.0 и 3.53.3 |
| Обычный `VACUUM`, те же rowid | Изменились на 1, 2, 3 на обеих версиях |
| Backup API при открытом WAL и committed INSERT | Подтверждённая строка вошла в snapshot |

Поэтому нельзя незаметно заменять неудачный `VACUUM INTO` на `backup + VACUUM`, даже
если это делает существующий общий packer filerepack. Более строгий проверяющий код
`filerepack/qgis.py` учитывает rowid и отклоняет изменившийся кандидат; этот принцип
следует сохранить. Два проверенных SQLite runtime не дают гарантии для всех версий и
структур базы, поэтому проверка идентификаторов нужна в каждом успешном repack.

### Настоящее сжатие SQLite требует другого формата/окружения

Обычная компактизация не сжимает повторяющиеся поля произвольным кодеком. SQLite ZIPVFS
умеет сжатие страниц, но требует соответствующего VFS в читателе и имеет другой
заголовок файла. Поэтому такой режим должен быть явной конвертацией/экспортом с новым
контрактом совместимости, а не обещанием сохраняющего repack стандартной SQLite-базы.
См. [ZIPVFS File Format](https://sqlite.org/zipvfs/doc/trunk/www/fileformat.wiki).

GeoPackage (`.gpkg`), MBTiles (`.mbtiles`) и прикладные SQLite-контейнеры могут получать
выигрыш от уплотнения. Пересжатие уже хранящихся внутри JPEG/PNG/vector-tile BLOB —
другая операция с отдельными правилами; `VACUUM INTO` их содержимое не перекодирует.

## Для каких ещё дата-файлов подходит recompression

Здесь «реализуемо» означает наличие механизма формата; это не обещание текущей
поддержки undatum или гарантированной экономии на каждом файле.

| Формат | Механизм | Текущий undatum / следующий шаг |
|---|---|---|
| CSV, TSV, JSON, JSONL, XML, BSON и произвольные байты в `.gz/.bz2/.xz/.lzma/.zst/.lz4/.br` | Полное декодирование/кодирование внешнего потока с точной проверкой байтов | Уже реализовано; внутренний формат разбирать не нужно |
| Parquet | Пересжатие column chunks и допустимое изменение row groups | Уже реализован native adapter |
| ORC | Пересжатие stripes; native codec и strategy | Уже реализован native adapter |
| Avro OCF | Смена codec encoded blocks без изменения схемы/union choices | Уже реализован native adapter |
| Arrow IPC / Feather v2 | LZ4 ↔ ZSTD / изменение уровня при сохранении framing, dictionaries и metadata | Приоритетный follow-up; уже есть proposal `add-native-arrow-repack` |
| HDF5, включая MATLAB v7.3 как специальный профиль | `h5repack`: chunking и lossless filters, например gzip+shuffle | Отдельный adapter; сохранять links, references, attrs, dtype; не включать lossy scale-offset |
| netCDF-4 | `nccopy`: deflate, shuffle, chunk sizes | Отдельный adapter; сохранять groups/dimensions/attrs и raw значения |
| netCDF classic / 64-bit offset | Собственного внутреннего deflate нет; для него требуется netCDF-4 | Внешний stream codec либо явная конвертация; не скрывать смену варианта формата |
| Zarr v2/v3 | Перекодирование chunks lossless codecs/filters | Отдельная задача: часто это каталог/много объектов, нужен store-level publish вместо file rename |
| NumPy `.npz` | ZIP-DEFLATE с неизменными `.npy` members | Требуется сохраняющий ZIP adapter; текущий repack ZIP отклоняет |
| NumPy `.npy` | Собственного внутреннего codec нет | Внешнее сжатие либо явная конвертация в `.npz`/другой формат |
| NRRD | gzip/bzip2 data encoding | Возможен узкий adapter; detached headers/внешние data files требуют отдельного контракта |
| FITS | Tiled image compression | Возможен специальный lossless profile; исключить float quantization и проверять HDU/header metadata |
| XLSX/XLSM, ODS и другие ZIP-пакеты данных | Пересжатие ZIP members с сохранением их исходных байтов и структуры | Отдельный package-preserving adapter; не переписывать workbook через CSV/DataFrame |

Механизмы подтверждены первичной документацией:

- [Arrow Feather](https://arrow.apache.org/docs/python/feather.html): v2 использует IPC
  и поддерживает LZ4/ZSTD; v1 не включается автоматически в этот профиль.
- [HDF5 h5repack](https://support.hdfgroup.org/documentation/hdf5/latest/_h5_t_o_o_l__r_p__u_g.html):
  изменение filters/layout, включая gzip/shuffle. Не каждый фильтр lossless для всех типов.
- [netCDF nccopy](https://docs.unidata.ucar.edu/nug/current/netcdf_utilities_guide.html):
  compression/chunking, переход classic → netCDF-4 при запросе внутреннего deflate.
- [Zarr arrays](https://zarr.readthedocs.io/en/stable/user-guide/arrays/): chunk codecs,
  compressors и filters. Вывод о необходимости отдельной публикации store следует из
  многофайловой структуры Zarr и текущего single-file контракта undatum.
- [NumPy savez_compressed](https://numpy.org/doc/stable/reference/generated/numpy.savez_compressed.html):
  `.npz` — ZIP-DEFLATE с `.npy` members.
- [NRRD specification](https://teem.sourceforge.net/nrrd/format.html): gzip/bzip2 encoding
  и detached data.
- [Astropy compressed images](https://docs.astropy.org/en/stable/io/fits/api/images.html):
  lossless integer image compression и отдельные параметры float quantization.
- ZIP-пакеты `.npz`, XLSX/XLSM/ODS уже перечислены в локальном
  `filerepack/format_registry.py`; перенос их целиком не входит в DuckDB adapter.

Предлагаемый порядок: DuckDB в этом change; Arrow/Feather по существующему proposal;
SQLite с отдельным offline/snapshot контрактом; HDF5/netCDF-4; затем сохраняющий ZIP
adapter и специализированные научные форматы. Zarr целесообразно делать после
появления подходящего контракта публикации для набора объектов.
