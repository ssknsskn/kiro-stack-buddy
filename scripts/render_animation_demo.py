"""IDLEアニメーションをREADME用GIFとして生成する。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCREEN_SIZE = (320, 240)
IMAGE_SIZE = 96
IMAGE_Y = 30
IDLE_FRAMES = 12
FRAME_DURATION_MS = 100
STATUS_TEXT_SIZE = 24
FOOTER_TEXT_SIZE = 10

ROOT = Path(__file__).resolve().parent.parent
RIGHT_IMAGE = ROOT / "firmware/assets/kiro_bw_96x96.bmp"
LEFT_IMAGE = ROOT / "firmware/assets/kiro_bw_96x96_left.bmp"
OUTPUT = ROOT / "assets/idle-animation.gif"


def render_frame(
    right_image: Image.Image,
    left_image: Image.Image,
    frame: int,
) -> Image.Image:
    """ファームウェアの_idleと同じ画面を生成する。"""
    phase = frame % IDLE_FRAMES
    if phase < 6:
        x = 112 + phase * 2
        facing_left = False
    else:
        x = 122 - (phase - 6) * 2
        facing_left = True

    screen = Image.new("RGB", SCREEN_SIZE, (0, 0, 0))
    character = left_image if facing_left else right_image
    screen.paste(character, (x, IMAGE_Y))

    draw = ImageDraw.Draw(screen)
    status_font = ImageFont.load_default(size=STATUS_TEXT_SIZE)
    draw.text((10, 150), "IDLE", fill=(0, 255, 0), font=status_font)

    footer_font = ImageFont.load_default(size=FOOTER_TEXT_SIZE)
    draw.rectangle((0, 215, 319, 239), fill=(64, 64, 64))
    draw.text((10, 215), "BRIDGE CONNECTED", fill=(0, 255, 0), font=footer_font)
    draw.text((250, 215), "BLE: ON", fill=(0, 255, 0), font=footer_font)
    return screen


def main() -> None:
    """IDLEアニメーションGIFを生成する。"""
    with Image.open(RIGHT_IMAGE) as source:
        right_image = source.convert("RGB")
    with Image.open(LEFT_IMAGE) as source:
        left_image = source.convert("RGB")

    frames = [
        render_frame(right_image, left_image, frame)
        for frame in range(IDLE_FRAMES)
    ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        optimize=True,
    )
    print(f"生成完了: {OUTPUT}")
    print(
        f"フレーム数: {len(frames)}, サイズ: {SCREEN_SIZE}, "
        f"周期: {len(frames) * FRAME_DURATION_MS}ms"
    )


if __name__ == "__main__":
    main()
