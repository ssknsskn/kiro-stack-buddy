"""ローカル画像からM5Stack用のRGB565 BMPを生成する。"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PIL import Image

DEFAULT_OUTPUT_DIR = Path("firmware/assets")
DEFAULT_SIZE = 96
DEFAULT_THRESHOLD = 128


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="ローカル画像を2値化し、左右のRGB565 BMPを生成します。"
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="利用者が用意した入力画像（PNG/JPGなど）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"生成先ディレクトリ（既定値: {DEFAULT_OUTPUT_DIR}）",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"2値化の閾値 0-255（既定値: {DEFAULT_THRESHOLD}）",
    )
    return parser.parse_args()


def write_rgb565_bmp(image: Image.Image, output_path: Path) -> None:
    """2値RGB画像を、firmwareが読む16-bit BMPとして保存する。"""
    width, height = image.size
    row_bytes = width * 2
    image_size = row_bytes * height
    pixel_offset = 54
    file_size = pixel_offset + image_size

    file_header = struct.pack(
        "<2sIHHI",
        b"BM",
        file_size,
        0,
        0,
        pixel_offset,
    )
    info_header = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        16,
        0,
        image_size,
        0,
        0,
        0,
        0,
    )

    with output_path.open("wb") as output:
        output.write(file_header)
        output.write(info_header)

        # BMPの画素データはbottom-upで保存する。
        for y in range(height - 1, -1, -1):
            row = bytearray(row_bytes)
            for x in range(width):
                pixel = image.getpixel((x, y))
                value = 0xFFFF if pixel[0] >= 128 else 0x0000
                struct.pack_into("<H", row, x * 2, value)
            output.write(row)


def prepare_image(input_path: Path, output_dir: Path, threshold: int) -> None:
    """入力画像から右向き・左向きの96x96 BMPを生成する。"""
    size = DEFAULT_SIZE
    if not input_path.is_file():
        raise FileNotFoundError(f"入力画像が見つかりません: {input_path}")
    if size <= 0:
        raise ValueError("--sizeは1以上で指定してください")
    if not 0 <= threshold <= 255:
        raise ValueError("--thresholdは0から255の範囲で指定してください")

    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as source:
        # 透明部分は白背景として合成し、画像形式に依存しないようにする。
        rgba = source.convert("RGBA")
        white_background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        composited = Image.alpha_composite(white_background, rgba).convert("L")
        resized = composited.resize((size, size), Image.Resampling.LANCZOS)
        binary = resized.point(
            lambda value: 0 if value < threshold else 255,
            mode="1",
        ).convert("RGB")

    right_path = output_dir / "kiro_bw_96x96.bmp"
    left_path = output_dir / "kiro_bw_96x96_left.bmp"
    write_rgb565_bmp(binary, right_path)
    write_rgb565_bmp(binary.transpose(Image.Transpose.FLIP_LEFT_RIGHT), left_path)

    print(f"生成完了: {right_path}")
    print(f"生成完了: {left_path}")
    print(f"サイズ: {size}x{size}, 閾値: {threshold}")


def main() -> None:
    """エントリポイント。"""
    args = parse_args()
    prepare_image(args.input, args.output_dir, args.threshold)


if __name__ == "__main__":
    main()
