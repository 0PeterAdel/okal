"""Bounded local document extraction. Embedded text never becomes instructions."""

import csv
import io
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

from ..intelligence import SECRET
from .process import run


def extract(path, data, check):
    suffix = Path(path).suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".tsv", ".log"}:
        value = data.decode("utf-8-sig")
        if suffix == ".json":
            value = json.dumps(json.loads(value), ensure_ascii=False, indent=2)
        if suffix in {".csv", ".tsv"}:
            rows = csv.reader(
                io.StringIO(value), delimiter="\t" if suffix == ".tsv" else ","
            )
            value = "\n".join(" | ".join(row) for _, row in zip(range(200), rows))
    elif suffix == ".pdf":
        if not shutil.which("pdftotext") or not shutil.which("bwrap"):
            raise ValueError("pdftotext_unavailable")
        value = run(
            [
                "/usr/bin/bwrap",
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib",
                "/lib64",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--clearenv",
                "--setenv",
                "PATH",
                "/usr/bin:/bin",
                "--",
                "/usr/bin/pdftotext",
                "-f",
                "1",
                "-l",
                "30",
                "-layout",
                "-",
                "-",
            ],
            check,
            20,
            data,
        ).decode("utf-8")
    elif suffix in {".docx", ".xlsx"}:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000 or sum(i.file_size for i in infos) > 8 * 1024 * 1024:
                raise ValueError("document_expansion_limit")
            names = (
                ["word/document.xml"]
                if suffix == ".docx"
                else [
                    i.filename
                    for i in infos
                    if i.filename == "xl/sharedStrings.xml"
                    or i.filename.startswith("xl/worksheets/sheet")
                    and i.filename.endswith(".xml")
                ][:20]
            )
            strings = []
            shared = []
            for name in names:
                check()
                xml = archive.read(name)
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise ValueError("xml_entities_denied")
                root = ET.fromstring(xml)
                if name == "xl/sharedStrings.xml":
                    shared = ["".join(n.itertext()) for n in root]
                    continue
                if suffix == ".docx":
                    strings.extend(
                        "".join(n.itertext())
                        for n in root.iter()
                        if n.tag.endswith("}p")
                    )
                else:
                    for row in root.iter():
                        if not row.tag.endswith("}row"):
                            continue
                        cells = []
                        for cell in row:
                            values = [
                                n.text or ""
                                for n in cell.iter()
                                if n.tag.endswith("}v") or n.tag.endswith("}t")
                            ]
                            raw = " ".join(values)
                            if (
                                cell.get("t") == "s"
                                and raw.isdigit()
                                and int(raw) < len(shared)
                            ):
                                raw = shared[int(raw)]
                            cells.append(raw)
                        strings.append(" | ".join(cells))
            value = "\n".join(strings)
    else:
        raise ValueError("unsupported_document_format")
    if SECRET.search(value):
        raise ValueError("credential_like_document_rejected")
    return {
        "path": path,
        "text": value[:12000],
        "limited": len(value) > 12000 or suffix in {".pdf", ".csv", ".tsv", ".xlsx"},
    }
