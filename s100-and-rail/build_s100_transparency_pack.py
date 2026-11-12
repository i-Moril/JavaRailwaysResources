#!/usr/bin/env python3
"""Build S100 resource packs with a Minecraft 26.2-only transparency overlay.

The base assets stay byte-for-byte compatible with Minecraft 1.21.11. The optimized
pack adds a pack-format 88 overlay that splits mixed solid/translucent item models
into separate minecraft:composite layers. The source pack is never modified.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import struct
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "s100-and-rail" / "resourcepack"
DEFAULT_CONTROL = ROOT / "s100-and-rail" / "distributions" / "resourcepack-control-1.21.11-26.2.zip"
DEFAULT_OPTIMIZED = ROOT / "s100-and-rail" / "distributions" / "resourcepack-s100-transparency-1.21.11-26.2.zip"

MODEL_DIR = PurePosixPath("assets/minecraft/models/item/art1st/tc/s100")
ITEM_DIR = PurePosixPath("assets/minecraft/items/art1st/tc/s100")
TEXTURE_DIR = PurePosixPath("assets/minecraft/textures")
OVERLAY_DIR = PurePosixPath("overlay_26_2")

TARGET_MODELS = {
    "body_connector": "glass",
    "body_head": "glass",
    "body_head_overlay": "translucent",
    "body_seated": "glass",
    "door_a": "glass",
    "door_b": "glass",
    "door_cab_a": "glass",
    "door_cab_b": "glass",
}

FLAT_LIGHT_MODELS = {
    "body_connector",
    "body_connector_toilet",
    "body_head",
    "body_head_overlay",
    "body_seated",
}
FLAT_LIGHT_TINT = {"type": "minecraft:constant", "value": 0xFEFFFF}

# Five-car default S100 consist. These weights keep the optimization auditable.
MODEL_WEIGHTS = {
    "air_conditioner": 5,
    "body_connector": 6,
    "body_connector_toilet": 2,
    "body_head": 2,
    "body_head_overlay": 2,
    "body_overlay": 28,
    "body_seated": 20,
    "bogie": 10,
    "bottom_devices_a": 4,
    "bottom_devices_b": 6,
    "bottom_devices_c": 4,
    "cabin_light": 20,
    "cabin_light_connector": 6,
    "cabin_light_connector_toilet": 2,
    "cabin_light_head": 2,
    "connector_front": 2,
    "connector_mid_a": 8,
    "door_a": 30,
    "door_b": 30,
    "left_door_light": 30,
    "door_cab_a": 2,
    "door_cab_b": 2,
    "door_display": 15,
    "head_light": 1,
    "tail_light": 1,
    "pantograph": 2,
    "pantograph_retrieved": 2,
    "side_display": 10,
    "wheel": 20,
}

EXPECTED_BASE = {
    "item_displays": 274,
    "quads": 16_158,
    "translucent_quads": 502,
    "mixed_submits": 94,
}
EXPECTED_OPTIMIZED = {
    "item_displays": 274,
    "quads": 15_902,
    "translucent_quads": 246,
    "mixed_submits": 0,
}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PngAlpha:
    width: int
    height: int
    rows: tuple[tuple[int, ...], ...]

    @classmethod
    def read(cls, path: Path) -> "PngAlpha":
        data = path.read_bytes()
        if not data.startswith(PNG_SIGNATURE):
            raise ValueError(f"not a PNG: {path}")

        offset = len(PNG_SIGNATURE)
        idat: list[bytes] = []
        width = height = bit_depth = color_type = interlace = -1
        while offset < len(data):
            length = int.from_bytes(data[offset : offset + 4], "big")
            chunk_type = data[offset + 4 : offset + 8]
            chunk = data[offset + 8 : offset + 8 + length]
            offset += length + 12
            if chunk_type == b"IHDR":
                width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                    ">IIBBBBB", chunk
                )
                if compression != 0 or filtering != 0:
                    raise ValueError(f"unsupported PNG compression/filter method: {path}")
            elif chunk_type == b"IDAT":
                idat.append(chunk)
            elif chunk_type == b"IEND":
                break

        if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
            raise ValueError(
                f"unsupported PNG layout in {path}: depth={bit_depth}, type={color_type}, interlace={interlace}"
            )

        channels = 3 if color_type == 2 else 4
        stride = width * channels
        raw = zlib.decompress(b"".join(idat))
        expected_size = height * (stride + 1)
        if len(raw) != expected_size:
            raise ValueError(f"unexpected decompressed PNG size in {path}: {len(raw)} != {expected_size}")

        previous = bytearray(stride)
        rows: list[tuple[int, ...]] = []
        cursor = 0
        for _ in range(height):
            filter_type = raw[cursor]
            cursor += 1
            row = bytearray(raw[cursor : cursor + stride])
            cursor += stride
            cls._unfilter(row, previous, channels, filter_type, path)
            if color_type == 2:
                rows.append(tuple(255 for _ in range(width)))
            else:
                rows.append(tuple(row[3::4]))
            previous = row
        return cls(width, height, tuple(rows))

    @staticmethod
    def _unfilter(row: bytearray, previous: bytearray, channels: int, filter_type: int, path: Path) -> None:
        def paeth(left: int, above: int, upper_left: int) -> int:
            estimate = left + above - upper_left
            distances = (abs(estimate - left), abs(estimate - above), abs(estimate - upper_left))
            return (left, above, upper_left)[distances.index(min(distances))]

        if filter_type == 0:
            return
        for index in range(len(row)):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = paeth(left, above, upper_left)
            else:
                raise ValueError(f"unsupported PNG filter {filter_type} in {path}")
            row[index] = (row[index] + predictor) & 0xFF

    def has_partial_alpha(self, uv: list[float]) -> bool:
        min_u, max_u = sorted((float(uv[0]), float(uv[2])))
        min_v, max_v = sorted((float(uv[1]), float(uv[3])))
        x0 = math.floor(min_u * self.width / 16.0)
        x1 = math.ceil(max_u * self.width / 16.0)
        y0 = math.floor(min_v * self.height / 16.0)
        y1 = math.ceil(max_v * self.height / 16.0)
        if not (0 <= x0 <= x1 <= self.width and 0 <= y0 <= y1 <= self.height):
            raise ValueError(f"UV region {uv} falls outside {self.width}x{self.height} texture")
        return any(0 < self.rows[y][x] < 255 for y in range(y0, y1) for x in range(x0, x1))


@dataclass(frozen=True)
class ModelSplit:
    solid: dict[str, Any]
    translucent: dict[str, Any]
    original_quads: int
    solid_quads: int
    translucent_quads: int
    removed_degenerate_quads: int


class TransparencyAnalyzer:
    def __init__(self, source: Path):
        self.source = source
        self._png_cache: dict[Path, PngAlpha] = {}

    def read_model(self, name: str) -> dict[str, Any]:
        path = self.source / MODEL_DIR / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def resolve_texture(model: dict[str, Any], reference: str) -> str:
        seen: set[str] = set()
        value = reference
        while value.startswith("#"):
            key = value[1:]
            if key in seen:
                raise ValueError(f"cyclic texture reference: {reference}")
            seen.add(key)
            try:
                value = model["textures"][key]
            except KeyError as error:
                raise ValueError(f"missing texture key {value}") from error
        return value.removeprefix("minecraft:")

    def face_is_translucent(self, model: dict[str, Any], face: dict[str, Any]) -> bool:
        if "uv" not in face:
            raise ValueError("target S100 models must use explicit face UVs")
        texture = self.resolve_texture(model, face["texture"])
        path = self.source / TEXTURE_DIR / f"{texture}.png"
        png = self._png_cache.setdefault(path, PngAlpha.read(path))
        return png.has_partial_alpha(face["uv"])

    @staticmethod
    def face_area(element: dict[str, Any], direction: str) -> float:
        start = element["from"]
        end = element["to"]
        axes = {
            "north": (0, 1),
            "south": (0, 1),
            "east": (2, 1),
            "west": (2, 1),
            "up": (0, 2),
            "down": (0, 2),
        }
        first, second = axes[direction]
        return abs(float(end[first]) - float(start[first])) * abs(float(end[second]) - float(start[second]))

    def split(self, model: dict[str, Any]) -> ModelSplit:
        shell = {key: copy.deepcopy(value) for key, value in model.items() if key not in ("elements", "groups")}
        solid_elements: list[dict[str, Any]] = []
        translucent_elements: list[dict[str, Any]] = []
        original_quads = solid_quads = translucent_quads = removed_degenerate = 0

        for element in model.get("elements", []):
            solid_faces: dict[str, Any] = {}
            translucent_faces: dict[str, Any] = {}
            for direction, face in element.get("faces", {}).items():
                original_quads += 1
                if self.face_is_translucent(model, face):
                    if self.face_area(element, direction) <= 1.0e-9:
                        removed_degenerate += 1
                    else:
                        translucent_faces[direction] = copy.deepcopy(face)
                        translucent_quads += 1
                else:
                    solid_faces[direction] = copy.deepcopy(face)
                    solid_quads += 1

            if solid_faces:
                solid_element = copy.deepcopy(element)
                solid_element["faces"] = solid_faces
                solid_elements.append(solid_element)
            if translucent_faces:
                translucent_element = copy.deepcopy(element)
                translucent_element["faces"] = translucent_faces
                translucent_elements.append(translucent_element)

        solid = copy.deepcopy(shell)
        solid["elements"] = solid_elements
        translucent = copy.deepcopy(shell)
        translucent["elements"] = translucent_elements
        return ModelSplit(
            solid,
            translucent,
            original_quads,
            solid_quads,
            translucent_quads,
            removed_degenerate,
        )

    def model_counts(self, model: dict[str, Any]) -> tuple[int, int, bool]:
        total = translucent = 0
        for element in model.get("elements", []):
            for face in element.get("faces", {}).values():
                total += 1
                if self.face_is_translucent(model, face):
                    translucent += 1
        return total, translucent, translucent > 0 and translucent < total


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pack_metadata(optimized: bool) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "pack": {
            "min_format": 75,
            "max_format": 88,
            "description": "Series 100 train pack (Minecraft 1.21.11-26.2)",
        }
    }
    if optimized:
        metadata["overlays"] = {
            "entries": [
                {
                    "directory": str(OVERLAY_DIR),
                    "min_format": 88,
                    "max_format": 88,
                }
            ]
        }
    return metadata


def item_model_layer(model: str, flat_light: bool) -> dict[str, Any]:
    layer: dict[str, Any] = {"type": "minecraft:model", "model": model}
    if flat_light:
        layer["tints"] = [FLAT_LIGHT_TINT]
    return layer


def composite_item(name: str, translucent_suffix: str) -> dict[str, Any]:
    model_prefix = "minecraft:item/art1st/tc/s100"
    flat_light = name in FLAT_LIGHT_MODELS
    return {
        "model": {
            "type": "minecraft:composite",
            "models": [
                item_model_layer(f"{model_prefix}/{name}", flat_light),
                item_model_layer(f"{model_prefix}/{name}_{translucent_suffix}", flat_light),
            ],
        }
    }


def prepare_stage(source: Path, stage: Path, optimized: bool) -> dict[str, int]:
    shutil.copytree(source, stage, dirs_exist_ok=True)
    write_json(stage / "pack.mcmeta", pack_metadata(optimized))

    analyzer = TransparencyAnalyzer(source)
    base_quads = base_translucent = base_mixed = 0
    optimized_quads = optimized_translucent = 0
    split_by_name: dict[str, ModelSplit] = {}

    for name, weight in MODEL_WEIGHTS.items():
        model = analyzer.read_model(name)
        quads, translucent, mixed = analyzer.model_counts(model)
        base_quads += quads * weight
        base_translucent += translucent * weight
        if mixed:
            base_mixed += weight

        if name in TARGET_MODELS:
            split = analyzer.split(model)
            split_by_name[name] = split
            optimized_quads += (split.solid_quads + split.translucent_quads) * weight
            optimized_translucent += split.translucent_quads * weight
        else:
            optimized_quads += quads * weight
            optimized_translucent += translucent * weight

    stats = {
        "item_displays": sum(MODEL_WEIGHTS.values()),
        "base_quads": base_quads,
        "base_translucent_quads": base_translucent,
        "base_mixed_submits": base_mixed,
        "optimized_quads": optimized_quads,
        "optimized_translucent_quads": optimized_translucent,
        "optimized_mixed_submits": 0,
        "removed_degenerate_quads": base_quads - optimized_quads,
    }
    validate_stats(stats)

    if optimized:
        overlay = stage / OVERLAY_DIR
        for name, suffix in TARGET_MODELS.items():
            split = split_by_name[name]
            if split.solid_quads == 0 or split.translucent_quads == 0:
                raise ValueError(f"{name} did not split into two non-empty layers")
            write_json(overlay / MODEL_DIR / f"{name}.json", split.solid)
            write_json(overlay / MODEL_DIR / f"{name}_{suffix}.json", split.translucent)
            write_json(overlay / ITEM_DIR / f"{name}.json", composite_item(name, suffix))
        validate_overlay(stage, analyzer, split_by_name)

    return stats


def validate_stats(stats: dict[str, int]) -> None:
    actual_base = {
        "item_displays": stats["item_displays"],
        "quads": stats["base_quads"],
        "translucent_quads": stats["base_translucent_quads"],
        "mixed_submits": stats["base_mixed_submits"],
    }
    actual_optimized = {
        "item_displays": stats["item_displays"],
        "quads": stats["optimized_quads"],
        "translucent_quads": stats["optimized_translucent_quads"],
        "mixed_submits": stats["optimized_mixed_submits"],
    }
    if actual_base != EXPECTED_BASE:
        raise ValueError(f"unexpected base S100 metrics: {actual_base}; expected {EXPECTED_BASE}")
    if actual_optimized != EXPECTED_OPTIMIZED:
        raise ValueError(f"unexpected optimized S100 metrics: {actual_optimized}; expected {EXPECTED_OPTIMIZED}")


def validate_overlay(stage: Path, analyzer: TransparencyAnalyzer, splits: dict[str, ModelSplit]) -> None:
    overlay = stage / OVERLAY_DIR
    expected_files: set[PurePosixPath] = set()
    for name, suffix in TARGET_MODELS.items():
        expected_files.update(
            {
                MODEL_DIR / f"{name}.json",
                MODEL_DIR / f"{name}_{suffix}.json",
                ITEM_DIR / f"{name}.json",
            }
        )
        split = splits[name]
        solid_total, solid_translucent, solid_mixed = analyzer.model_counts(split.solid)
        translucent_total, translucent_count, translucent_mixed = analyzer.model_counts(split.translucent)
        if solid_translucent != 0 or solid_mixed:
            raise ValueError(f"{name} solid layer still contains translucent faces")
        if translucent_count != translucent_total or translucent_mixed:
            raise ValueError(f"{name} translucent layer contains non-translucent faces")
        if solid_total + translucent_total + split.removed_degenerate_quads != split.original_quads:
            raise ValueError(f"{name} split did not preserve every non-degenerate face exactly once")

    actual_files = {
        PurePosixPath(path.relative_to(overlay).as_posix())
        for path in overlay.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        missing = sorted(str(path) for path in expected_files - actual_files)
        extra = sorted(str(path) for path in actual_files - expected_files)
        raise ValueError(f"overlay file set mismatch; missing={missing}, extra={extra}")


def deterministic_zip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted((path for path in source.rglob("*") if path.is_file()), key=lambda p: p.as_posix()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    temporary.replace(destination)


def validate_zip(path: Path, optimized: bool) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate ZIP entries in {path}")
        if "pack.mcmeta" not in names or not any(name.startswith("assets/") for name in names):
            raise ValueError(f"invalid resource-pack root in {path}")
        has_overlay = any(name.startswith(f"{OVERLAY_DIR}/") for name in names)
        if has_overlay != optimized:
            raise ValueError(f"unexpected overlay presence in {path}: {has_overlay}")
        metadata = json.loads(archive.read("pack.mcmeta"))
        if metadata != pack_metadata(optimized):
            raise ValueError(f"unexpected pack.mcmeta in {path}")
        bad_json: list[str] = []
        for name in names:
            if name.endswith(".json") or name == "pack.mcmeta":
                try:
                    json.loads(archive.read(name))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    bad_json.append(name)
        if bad_json:
            raise ValueError(f"invalid JSON files in {path}: {bad_json}")


def digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def build(source: Path, control: Path, optimized: Path) -> dict[str, int]:
    if not (source / "pack.mcmeta").is_file() or not (source / "assets").is_dir():
        raise ValueError(f"resource-pack source is incomplete: {source}")

    with tempfile.TemporaryDirectory(prefix="s100-resourcepack-") as temporary:
        temporary_root = Path(temporary)
        control_stage = temporary_root / "control"
        optimized_stage = temporary_root / "optimized"
        control_stats = prepare_stage(source, control_stage, optimized=False)
        optimized_stats = prepare_stage(source, optimized_stage, optimized=True)
        if control_stats != optimized_stats:
            raise ValueError("control and optimized analysis stats differ")
        deterministic_zip(control_stage, control)
        deterministic_zip(optimized_stage, optimized)

    validate_zip(control, optimized=False)
    validate_zip(optimized, optimized=True)
    return control_stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--control", type=Path, default=DEFAULT_CONTROL)
    parser.add_argument("--optimized", type=Path, default=DEFAULT_OPTIMIZED)
    args = parser.parse_args()

    source = args.source.resolve()
    control = args.control.resolve()
    optimized = args.optimized.resolve()
    if control == optimized:
        parser.error("--control and --optimized must be different files")

    stats = build(source, control, optimized)
    print("S100 transparency analysis:")
    print(
        f"  ItemDisplays: {stats['item_displays']} -> {stats['item_displays']}\n"
        f"  total quads: {stats['base_quads']} -> {stats['optimized_quads']}\n"
        f"  translucent quads: {stats['base_translucent_quads']} -> {stats['optimized_translucent_quads']}\n"
        f"  mixed submits: {stats['base_mixed_submits']} -> {stats['optimized_mixed_submits']}\n"
        f"  removed zero-area quads: {stats['removed_degenerate_quads']}"
    )
    for label, path in (("control", control), ("optimized", optimized)):
        print(f"{label}: {path}")
        print(f"  bytes={path.stat().st_size} sha1={digest(path, 'sha1')} sha256={digest(path, 'sha256')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
