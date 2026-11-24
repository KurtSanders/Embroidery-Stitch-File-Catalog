#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import configparser
import hashlib
import html
import json
import logging
import os
import re
import shutil
import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import pyembroidery
from colorama import Fore, Style, init as colorama_init
from tqdm import tqdm

try:
    from osxmetadata import OSXMetaData
except ImportError:
    OSXMetaData = None


__version__ = "1.0.0"

# Preference order when multiple formats exist for the same design
SUPPORTED_EXTENSIONS = (".vp3", ".hus", ".vip")
RENDERABLE_EXTENSIONS = {".vp3", ".hus"}
FORMAT_PRIORITY = {".vp3": 0, ".hus": 1, ".vip": 2}
IMAGE_FALLBACK_EXTENSIONS = (".jpg", ".jpeg", ".png")

# Matches hoop dimensions (4x4, 5X7, birthdayballoons4x4), single dimensions (5inch, 6in, 130mm, 15cm), and size labels
SIZE_TOKEN_RE = re.compile(
    r"(?:"
    r"(?:^|[\s_\-(]+|(?<=[a-zA-Z]))(\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*(?:inch(?:es)?|in|mm|cm))?)(?=$|[\s_\-).])"
    r"|"
    r"(?:^|[\s_\-(]+)(\d+(?:\.\d+)?\s*(?:inch(?:es)?|in|mm|cm)|xxs|xs|sm|small|med|medium|lrg|large|xl|xxl|jumbo|mini)(?=$|[\s_\-).])"
    r")",
    re.IGNORECASE,
)

HOOP_DIM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)")
SINGLE_DIM_RE = re.compile(r"(?:^|[\s_\-(])(\d+(?:\.\d+)?)\s*(?:inch(?:es)?|in|mm|cm)(?=$|[\s_\-).])", re.IGNORECASE)
SIZE_OR_FORMAT_DIR_RE = re.compile(
    r"^(?:vp3|vip|hus|\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*(?:inch(?:es)?|in|mm|cm))?|\d+(?:\.\d+)?\s*(?:inch(?:es)?|in|mm|cm)|(?:xxs|xs|sm|small|med|medium|lrg|large|xl|xxl|jumbo|mini))(?:\s*hoop)?$",
    re.IGNORECASE,
)


@dataclass
class AppConfig:
    root_dir: Path
    start_dir: Path
    catalog_dir: Path
    images_dir: Path
    html_file: Path
    favicon_file: Path
    excluded_folders: list[str]
    max_files: int
    table_cols: int
    log_level: int
    recreate_images: bool = False
    clean_images: bool = False


@dataclass
class DesignEntry:
    catalog_name: str
    display_name: str
    canonical_key: str
    stitch_file: Path
    stitch_rel_path: str
    image_file: Path | None = None
    image_rel_path: str | None = None
    sizes: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    group_filenames: list[str] = field(default_factory=list)
    fallback_jpg: Path | None = None
    needs_render: bool = False


class DynamicContextFilter(logging.Filter):
    def __init__(self, prefix: str = f"{Fore.RESET}", suffix: str = f"{Style.RESET_ALL}"):
        super().__init__()
        self.prefix = prefix
        self.suffix = suffix

    def filter(self, record: logging.LogRecord) -> bool:
        record.prefix_data = getattr(record, "prefix_data", self.prefix)
        record.suffix_data = getattr(record, "suffix_data", self.suffix)
        return True


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    log = logging.getLogger("EmbroideryCatalog")
    log.setLevel(level)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(DynamicContextFilter())
        formatter = logging.Formatter("%(prefix_data)s%(levelname)s: %(message)s%(suffix_data)s")
        handler.setFormatter(formatter)
        log.addHandler(handler)
    return log


def load_config(script_dir: Path, log: logging.Logger) -> AppConfig:
    config_path = script_dir / "config.ini"
    parser = configparser.ConfigParser()
    if not parser.read(config_path):
        sample_path = script_dir / "config.sample.ini"
        log.critical(
            f"{Fore.RED}Fatal Error: Configuration file not found at {Fore.MAGENTA}{config_path}\n"
            f"{Fore.YELLOW}Copy {sample_path.name} to config.ini and update your embroidery folder paths."
        )
        sys.exit(99)

    try:
        root_dir = Path(parser.get("General", "root_embroidery_directory")).expanduser()
        start_dir = Path(parser.get("General", "embroidery_start_directory")).expanduser()
        catalog_dir_raw = parser.get("General", "catalog_directory", fallback="").strip()
        excluded_raw = parser.get("General", "excluded_folders", fallback="")
        max_files = parser.getint("General", "max_files", fallback=100000)
        table_cols = max(1, parser.getint("General", "table_cols", fallback=6))
        log_level_name = parser.get("General", "log_level", fallback="info").strip().lower()
        recreate_images = parser.getboolean("General", "recreate_images", fallback=False)
        clean_images = parser.getboolean("General", "clean_images", fallback=False)
    except (configparser.NoOptionError, configparser.NoSectionError, ValueError) as exc:
        log.critical(f"{Fore.RED}Error reading config.ini: {Fore.YELLOW}{exc}")
        sys.exit(10)

    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    if log_level_name not in level_map:
        log.critical(
            f"Invalid log_level in config.ini: '{log_level_name}'. "
            f"Valid levels: {', '.join(level_map)}"
        )
        sys.exit(1)

    excluded_folders = [item.strip().lower() for item in excluded_raw.split(",") if item.strip()]
    catalog_dir = Path(catalog_dir_raw).expanduser() if catalog_dir_raw else (root_dir / "Catalog")
    images_dir = catalog_dir / "images"

    return AppConfig(
        root_dir=root_dir,
        start_dir=start_dir,
        catalog_dir=catalog_dir,
        images_dir=images_dir,
        html_file=catalog_dir / "Embroidery_image_table.html",
        favicon_file=images_dir / "K+N_favicon.svg",
        excluded_folders=excluded_folders,
        max_files=max_files,
        table_cols=table_cols,
        log_level=level_map[log_level_name],
        recreate_images=recreate_images,
        clean_images=clean_images,
    )


def ensure_directories_and_favicon(cfg: AppConfig, script_dir: Path, log: logging.Logger) -> None:
    if not cfg.start_dir.is_dir():
        log.critical(f"{Fore.RED}Start directory does not exist: {Fore.YELLOW}{cfg.start_dir}")
        sys.exit(99)

    cfg.catalog_dir.mkdir(parents=True, exist_ok=True)
    cfg.images_dir.mkdir(parents=True, exist_ok=True)

    if cfg.favicon_file.exists():
        return

    local_favicon = script_dir / "images" / "K+N_favicon.svg"
    if local_favicon.is_file():
        shutil.copy2(local_favicon, cfg.favicon_file)
        log.debug(f"Copied local favicon to {cfg.favicon_file}")
    else:
        log.warning(f"Local favicon not found at {local_favicon}; continuing without favicon.")


def clean_images_folder(cfg: AppConfig, log: logging.Logger) -> None:
    """Remove all cached thumbnail folders/files in Catalog/images/ except K+N_favicon.svg."""
    if not cfg.images_dir.is_dir():
        return

    removed_dirs = 0
    removed_files = 0
    keep_name = cfg.favicon_file.name

    for item in cfg.images_dir.iterdir():
        if item.name == keep_name:
            continue
        if item.is_dir():
            shutil.rmtree(item)
            removed_dirs += 1
        else:
            item.unlink()
            removed_files += 1

    log.info(
        f"{Fore.YELLOW}Cleaned {cfg.images_dir}: removed {removed_dirs:,} folder(s) and "
        f"{removed_files:,} file(s) (preserved {keep_name})."
    )


def camel_to_spaces(text: str) -> str:
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    s2 = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", s1)
    return s2


def extract_size_tokens(stem: str) -> list[str]:
    tokens = [
        (m.group(1) or m.group(2)).strip().lower().replace(" ", "")
        for m in SIZE_TOKEN_RE.finditer(stem)
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def normalize_design_name(filename: str) -> tuple[str, str]:
    """
    Strip hoop dimensions and size tokens from a filename.
    Returns (canonical_key, display_name).
    """
    stem = Path(filename).stem
    stripped = SIZE_TOKEN_RE.sub(" ", stem)
    stripped = re.sub(r"[()\[\]]", " ", stripped)
    stripped = re.sub(r"[._\-]+", " ", stripped)
    spaced = camel_to_spaces(stripped)
    display_name = re.sub(r"\s+", " ", spaced).strip()

    if not display_name:
        display_name = re.sub(r"\s+", " ", camel_to_spaces(re.sub(r"[._\-]+", " ", stem))).strip()

    canonical_key = display_name.lower()
    return canonical_key, display_name


def _size_sort_key(path: Path) -> tuple[int, float, str]:
    """Sort key that priorities preferred formats first, then larger hoop dimensions."""
    ext_rank = FORMAT_PRIORITY.get(path.suffix.lower(), 99)
    match = HOOP_DIM_RE.search(path.stem)
    if match:
        area = float(match.group(1)) * float(match.group(2))
    else:
        single = SINGLE_DIM_RE.search(path.stem)
        area = float(single.group(1)) ** 2 if single else 0.0
    # Negative area prefers larger/more detailed stitch files when rendering thumbnails
    return (ext_rank, -area, path.name.lower())


def get_catalog_folder_name(dirpath: Path, root_dir: Path) -> str:
    try:
        rel_parts = dirpath.resolve().relative_to(root_dir.resolve()).parts
        return rel_parts[0] if rel_parts else root_dir.name
    except ValueError:
        return dirpath.name


def find_matching_jpg(canonical_key: str, jpg_files: list[Path]) -> Path | None:
    if not jpg_files:
        return None
    for jpg in jpg_files:
        jpg_key, _ = normalize_design_name(jpg.name)
        if jpg_key == canonical_key:
            return jpg
    return jpg_files[0]


def to_url_relpath(target: Path, base_dir: Path) -> str:
    rel = os.path.relpath(target, base_dir).replace(os.sep, "/")
    return quote(rel, safe="/")


def is_excluded_dir(dirname: str, excluded_keywords: list[str]) -> bool:
    if dirname.startswith("."):
        return True
    lowered = dirname.lower()
    return any(keyword in lowered for keyword in excluded_keywords)


def get_logical_group_dir(dirpath: Path, root_dir: Path) -> Path:
    """Collapse trailing size-only or format-only subfolders (e.g. 5inch/, 4x4/, VP3/) so sibling variants merge."""
    cur = dirpath
    root_resolved = root_dir.resolve()
    while cur.resolve() != root_resolved and SIZE_OR_FORMAT_DIR_RE.match(cur.name.strip()):
        cur = cur.parent
    return cur


def scan_embroidery_designs(cfg: AppConfig, log: logging.Logger) -> list[DesignEntry]:
    # Group across the whole scan by (catalog_name, logical_group_dir, canonical_key)
    # so size/format variants in the same folder OR sibling size/format subfolders collapse cleanly.
    grouped_files: dict[tuple[str, Path, str], list[Path]] = {}
    display_names: dict[tuple[str, Path, str], str] = {}
    jpgs_by_group_dir: dict[Path, list[Path]] = {}
    scanned_files_count = 0

    for dirpath_str, dirnames, filenames in os.walk(cfg.start_dir, topdown=True):
        # Mutate dirnames in place so os.walk actually skips excluded directories
        dirnames[:] = sorted(
            d for d in dirnames if not is_excluded_dir(d, cfg.excluded_folders)
        )
        visible_files = sorted(f for f in filenames if not f.startswith("."))
        if not visible_files:
            continue

        dirpath = Path(dirpath_str)
        logical_dir = get_logical_group_dir(dirpath, cfg.root_dir)
        catalog_name = get_catalog_folder_name(dirpath, cfg.root_dir)

        for fname in visible_files:
            fpath = dirpath / fname
            ext = fpath.suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                scanned_files_count += 1
                canonical_key, disp = normalize_design_name(fpath.name)
                gkey = (catalog_name, logical_dir, canonical_key)
                grouped_files.setdefault(gkey, []).append(fpath)
                display_names.setdefault(gkey, disp)
            elif ext in IMAGE_FALLBACK_EXTENSIONS:
                jpgs_by_group_dir.setdefault(logical_dir, []).append(fpath)

    entries: list[DesignEntry] = []
    used_stems_per_catalog: dict[str, set[str]] = {}

    for gkey, group_files in grouped_files.items():
        catalog_name, logical_dir, canonical_key = gkey
        used_stems = used_stems_per_catalog.setdefault(catalog_name, set())

        # Pick the best representative (prefers .vp3 > .hus > .vip, then largest hoop/size)
        best_file = min(group_files, key=_size_sort_key)

        sizes_set: list[str] = []
        formats_set: list[str] = []
        for gf in sorted(group_files, key=lambda p: p.name.lower()):
            for token in extract_size_tokens(gf.stem):
                if token not in sizes_set:
                    sizes_set.append(token)
            fmt = gf.suffix.lower().lstrip(".")
            if fmt not in formats_set:
                formats_set.append(fmt)

        fallback_jpg = find_matching_jpg(canonical_key, jpgs_by_group_dir.get(logical_dir, []))

        if best_file.suffix.lower() in RENDERABLE_EXTENSIONS:
            # Reuse <stem>.png when unique in this catalog; add short path hash only on collision
            stem_key = best_file.stem.lower()
            if stem_key in used_stems:
                rel_hash = hashlib.md5(
                    str(best_file.relative_to(cfg.root_dir)).encode("utf-8")
                ).hexdigest()[:6]
                png_name = f"{best_file.stem}_{rel_hash}.png"
            else:
                used_stems.add(stem_key)
                png_name = f"{best_file.stem}.png"

            image_file = cfg.images_dir / catalog_name / png_name
            needs_render = cfg.recreate_images or not image_file.exists()
        else:
            # pyembroidery 1.5.1 does not include a .vip reader; copy accompanying image into Catalog/images/ so Catalog is self-contained
            if fallback_jpg is None:
                log.warning(f"Skipping {best_file.name}: .vip design has no accompanying JPG/PNG in {logical_dir}")
                continue
            stem_key = best_file.stem.lower()
            ext_img = fallback_jpg.suffix.lower()
            if stem_key in used_stems:
                rel_hash = hashlib.md5(
                    str(best_file.relative_to(cfg.root_dir)).encode("utf-8")
                ).hexdigest()[:6]
                copied_name = f"{best_file.stem}_{rel_hash}{ext_img}"
            else:
                used_stems.add(stem_key)
                copied_name = f"{best_file.stem}{ext_img}"
            image_file = cfg.images_dir / catalog_name / copied_name
            if cfg.recreate_images or not image_file.exists():
                image_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fallback_jpg, image_file)
            needs_render = False

        # Format group filenames cleanly (include relative subfolder if variants span sibling size folders)
        group_labels: list[str] = []
        for gf in sorted(group_files, key=lambda p: p.name.lower()):
            if gf.parent == best_file.parent:
                group_labels.append(gf.name)
            else:
                group_labels.append(os.path.relpath(gf, best_file.parent).replace(os.sep, "/"))

        entry = DesignEntry(
            catalog_name=catalog_name,
            display_name=display_names[gkey],
            canonical_key=canonical_key,
            stitch_file=best_file,
            stitch_rel_path=to_url_relpath(best_file, cfg.catalog_dir),
            image_file=image_file,
            image_rel_path=to_url_relpath(image_file, cfg.catalog_dir),
            sizes=sizes_set,
            formats=formats_set,
            group_filenames=group_labels,
            fallback_jpg=fallback_jpg,
            needs_render=needs_render,
        )
        entries.append(entry)

        if len(entries) >= cfg.max_files:
            log.info(
                f"Reached max_files limit ({cfg.max_files:,} unique designs from "
                f"{scanned_files_count:,} stitch files)."
            )
            return entries

    log.info(
        f"Discovered {Fore.YELLOW}{len(entries):,}{Fore.RESET} unique designs "
        f"(deduplicated from {Fore.YELLOW}{scanned_files_count:,}{Fore.RESET} stitch files)."
    )
    return entries


def set_finder_comment(file_path: Path, comment_text: str) -> None:
    if OSXMetaData is None:
        return
    try:
        md = OSXMetaData(str(file_path.resolve()))
        md.kMDItemFinderComment = comment_text
    except Exception:
        # Finder comment metadata is best-effort and should not fail rendering
        pass


def render_thumbnail(task: tuple[str, str, str]) -> tuple[str, bool, str]:
    """
    Top-level worker function for ProcessPoolExecutor.
    Renders .vp3, .hus, or .vip files to PNG via pyembroidery.
    """
    infile_str, outfile_str, root_dir_str = task
    outfile = Path(outfile_str)
    try:
        pattern = pyembroidery.read(infile_str)
        if pattern is None or len(pattern.stitches) == 0:
            return (infile_str, False, "Empty or unreadable stitch pattern")

        outfile.parent.mkdir(parents=True, exist_ok=True)
        pyembroidery.write_png(pattern, outfile_str)

        rel_comment = infile_str.replace(root_dir_str, "", 1)
        set_finder_comment(outfile, rel_comment)
        return (infile_str, True, "")
    except Exception as exc:
        return (infile_str, False, str(exc))


def render_missing_thumbnails(
    entries: list[DesignEntry], cfg: AppConfig, log: logging.Logger
) -> list[DesignEntry]:
    tasks: list[tuple[str, str, str]] = []

    for entry in entries:
        if entry.needs_render and entry.image_file is not None:
            entry.image_file.parent.mkdir(parents=True, exist_ok=True)
            tasks.append((str(entry.stitch_file), str(entry.image_file), str(cfg.root_dir)))

    if not tasks:
        log.info("All thumbnails already exist; skipping PNG rendering.")
        return entries

    log.info(f"Rendering {Fore.YELLOW}{len(tasks):,}{Fore.RESET} thumbnails using multiprocessing...")
    failed_infiles: dict[str, str] = {}

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = [executor.submit(render_thumbnail, task) for task in tasks]
        with tqdm(total=len(futures), unit=" files", desc="Rendering PNGs") as pbar:
            for future in concurrent.futures.as_completed(futures):
                infile_str, success, err_msg = future.result()
                if not success:
                    failed_infiles[infile_str] = err_msg
                pbar.set_description(f"Rendered {Path(infile_str).stem[:30]}")
                pbar.update(1)

    if not failed_infiles:
        return entries

    kept_entries: list[DesignEntry] = []
    for entry in entries:
        infile_str = str(entry.stitch_file)
        if infile_str in failed_infiles:
            if entry.fallback_jpg and entry.fallback_jpg.is_file():
                entry.image_file = entry.fallback_jpg
                entry.image_rel_path = to_url_relpath(entry.fallback_jpg, cfg.catalog_dir)
                log.warning(
                    f"Render failed for {entry.stitch_file.name} ({failed_infiles[infile_str]}); "
                    f"using fallback image {entry.fallback_jpg.name}"
                )
                kept_entries.append(entry)
            else:
                log.error(
                    f"Skipping {entry.stitch_file}: render failed ({failed_infiles[infile_str]}) "
                    "and no fallback image found."
                )
        else:
            kept_entries.append(entry)

    return kept_entries


def create_catalog_html(entries: list[DesignEntry], cfg: AppConfig, log: logging.Logger) -> None:
    log.info(f"Creating HTML catalog from {Fore.YELLOW}{len(entries):,}{Fore.RESET} designs...")

    by_catalog: dict[str, list[DesignEntry]] = {}
    for entry in entries:
        by_catalog.setdefault(entry.catalog_name, []).append(entry)

    sorted_catalogs = sorted(by_catalog.items(), key=lambda kv: kv[0].lower())
    total_designs = len(entries)

    parts: list[str] = [
        f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kurt's Embroidery Image Finder</title>
    <link rel="icon" type="image/svg+xml" href="images/K+N_favicon.svg">
    <style>
        :root {{
            --grid-cols: {cfg.table_cols};
            --accent: #2b6cb0;
            --accent-bg: #e6f0fa;
            --border: #d8e2ec;
            --card-bg: #ffffff;
            --page-bg: #f7f9fc;
            --text: #1f2933;
            --muted: #52606d;
        }}
        * {{ box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body {{
            margin: 0;
            padding: 16px 24px 64px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Verdana, sans-serif;
            background: var(--page-bg);
            color: var(--text);
        }}
        .sticky-bar {{
            position: sticky;
            top: 0;
            z-index: 50;
            background: var(--page-bg);
            padding: 12px 0;
            border-bottom: 1px solid var(--border);
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
        }}
        #imageSearchInput {{
            flex: 1 1 280px;
            padding: 10px 14px;
            font-size: 15px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: #fff;
        }}
        #matchCount {{
            font-size: 14px;
            color: var(--muted);
            white-space: nowrap;
        }}
        .toc {{
            margin: 18px 0 28px;
            padding: 16px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
        }}
        .toc h2 {{
            margin: 0 0 12px;
            font-size: 16px;
            color: var(--accent);
        }}
        .toc-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
            gap: 8px;
        }}
        .toc-link {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 10px;
            background: var(--accent-bg);
            color: var(--text);
            text-decoration: none;
            border-radius: 6px;
            font-size: 13px;
        }}
        .toc-link:hover {{
            background: #cfe2f7;
        }}
        .toc-count {{
            font-weight: 600;
            color: var(--accent);
            margin-left: 8px;
        }}
        .catalog-section {{
            margin-bottom: 32px;
            scroll-margin-top: 76px;
        }}
        .catalog-header {{
            background: powderblue;
            padding: 10px 16px;
            border-radius: 8px;
            margin: 0 0 14px;
            font-size: 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .catalog-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
            gap: 14px;
        }}
        @media (min-width: 1200px) {{
            .catalog-grid {{
                grid-template-columns: repeat(var(--grid-cols), minmax(0, 1fr));
            }}
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            transition: box-shadow 0.15s ease;
        }}
        .card:hover {{
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }}
        .thumb-btn {{
            width: 100%;
            height: 150px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 8px;
            padding: 0;
            border: none;
            background: transparent;
            cursor: zoom-in;
        }}
        .thumb-btn img {{
            max-width: 100%;
            max-height: 100%;
            width: auto;
            height: auto;
            object-fit: contain;
            display: block;
        }}
        .card-title {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text);
            word-break: break-word;
            margin-bottom: 4px;
        }}
        .badges {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            justify-content: center;
            margin: 4px 0 6px;
        }}
        .badge {{
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 999px;
            background: #eef2f6;
            color: var(--muted);
        }}
        .badge-fmt {{
            background: #e6f4ea;
            color: #1e6b3a;
            text-transform: uppercase;
            font-weight: 600;
        }}
        .path-toggle {{
            background: none;
            border: 1px solid var(--border);
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            padding: 3px 8px;
            color: var(--muted);
            margin-top: auto;
        }}
        .path-toggle:hover {{
            background: #f1f5f9;
        }}
        .path-box {{
            display: none;
            width: 100%;
            margin-top: 8px;
            padding: 8px;
            font-size: 11px;
            text-align: left;
            word-break: break-all;
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text);
        }}
        .path-box.open {{
            display: block;
        }}
        .dir-tree {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 11px;
            line-height: 1.55;
            text-align: left;
            white-space: nowrap;
            overflow-x: auto;
            padding: 2px 0;
        }}
        .tree-node {{
            display: flex;
            align-items: baseline;
            gap: 4px;
        }}
        .tree-branch {{
            color: #9aa5b1;
            user-select: none;
        }}
        .tree-folder {{
            font-weight: 600;
            color: #2b6cb0;
        }}
        .tree-file {{
            color: var(--text);
        }}
        .tree-file.is-primary {{
            font-weight: 700;
            color: #1e6b3a;
        }}
        .path-copy-btn {{
            margin-top: 6px;
            padding: 3px 8px;
            font-size: 11px;
            border: 1px solid var(--border);
            border-radius: 5px;
            background: #fff;
            color: var(--muted);
            cursor: pointer;
        }}
        .path-copy-btn:hover {{
            background: #eef2f6;
        }}
        #scrollToTopBtn {{
            display: none;
            position: fixed;
            bottom: 24px;
            right: 28px;
            z-index: 99;
            border: none;
            background: #d64545;
            color: #fff;
            cursor: pointer;
            padding: 12px 16px;
            border-radius: 10px;
            font-size: 15px;
            box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2);
        }}
        #scrollToTopBtn:hover {{
            background: #555;
        }}
        .lightbox-overlay {{
            display: none;
            position: fixed;
            inset: 0;
            z-index: 1000;
            background: rgba(15, 23, 42, 0.78);
            align-items: center;
            justify-content: center;
            padding: 24px;
        }}
        .lightbox-overlay.open {{
            display: flex;
        }}
        .lightbox-dialog {{
            position: relative;
            background: #ffffff;
            border-radius: 12px;
            max-width: min(92vw, 900px);
            max-height: 92vh;
            width: auto;
            padding: 20px 24px 18px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            overflow: auto;
        }}
        .lightbox-close {{
            position: absolute;
            top: 10px;
            right: 12px;
            border: none;
            background: #eef2f6;
            color: var(--text);
            font-size: 22px;
            line-height: 1;
            width: 34px;
            height: 34px;
            border-radius: 50%;
            cursor: pointer;
        }}
        .lightbox-close:hover {{
            background: #dce3ec;
        }}
        .lightbox-img {{
            max-width: 82vw;
            max-height: 68vh;
            width: auto;
            height: auto;
            object-fit: contain;
            display: block;
            border-radius: 6px;
            background: #f8fafc;
        }}
        .lightbox-title {{
            margin: 4px 0 0;
            font-size: 17px;
            font-weight: 600;
            color: var(--text);
            text-align: center;
        }}
        .lightbox-path {{
            font-size: 12px;
            color: var(--muted);
            word-break: break-all;
            text-align: center;
            background: #f8fafc;
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid var(--border);
            max-width: 100%;
        }}
        .lightbox-nav {{
            display: flex;
            gap: 10px;
            align-items: center;
            margin-top: 2px;
        }}
        .lightbox-nav button {{
            border: 1px solid var(--border);
            background: #fff;
            color: var(--text);
            border-radius: 6px;
            padding: 5px 12px;
            font-size: 13px;
            cursor: pointer;
        }}
        .lightbox-nav button:hover {{
            background: #f1f5f9;
        }}
        #menuToggleBtn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 9px 14px;
            font-size: 14px;
            font-weight: 600;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--card-bg);
            color: var(--accent);
            cursor: pointer;
            white-space: nowrap;
        }}
        #menuToggleBtn:hover {{
            background: var(--accent-bg);
        }}
        .side-nav-backdrop {{
            display: none;
            position: fixed;
            inset: 0;
            z-index: 900;
            background: rgba(15, 23, 42, 0.45);
        }}
        .side-nav-backdrop.open {{
            display: block;
        }}
        .side-nav {{
            position: fixed;
            top: 0;
            left: 0;
            bottom: 0;
            width: min(310px, 85vw);
            z-index: 950;
            background: var(--card-bg);
            border-right: 1px solid var(--border);
            box-shadow: 4px 0 24px rgba(0, 0, 0, 0.16);
            display: flex;
            flex-direction: column;
            transform: translateX(-100%);
            transition: transform 0.22s ease;
        }}
        .side-nav.open {{
            transform: translateX(0);
        }}
        .side-nav-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 16px;
            border-bottom: 1px solid var(--border);
            background: var(--page-bg);
        }}
        .side-nav-header h2 {{
            margin: 0;
            font-size: 16px;
            color: var(--accent);
        }}
        .side-nav-close {{
            border: none;
            background: #eef2f6;
            color: var(--text);
            font-size: 20px;
            line-height: 1;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            cursor: pointer;
        }}
        .side-nav-close:hover {{
            background: #dce3ec;
        }}
        .side-nav-search {{
            padding: 10px 14px;
            border-bottom: 1px solid var(--border);
        }}
        #sideNavFilter {{
            width: 100%;
            padding: 7px 10px;
            font-size: 13px;
            border: 1px solid var(--border);
            border-radius: 6px;
        }}
        .side-nav-list {{
            flex: 1;
            overflow-y: auto;
            padding: 10px 12px 24px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .side-nav-link {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 7px 10px;
            border-radius: 6px;
            text-decoration: none;
            color: var(--text);
            font-size: 13px;
        }}
        .side-nav-link:hover {{
            background: var(--accent-bg);
            color: var(--accent);
        }}
        .side-nav-top-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            width: calc(100% - 24px);
            margin: 10px 12px 4px;
            padding: 8px 10px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--accent-bg);
            color: var(--accent);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }}
        .side-nav-top-btn:hover {{
            background: #cfe2f7;
        }}
    </style>
</head>
<body>
    <div id="sideNavBackdrop" class="side-nav-backdrop"></div>
    <aside id="sideNav" class="side-nav" aria-label="Folder navigation">
        <div class="side-nav-header">
            <h2>Folders ({len(sorted_catalogs):,})</h2>
            <button type="button" id="sideNavClose" class="side-nav-close" aria-label="Close menu">&times;</button>
        </div>
        <div class="side-nav-search">
            <input type="search" id="sideNavFilter" placeholder="Filter folders..." autocomplete="off">
        </div>
        <button type="button" id="sideNavTopBtn" class="side-nav-top-btn">&uarr; Top</button>
        <div id="sideNavList" class="side-nav-list">
"""
    ]

    for catalog_name, group in sorted_catalogs:
        anchor_id = f"cat-{hashlib.md5(catalog_name.encode('utf-8')).hexdigest()[:8]}"
        escaped_name = html.escape(catalog_name)
        parts.append(
            f'            <a class="side-nav-link" href="#{anchor_id}" data-folder="{html.escape(catalog_name.lower())}">'
            f'<span>{escaped_name}</span><span class="toc-count">{len(group):,}</span></a>\n'
        )

    parts.append(
        f"""        </div>
    </aside>

    <button id="scrollToTopBtn" title="Go to top">Top</button>
    <div class="sticky-bar">
        <button type="button" id="menuToggleBtn" aria-controls="sideNav" aria-expanded="false">&#9776; Folders</button>
        <input type="search" id="imageSearchInput" placeholder="Search designs, folders, formats, or sizes..." autocomplete="off">
        <span id="matchCount">Showing {total_designs:,} of {total_designs:,} designs</span>
    </div>

    <nav class="toc" aria-label="Category links">
        <h2>Embroidery Category Folder Links ({total_designs:,} designs)</h2>
        <div class="toc-grid">
"""
    )

    for catalog_name, group in sorted_catalogs:
        anchor_id = f"cat-{hashlib.md5(catalog_name.encode('utf-8')).hexdigest()[:8]}"
        escaped_name = html.escape(catalog_name)
        parts.append(
            f'            <a class="toc-link" href="#{anchor_id}">'
            f'<span>{escaped_name}</span><span class="toc-count">{len(group):,}</span></a>\n'
        )

    parts.append('        </div>\n    </nav>\n\n    <main id="catalogMain">\n')

    box_index = 0
    for catalog_name, group in sorted_catalogs:
        anchor_id = f"cat-{hashlib.md5(catalog_name.encode('utf-8')).hexdigest()[:8]}"
        escaped_cat = html.escape(catalog_name)
        parts.append(
            f'        <section class="catalog-section" id="{anchor_id}" data-category="{html.escape(catalog_name.lower())}">\n'
            f'            <h2 class="catalog-header"><span>{escaped_cat}</span>'
            f'<span class="section-count">{len(group):,}</span></h2>\n'
            f'            <div class="catalog-grid">\n'
        )

        for entry in sorted(group, key=lambda e: e.display_name.lower()):
            escaped_title = html.escape(entry.display_name)
            rel_display = html.escape(
                os.path.relpath(entry.stitch_file, cfg.root_dir)
            )
            search_blob = html.escape(
                " ".join(
                    [
                        entry.display_name,
                        entry.catalog_name,
                        entry.stitch_file.name,
                        " ".join(entry.sizes),
                        " ".join(entry.formats),
                    ]
                ).lower()
            )
            badges_html = "".join(
                f'<span class="badge badge-fmt">{html.escape(fmt)}</span>'
                for fmt in entry.formats
            ) + "".join(
                f'<span class="badge">{html.escape(sz)}</span>'
                for sz in entry.sizes
            )

            files_json = html.escape(json.dumps(entry.group_filenames))
            parts.append(
                f'                <article class="card" data-search="{search_blob}" '
                f'data-img="{entry.image_rel_path}" data-title="{escaped_title}" '
                f'data-path="{rel_display}" data-files="{files_json}">\n'
                f'                    <button type="button" class="thumb-btn" aria-label="Preview {escaped_title}">\n'
                f'                        <img loading="lazy" src="{entry.image_rel_path}" alt="{escaped_title}">\n'
                f'                    </button>\n'
                f'                    <div class="card-title">{escaped_title}</div>\n'
                f'                    <div class="badges">{badges_html}</div>\n'
                f'                    <button type="button" class="path-toggle" data-target="box{box_index}">&#128194; Path</button>\n'
                f'                    <div id="box{box_index}" class="path-box"></div>\n'
                f'                </article>\n'
            )
            box_index += 1

        parts.append("            </div>\n        </section>\n")

    parts.append(
        f"""    </main>
    <div id="lightbox" class="lightbox-overlay" role="dialog" aria-modal="true" aria-labelledby="lightboxTitle">
        <div class="lightbox-dialog">
            <button type="button" class="lightbox-close" id="lightboxClose" aria-label="Close">&times;</button>
            <img id="lightboxImg" class="lightbox-img" src="" alt="">
            <h3 id="lightboxTitle" class="lightbox-title"></h3>
            <div id="lightboxBadges" class="badges"></div>
            <div id="lightboxPath" class="lightbox-path"></div>
            <div class="lightbox-nav">
                <button type="button" id="lightboxPrev">&larr; Prev</button>
                <button type="button" id="lightboxCopy">Copy Path</button>
                <button type="button" id="lightboxNext">Next &rarr;</button>
            </div>
        </div>
    </div>
    <script>
        const rootFolderName = {json.dumps(cfg.root_dir.name)};
        const searchInput = document.getElementById("imageSearchInput");
        const matchCount = document.getElementById("matchCount");
        const sections = Array.from(document.querySelectorAll(".catalog-section"));
        const totalDesigns = {total_designs};
        let debounceTimer = null;

        function buildDirectoryTreeElement(card, includeCopyBtn) {{
            const relPath = card.dataset.path || "";
            const segments = relPath.split("/").filter(Boolean);
            const primaryFile = segments.length ? segments[segments.length - 1] : "";
            const folderSegments = segments.slice(0, -1);
            let groupFiles = [];
            try {{ groupFiles = JSON.parse(card.dataset.files || "[]"); }} catch (e) {{}}
            if (!groupFiles.length && primaryFile) groupFiles = [primaryFile];

            const wrapper = document.createElement("div");
            const tree = document.createElement("div");
            tree.className = "dir-tree";

            const addRow = (depth, branch, icon, label, cls) => {{
                const row = document.createElement("div");
                row.className = "tree-node";
                row.style.paddingLeft = `${{depth * 14}}px`;
                if (branch) {{
                    const b = document.createElement("span");
                    b.className = "tree-branch";
                    b.textContent = branch;
                    row.appendChild(b);
                }}
                const txt = document.createElement("span");
                txt.className = cls;
                txt.textContent = `${{icon}} ${{label}}`;
                row.appendChild(txt);
                tree.appendChild(row);
            }};

            addRow(0, "", "\\u{{1F4C1}}", rootFolderName, "tree-folder");
            folderSegments.forEach((folder, idx) => {{
                addRow(idx + 1, "\\u2514\\u2500", "\\u{{1F4C2}}", folder, "tree-folder");
            }});
            const fileDepth = folderSegments.length + 1;
            groupFiles.forEach((fname, idx) => {{
                const connector = idx === groupFiles.length - 1 ? "\\u2514\\u2500" : "\\u251C\\u2500";
                const isPrimary = fname === primaryFile;
                addRow(fileDepth, connector, "\\u{{1F9F5}}", fname, isPrimary ? "tree-file is-primary" : "tree-file");
            }});
            wrapper.appendChild(tree);

            if (includeCopyBtn) {{
                const copyBtn = document.createElement("button");
                copyBtn.type = "button";
                copyBtn.className = "path-copy-btn";
                copyBtn.textContent = "Copy Folder Path";
                copyBtn.dataset.copyPath = folderSegments.length
                    ? `${{rootFolderName}}/${{folderSegments.join("/")}}`
                    : rootFolderName;
                wrapper.appendChild(copyBtn);
            }}
            return wrapper;
        }}

        function copyTextWithFeedback(text, buttonEl, defaultLabel) {{
            if (!navigator.clipboard || !navigator.clipboard.writeText) return;
            navigator.clipboard.writeText(text).then(() => {{
                buttonEl.textContent = "Copied!";
                setTimeout(() => {{ buttonEl.textContent = defaultLabel; }}, 1500);
            }});
        }}

        function filterCards() {{
            const terms = searchInput.value.trim().toLowerCase().split(/\\s+/).filter(Boolean);
            let visibleTotal = 0;

            for (const section of sections) {{
                const cards = section.querySelectorAll(".card");
                let visibleInSection = 0;

                for (const card of cards) {{
                    const haystack = card.dataset.search || "";
                    const matched = terms.every(term => haystack.includes(term));
                    card.style.display = matched ? "" : "none";
                    if (matched) visibleInSection++;
                }}

                section.style.display = visibleInSection > 0 ? "" : "none";
                const countEl = section.querySelector(".section-count");
                if (countEl) countEl.textContent = visibleInSection.toLocaleString();
                visibleTotal += visibleInSection;
            }}

            matchCount.textContent = `Showing ${{visibleTotal.toLocaleString()}} of ${{totalDesigns.toLocaleString()}} designs`;
        }}

        searchInput.addEventListener("input", () => {{
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(filterCards, 150);
        }});

        const lightbox = document.getElementById("lightbox");
        const lightboxImg = document.getElementById("lightboxImg");
        const lightboxTitle = document.getElementById("lightboxTitle");
        const lightboxBadges = document.getElementById("lightboxBadges");
        const lightboxPath = document.getElementById("lightboxPath");
        const lightboxCopy = document.getElementById("lightboxCopy");
        let activeCard = null;

        function getVisibleCards() {{
            return Array.from(document.querySelectorAll(".card")).filter(
                c => c.style.display !== "none" && c.closest(".catalog-section").style.display !== "none"
            );
        }}

        function openLightbox(card) {{
            activeCard = card;
            lightboxImg.src = card.dataset.img || "";
            lightboxImg.alt = card.dataset.title || "";
            lightboxTitle.textContent = card.dataset.title || "";
            lightboxPath.innerHTML = "";
            lightboxPath.appendChild(buildDirectoryTreeElement(card, false));
            const badgesEl = card.querySelector(".badges");
            lightboxBadges.innerHTML = badgesEl ? badgesEl.innerHTML : "";
            lightboxCopy.textContent = "Copy Path";
            lightbox.classList.add("open");
            document.body.style.overflow = "hidden";
        }}

        function closeLightbox() {{
            lightbox.classList.remove("open");
            document.body.style.overflow = "";
            activeCard = null;
        }}

        function stepLightbox(delta) {{
            if (!activeCard) return;
            const visible = getVisibleCards();
            const idx = visible.indexOf(activeCard);
            if (idx === -1 || visible.length <= 1) return;
            const nextIdx = (idx + delta + visible.length) % visible.length;
            openLightbox(visible[nextIdx]);
        }}

        document.getElementById("catalogMain").addEventListener("click", (event) => {{
            const thumbBtn = event.target.closest(".thumb-btn");
            if (thumbBtn) {{
                const card = thumbBtn.closest(".card");
                if (card) openLightbox(card);
                return;
            }}
            const copyBtn = event.target.closest(".path-copy-btn");
            if (copyBtn) {{
                copyTextWithFeedback(copyBtn.dataset.copyPath || "", copyBtn, "Copy Folder Path");
                return;
            }}
            const btn = event.target.closest(".path-toggle");
            if (!btn) return;
            const box = document.getElementById(btn.dataset.target);
            if (!box) return;
            const card = btn.closest(".card");
            if (card && !box.dataset.rendered) {{
                box.appendChild(buildDirectoryTreeElement(card, true));
                box.dataset.rendered = "1";
            }}
            const isOpen = box.classList.toggle("open");
            btn.textContent = isOpen ? "Hide Path" : "\\u{{1F4C2}} Path";
        }});

        document.getElementById("lightboxClose").addEventListener("click", closeLightbox);
        document.getElementById("lightboxPrev").addEventListener("click", () => stepLightbox(-1));
        document.getElementById("lightboxNext").addEventListener("click", () => stepLightbox(1));
        lightboxCopy.addEventListener("click", () => {{
            if (!activeCard) return;
            copyTextWithFeedback(activeCard.dataset.path || "", lightboxCopy, "Copy Path");
        }});
        lightbox.addEventListener("click", (event) => {{
            if (event.target === lightbox) closeLightbox();
        }});
        const sideNav = document.getElementById("sideNav");
        const sideNavBackdrop = document.getElementById("sideNavBackdrop");
        const menuToggleBtn = document.getElementById("menuToggleBtn");
        const sideNavFilter = document.getElementById("sideNavFilter");
        const sideNavLinks = Array.from(document.querySelectorAll(".side-nav-link"));

        function openSideNav() {{
            sideNav.classList.add("open");
            sideNavBackdrop.classList.add("open");
            menuToggleBtn.setAttribute("aria-expanded", "true");
        }}

        function closeSideNav() {{
            sideNav.classList.remove("open");
            sideNavBackdrop.classList.remove("open");
            menuToggleBtn.setAttribute("aria-expanded", "false");
        }}

        menuToggleBtn.addEventListener("click", () => {{
            if (sideNav.classList.contains("open")) closeSideNav();
            else openSideNav();
        }});
        document.getElementById("sideNavClose").addEventListener("click", closeSideNav);
        document.getElementById("sideNavTopBtn").addEventListener("click", () => {{
            closeSideNav();
            window.scrollTo({{ top: 0, behavior: "smooth" }});
        }});
        sideNavBackdrop.addEventListener("click", closeSideNav);
        document.getElementById("sideNavList").addEventListener("click", (event) => {{
            if (event.target.closest(".side-nav-link")) closeSideNav();
        }});
        sideNavFilter.addEventListener("input", () => {{
            const q = sideNavFilter.value.trim().toLowerCase();
            for (const link of sideNavLinks) {{
                link.style.display = (link.dataset.folder || "").includes(q) ? "" : "none";
            }}
        }});

        document.addEventListener("keydown", (event) => {{
            if (event.key === "Escape") {{
                if (lightbox.classList.contains("open")) closeLightbox();
                else if (sideNav.classList.contains("open")) closeSideNav();
                return;
            }}
            if (!lightbox.classList.contains("open")) return;
            if (event.key === "ArrowLeft") stepLightbox(-1);
            else if (event.key === "ArrowRight") stepLightbox(1);
        }});

        const scrollToTopBtn = document.getElementById("scrollToTopBtn");
        window.addEventListener("scroll", () => {{
            scrollToTopBtn.style.display = window.scrollY > 300 ? "block" : "none";
        }});
        scrollToTopBtn.addEventListener("click", () => {{
            window.scrollTo({{ top: 0, behavior: "smooth" }});
        }});
    </script>
</body>
</html>
"""
    )

    cfg.html_file.write_text("".join(parts), encoding="utf-8")
    log.info(f"HTML catalog saved to {Fore.YELLOW}{cfg.html_file}")
    webbrowser.open_new_tab(cfg.html_file.resolve().as_uri())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an HTML catalog of embroidery stitch files.")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--recreate-images",
        action="store_true",
        help="Force re-rendering of all PNG thumbnails even if cached images already exist.",
    )
    parser.add_argument(
        "--clean-images",
        action="store_true",
        help="Delete all folders and files in Catalog/images/ except K+N_favicon.svg before generating thumbnails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    colorama_init(autoreset=True)
    script_dir = Path(__file__).resolve().parent
    log = setup_logger()
    cfg = load_config(script_dir, log)
    if args.recreate_images:
        cfg.recreate_images = True
    if args.clean_images:
        cfg.clean_images = True
    log.setLevel(cfg.log_level)

    log.info(f"{Fore.GREEN}Embroidery Stitch File Catalog v{__version__}")
    log.info(f"Logging level set to {Fore.YELLOW}{logging.getLevelName(cfg.log_level)}")
    log.info(f"Excluded folders: {Fore.YELLOW}{cfg.excluded_folders}")
    if cfg.recreate_images:
        log.info(f"{Fore.YELLOW}recreate_images enabled: all renderable thumbnails will be regenerated.")

    ensure_directories_and_favicon(cfg, script_dir, log)
    if cfg.clean_images:
        clean_images_folder(cfg, log)
    entries = scan_embroidery_designs(cfg, log)
    if not entries:
        log.warning("No matching embroidery files (.vp3, .hus, .vip) were found.")
        return

    entries = render_missing_thumbnails(entries, cfg, log)
    create_catalog_html(entries, cfg, log)
    log.info(f"{Fore.GREEN}Image catalog generation complete.{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
