# -*- coding: utf-8 -*-
"""make_sample.py — 生成冒烟用样例课表 need/tt00.jpg + 真值 cases/smoke_gt.json

只用于跑通链路（--gt cases/smoke_gt.json），不参与正式 20 张评测。
用法：python test/Test3/make_sample.py
"""
import sys
from pathlib import Path

TEST3_DIR = Path(__file__).parent
NEED = TEST3_DIR / "need"
CASES = TEST3_DIR / "cases"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

COURSES = [
    # (名称, 周几, 起始节, 结束节, 教室, 教师, 画在哪一格)
    ("高等数学", 1, 1, 2, "教A101", "王明",  (1, 0)),
    ("大学英语", 2, 3, 4, "教B202", "李华",  (2, 1)),
    ("高等数学", 3, 1, 2, "教A101", "王明",  (3, 0)),
    ("数据结构", 3, 5, 6, "实验楼302", "张伟", (3, 2)),
    ("体育",    4, 7, 8, "操场",   "刘强",  (4, 3)),
    ("大学物理", 5, 3, 4, "教C303", "陈芳",  (5, 1)),
]
WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
SLOTS = ["第1-2节", "第3-4节", "第5-6节", "第7-8节", "第9-10节"]


def pick_font(size):
    from PIL import ImageFont
    for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc"):
        p = Path("C:/Windows/Fonts") / name
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw():
    from PIL import Image, ImageDraw
    W, H, ROW_H, COL_W, X0, Y0 = 1100, 640, 92, 152, 132, 96
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title, f_head, f_cell = pick_font(30), pick_font(26), pick_font(22)

    d.text((W // 2 - 66, 22), "我的课表", font=f_title, fill="black")

    # 表头：节次 + 周一到周五
    for i, w in enumerate(WEEK_CN[:5]):
        x = X0 + COL_W + i * COL_W
        d.rectangle([x, Y0, x + COL_W, Y0 + 52], outline="black", width=2)
        d.text((x + COL_W // 2 - 26, Y0 + 10), w, font=f_head, fill="black")
    d.rectangle([X0, Y0, X0 + COL_W, Y0 + 52], outline="black", width=2)
    d.text((X0 + 44, Y0 + 10), "节次", font=f_head, fill="black")

    # 行
    for r, slot in enumerate(SLOTS):
        y = Y0 + 52 + r * ROW_H
        d.rectangle([X0, y, X0 + COL_W, y + ROW_H], outline="black", width=2)
        d.text((X0 + 32, y + ROW_H // 2 - 14), slot, font=f_cell, fill="black")
        for c in range(5):
            x = X0 + COL_W + c * COL_W
            d.rectangle([x, y, x + COL_W, y + ROW_H], outline="black", width=2)

    # 课程格子（列 = weekday-1，行 = (起始节-1)//2）
    slot_row = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}
    for name, wd, s, e, room, tea, _ in COURSES:
        x = X0 + COL_W + (wd - 1) * COL_W
        y = Y0 + 52 + slot_row[(s - 1) // 2] * ROW_H
        d.rectangle([x + 5, y + 5, x + COL_W - 5, y + ROW_H - 5],
                    fill=(222, 235, 247))
        d.text((x + 14, y + 12), name, font=f_cell, fill="black")
        d.text((x + 14, y + 46), f"{room} {tea}", font=pick_font(17), fill=(60, 60, 60))

    NEED.mkdir(parents=True, exist_ok=True)
    out = NEED / "tt00.jpg"
    img.save(out, "JPEG", quality=92)
    print(f"已生成样例课表：{out}")


def write_gt():
    import json
    gt = {"tt00.jpg": {
        "tag": "样例_程序生成_清晰打印体",
        "courses": [{"name": n, "weekday": w, "start_slot": s, "end_slot": e,
                     "classroom": r, "teacher": t}
                    for n, w, s, e, r, t, _ in COURSES],
    }}
    CASES.mkdir(parents=True, exist_ok=True)
    (CASES / "smoke_gt.json").write_text(
        json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成冒烟真值：{CASES / 'smoke_gt.json'}（{len(COURSES)} 门课）")


if __name__ == "__main__":
    draw()
    write_gt()
