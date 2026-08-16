"""WORKINGアニメーションをREADME用GIFとして生成する。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCREEN_SIZE = (320, 240)
IMAGE_SIZE = 96
IMAGE_Y = 30
WALK_STEPS = 5
WALK_STEP_PIXELS = 12
WALK_LOOK_FRAMES = 4
WALK_HIDDEN_FRAMES = 1
WALK_SEQUENCE_FRAMES = (
    2
    + WALK_LOOK_FRAMES
    + WALK_STEPS
    + WALK_STEPS
    + WALK_HIDDEN_FRAMES
    + WALK_LOOK_FRAMES
    + WALK_STEPS
    + WALK_STEPS
    + WALK_HIDDEN_FRAMES
)
FRAME_DURATION_MS = 200
STATUS_TEXT_SIZE = 24
FOOTER_TEXT_SIZE = 10

ROOT = Path(__file__).resolve().parent.parent
RIGHT_IMAGE = ROOT / "firmware/assets/kiro_bw_96x96.bmp"
LEFT_IMAGE = ROOT / "firmware/assets/kiro_bw_96x96_left.bmp"
OUTPUT = ROOT / "assets/working-animation.gif"


def walk_phase(frame: int) -> tuple[int, bool, bool]:
    """ファームウェアの_animate_walkと同じ位置・向き・表示状態を返す。"""
    phase = frame % WALK_SEQUENCE_FRAMES
    movement_frames = WALK_STEPS

    right_look_end = WALK_LOOK_FRAMES
    right_walk_end = right_look_end + movement_frames
    right_return_end = right_walk_end + movement_frames
    right_hide_end = right_return_end + WALK_HIDDEN_FRAMES

    left_look_end = right_hide_end + WALK_LOOK_FRAMES
    left_walk_end = left_look_end + movement_frames
    left_return_end = left_walk_end + movement_frames

    if phase == 0:
        return 224, True, True
    if phase <= right_look_end:
        return 224, (phase % 2) == 0, True
    if phase <= right_walk_end:
        step = min(phase - right_look_end, WALK_STEPS)
        return 224 - step * WALK_STEP_PIXELS, True, True
    if phase <= right_return_end:
        step = min(phase - right_walk_end, WALK_STEPS)
        return 224 - (WALK_STEPS - step) * WALK_STEP_PIXELS, False, True
    if phase < right_hide_end:
        return 224, False, False
    if phase == right_hide_end:
        return 0, False, True
    if phase <= left_look_end:
        return 0, (phase % 2) == 1, True
    if phase <= left_walk_end:
        step = min(phase - left_look_end, WALK_STEPS)
        return step * WALK_STEP_PIXELS, False, True
    if phase <= left_return_end:
        step = min(phase - left_walk_end, WALK_STEPS)
        return (WALK_STEPS - step) * WALK_STEP_PIXELS, True, True
    return 0, True, False


def render_frame(
    right_image: Image.Image,
    left_image: Image.Image,
    frame: int,
) -> Image.Image:
    """WORKING状態の1フレームを生成する。"""
    x, facing_left, visible = walk_phase(frame)
    screen = Image.new("RGB", SCREEN_SIZE, (0, 0, 0))
    if visible:
        character = left_image if facing_left else right_image
        screen.paste(character, (x, IMAGE_Y))

    draw = ImageDraw.Draw(screen)
    status_font = ImageFont.load_default(size=STATUS_TEXT_SIZE)
    draw.text((10, 150), "WORKING", fill=(255, 255, 0), font=status_font)

    footer_font = ImageFont.load_default(size=FOOTER_TEXT_SIZE)
    draw.rectangle((0, 215, 319, 239), fill=(64, 64, 64))
    draw.text((10, 215), "BRIDGE CONNECTED", fill=(0, 255, 0), font=footer_font)
    draw.text((250, 215), "BLE: ON", fill=(0, 255, 0), font=footer_font)
    return screen


def main() -> None:
    """WORKINGアニメーションGIFを生成する。"""
    with Image.open(RIGHT_IMAGE) as source:
        right_image = source.convert("RGB")
    with Image.open(LEFT_IMAGE) as source:
        left_image = source.convert("RGB")

    frames = [
        render_frame(right_image, left_image, frame)
        for frame in range(WALK_SEQUENCE_FRAMES)
    ]

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
        f"論理フレーム数: {len(frames)}, サイズ: {SCREEN_SIZE}, "
        f"表示時間: {len(frames) * FRAME_DURATION_MS}ms"
    )


if __name__ == "__main__":
    main()
