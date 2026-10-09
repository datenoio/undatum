"""Schema definition and type mapping module."""

import csv
import datetime
import logging
from copy import copy
from typing import Any

import bson
import orjson

from .functions import get_dict_value_deep

logger = logging.getLogger(__name__)

OTYPES_MAP: list[tuple[type, str]] = [
    (str, "string"),
    (str, "string"),
    (datetime.datetime, "datetime"),
    (int, "integer"),
    (bool, "boolean"),
    (float, "float"),
    (str, "string"),
    (bson.int64.Int64, "integer"),
    (bson.objectid.ObjectId, "string"),
    (type([]), "array"),
]


def merge_schemes(alist: list[Any], novalue: bool = True) -> Any:
    """Merges schemes of list of objects and generates final data schema"""
    if len(alist) == 0:
        return None
    obj = alist[0]
    okeys = obj.keys()
    for item in alist[1:]:
        for k in item.keys():
            #            print(obj[k]['type'])
            if k not in okeys:
                obj[k] = item[k]
            elif obj[k]["type"] in ["integer", "float", "string", "datetime"]:
                if not novalue:
                    obj[k]["value"] += item[k]["value"]
            elif obj[k]["type"] == "dict":
                if not novalue:
                    obj[k]["value"] += item[k]["value"]
                if "schema" in item[k].keys():
                    obj[k]["schema"] = merge_schemes([obj[k]["schema"], item[k]["schema"]])
            elif obj[k]["type"] == "array":
                #                if 'subtype' not in obj[k].keys():
                #                   logger.info(str(obj[k]))
                if "subtype" in obj[k].keys() and obj[k]["subtype"] == "dict":
                    if not novalue:
                        obj[k]["value"] += item[k]["value"]
                    if "schema" in item[k].keys():
                        obj[k]["schema"] = merge_schemes([obj[k]["schema"], item[k]["schema"]])
                elif not novalue:
                    obj[k]["value"] += item["value"]
    return obj


def get_schemes(alist: list[Any]) -> list[Any]:
    """Generates schemas for each object"""
    results = []
    for o in alist:
        results.append(get_schema(o))
    return results


def get_schema(obj: dict[str, Any], novalue: bool = True) -> dict[str, Any]:
    """Generates schema from object"""
    result = {}
    for k, value in obj.items():
        tt = type(value)
        if value is None:
            result[k] = {"type": "string", "value": 1}
        elif isinstance(value, str):
            result[k] = {"type": "string", "value": 1}
        elif tt is datetime.datetime:
            result[k] = {"type": "datetime", "value": 1}
        elif tt is bool:
            result[k] = {"type": "boolean", "value": 1}
        elif tt is float:
            result[k] = {"type": "float", "value": 1}
        elif tt is int:
            result[k] = {"type": "integer", "value": 1}
        elif tt is bson.int64.Int64:
            result[k] = {"type": "integer", "value": 1}
        elif tt is bson.objectid.ObjectId:
            result[k] = {"type": "string", "value": 1}
        elif tt is dict:
            result[k] = {"type": "dict", "value": 1, "schema": get_schema(value)}
        elif tt is list:
            result[k] = {"type": "array", "value": 1}
            if len(value) == 0:
                result[k]["subtype"] = "string"
            else:
                found = False
                for otype, oname in OTYPES_MAP:
                    if isinstance(value[0], otype):
                        result[k]["subtype"] = oname
                        found = True
                if not found:
                    if isinstance(value[0], dict):
                        result[k]["subtype"] = "dict"
                        result[k]["schema"] = merge_schemes(get_schemes(value))
                    else:
                        logger.info(f"Unknown object {k} type {str(type(value[0]))}")
        else:
            logger.info(f"Unknown object {k} type {str(type(value))}")
            result[k] = {"type": "string", "value": 1}
        if novalue:
            del result[k]["value"]
    return result


def extract_keys(
    obj: Any, parent: str | None = None, text: str | None = None, level: int = 1
) -> str:
    """Extracts keys"""
    text = ""
    if not parent:
        text = "'schema': {\n"
    for k in obj.keys():
        if isinstance(obj[k], dict):
            text += "\t" * level + f"'{k}' : {{'type' : 'dict', 'schema' : {{\n"
            text += extract_keys(obj[k], k, text, level + 1)
            text += "\t" * level + "}},\n"
        elif isinstance(obj[k], list):
            text += (
                "\t" * level
                + f"'{k}' : {{'type' : 'list', 'schema' : {{ 'type' : 'dict', 'schema' : {{\n"
            )
            if len(obj[k]) > 0:
                item = obj[k][0]
                if isinstance(item, dict):
                    text += extract_keys(item, k, text, level + 1)
                else:
                    text += "\t" * level + f"'{k}' : {{'type' : 'string'}},\n"
            text += "\t" * level + "}}},\n"
        else:
            logger.info(str(type(obj[k])))
            text += "\t" * level + f"'{k}' : {{'type' : 'string'}},\n"
    if not parent:
        text += "}"
    return text


def __get_filetype_by_ext(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in ["bson", "json", "csv", "jsonl"]:
        return ext
    return filename


def generate_scheme_from_file(
    filename: str | None = None,
    fileobj: Any = None,
    filetype: str | None = "bson",
    alimit: int = 1000,
    verbose: int = 0,
    encoding: str = "utf8",
    delimiter: str = ",",
    quotechar: str = '"',
) -> Any:
    """Generates schema of the data BSON file"""
    if not filetype and filename is not None:
        filetype = __get_filetype_by_ext(filename)
    datacache: list[Any] = []
    source: Any
    if filetype == "bson":
        if filename:
            source = open(filename, "rb")
        else:
            source = fileobj
        n = 0
        for document in bson.decode_file_iter(source):
            n += 1
            if n > alimit:
                break
            datacache.append(document)
        if filename:
            source.close()
    elif filetype == "jsonl":
        if filename:
            source = open(filename, encoding=encoding)
        else:
            source = fileobj
        n = 0
        for line in source:
            n += 1
            if n > alimit:
                break
            datacache.append(orjson.loads(line))
        if filename:
            source.close()
    elif filetype == "csv":
        if filename:
            source = open(filename, encoding=encoding)
        else:
            source = fileobj
        n = 0
        reader = csv.DictReader(
            source, quotechar=quotechar, delimiter=delimiter, quoting=csv.QUOTE_ALL
        )
        for r in reader:
            n += 1
            if n > alimit:
                break
            datacache.append(r)
        if filename:
            source.close()
    n = 0
    scheme = None
    for r in datacache:
        n += 1
        if scheme is None:
            scheme = get_schema(r)
        else:
            scheme = merge_schemes([scheme, get_schema(r)])
    return scheme


def schema2fieldslist(
    schema: dict[str, Any],
    prefix: str | None = None,
    predefined: Any = None,
    sample: Any = None,
) -> list[dict[str, Any]]:
    """Converts data schema to the fields list"""
    fieldslist = []
    for k, entry in schema.items():
        if prefix is None:
            name = k
        else:
            name = ".".join([".".join(prefix.split(".")), k])
        try:
            sampledata = get_dict_value_deep(sample, name) if sample else ""
        except Exception:
            sampledata = ""
        if "schema" not in entry.keys():
            if entry["type"] != "array":
                field = {
                    "name": name,
                    "type": entry["type"],
                    "description": "",
                    "sample": sampledata,
                    "class": "",
                }
            else:
                field = {
                    "name": name,
                    "type": "list of [{}]".format(entry["type"]),
                    "description": "",
                    "sample": sampledata,
                    "class": "",
                }
            if predefined:
                if name in predefined.keys():
                    field["description"] = predefined[name]["text"]
                    if predefined[name]["class"]:
                        field["class"] = predefined[name]["class"]
                elif k in predefined.keys():
                    field["description"] = predefined[k]["text"]
                    if predefined[k]["class"]:
                        field["class"] = predefined[k]["class"]
            if field["type"] == "datetime":
                field["class"] = "datetime"
            fieldslist.append(field)
        else:
            if prefix is not None:
                subprefix = copy(prefix) + "." + k
            #                subprefix.append(k)
            else:
                subprefix = k
            if entry["type"] == "dict":
                field = {
                    "name": name,
                    "type": entry["type"],
                    "description": "",
                    "sample": "",
                    "class": "",
                }
                if predefined:
                    if name in predefined.keys():
                        field["description"] = predefined[name]["text"]
                        if predefined[name]["class"]:
                            field["class"] = predefined[name]["class"]
                    elif k in predefined.keys():
                        field["description"] = predefined[k]["text"]
                        if predefined[k]["class"]:
                            field["class"] = predefined[k]["class"]
                fieldslist.append(field)
                fieldslist.extend(
                    schema2fieldslist(
                        entry["schema"], prefix=subprefix, predefined=predefined, sample=sample
                    )
                )
            elif entry["type"] == "array":
                field = {
                    "name": name,
                    "type": "list of [{}]".format(entry["type"]),
                    "description": "",
                    "sample": "",
                    "class": "",
                }
                if predefined:
                    if name in predefined.keys():
                        field["description"] = predefined[name]["text"]
                        if predefined[name]["class"]:
                            field["class"] = predefined[name]["class"]
                    elif k in predefined.keys():
                        field["description"] = predefined[k]["text"]
                        if predefined[k]["class"]:
                            field["class"] = predefined[k]["class"]
                fieldslist.append(field)
                fieldslist.extend(
                    schema2fieldslist(entry["schema"], prefix=subprefix, sample=sample)
                )
    return fieldslist
