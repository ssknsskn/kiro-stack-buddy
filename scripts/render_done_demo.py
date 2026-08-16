"""DONEアニメーションをREADME用GIFとして生成する。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCREEN_SIZE = (320, 240)
IMAGE_Y = 30
IMAGE_X = 112
IMAGE_SIZE = 96
DONE_FRAMES = 20
FRAME_DURATION_MS = 100
STATUS_TEXT_SIZE = 24
FOOTER_TEXT_SIZE = 10

ROOT = Path(__file__).resolve().parent.parent
RIGHT_IMAGE = ROOT / "firmware/assets/kiro_bw_96x96.bmp"
OUTPUT = ROOT / "assets/done-animation.gif"


def render_frame(right_image: Image.Image, frame: int) -> Image.Image:
    """ファームウェアの_animate_completedと同じ画面を生成する。"""
    phase = frame % 6
    if phase == 1:
        y = 24
    elif phase == 2:
        y = 22
    elif phase == 3:
        y = 24
    else:
        y = IMAGE_Y

    screen = Image.new("RGB", SCREEN_SIZE, (0, 0, 0))
    screen.paste(right_image, (IMAGE_X, y))

    draw = ImageDraw.Draw(screen)
    status_font = ImageFont.load_default(size=STATUS_TEXT_SIZE)
    draw.text((10, 150), "DONE", fill=(255, 0, 255), font=status_font)

    footer_font = ImageFont.load_default(size=FOOTER_TEXT_SIZE)
    draw.rectangle((0, 215, 319, 239), fill=(64, 64, 64))
    draw.text((10, 215), "BRIDGE CONNECTED", fill=(0, 255, 0), font=footer_font)
    draw.text((250, 215), "BLE: ON", fill=(0, 255, 0), font=footer_font)
    return screen


def main() -> None:
    """DONEアニメーションGIFを生成する。"""
    with Image.open(RIGHT_IMAGE) as source:
        right_image = source.convert("RGB")

    frames = [render_frame(right_image, frame) for frame in range(DONE_FRAMES)]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        optimize=False,
    )
    print(f"生成完了: {OUTPUT}")
    print(
        f"フレーム数: {len(frames)}, サイズ: {SCREEN_SIZE}, "
        f"表示時間: {len(frames) * FRAME_DURATION_MS}ms"
    )


if __name__ == "__main__":
    main()
