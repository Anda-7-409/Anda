# -*- coding: utf-8 -*-
"""make_dataset.py — 生成 20 张覆盖不同清晰度/拍法/表格样式的课表图片（tt01~tt20.jpg）

因为图片是程序画的，"真值"天然精确：生成的同时自动把 courses 写入 cases/extract_gt.json。
判分口径与 judge.py 一致：weekday 1=周一；节次成对（1-2/3-4/.../9-10）；
连堂课 GT 写一个对象；图片上没有的教师字段 GT 填 ""（判分自动不计分母）。

用法：python test/Test3/make_dataset.py
"""
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

TEST3 = Path(__file__).parent
NEED = TEST3 / "need"
CASES = TEST3 / "cases"
FONT_DIR = Path("C:/Windows/Fonts")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

COURSE_POOL = [
    "高等数学", "大学英语", "大学物理", "数据结构", "操作系统", "计算机网络",
    "线性代数", "概率论", "程序设计", "数据库原理", "软件工程", "电路分析",
    "模拟电子技术", "数字逻辑", "大学语文", "体育", "形势与政策", "工程制图",
    "马克思主义基本原理", "毛泽东思想概论",
]
TEACHERS = ["王明", "李华", "张伟", "刘强", "陈芳", "杨光", "赵磊", "孙丽", "周涛", "吴敏"]
ROOMS = ["教A101", "教A203", "教B202", "教B305", "教C303", "实验楼302",
         "实验楼405", "图书馆报告厅", "操场", "音乐教室"]
WEEK_CN = ["周一", "周二", "周三", "周四", "周五"]
ROW_LABEL = ["第1-2节", "第3-4节", "第5-6节", "第7-8节", "第9-10节"]
PASTEL = [(222, 235, 247), (226, 240, 217), (253, 236, 230), (255, 242, 204),
          (237, 227, 247), (218, 238, 235)]


def font(names, size):
    for n in names:
        p = FONT_DIR / n
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


def print_font(size):
    return font(["msyh.ttc", "simhei.ttf", "simsun.ttc"], size)


def hand_font(size):
    return font(["simkai.ttf", "STKAITI.TTF", "msyh.ttc"], size)


# ---------- 课表内容生成 ----------
def gen_schedule(seed, n_target=10, cross_rows=()):
    """cross_rows 里写允许连堂起始行（0=1-2节 起，跨到 3-4节）。返回课程列表。"""
    rnd = random.Random(seed)
    names = rnd.sample(COURSE_POOL, len(COURSE_POOL))
    used, courses, k = set(), [], 0
    while len(courses) < n_target and k < 200:
        k += 1
        wd = rnd.randint(1, 5)
        row = rnd.randint(0, 4)
        span = 1
        if row in cross_rows and row + 1 <= 4 and rnd.random() < 0.6:
            span = 2
        cells = {(wd, row + i) for i in range(span)}
        if cells & used:
            continue
        used |= cells
        courses.append({
            "name": names[len(courses) % len(names)],
            "weekday": wd, "start_slot": 2 * row + 1, "end_slot": 2 * row + span,
            "classroom": rnd.choice(ROOMS), "teacher": rnd.choice(TEACHERS),
        })
    return courses


# ---------- 底图渲染 ----------
def render_base(courses, *, landscape, show_teacher, style, week_note, seed):
    rnd = random.Random(seed + 7)
    if landscape:
        cell_w, cell_h, label_w = 168, 96, 118
    else:
        cell_w, cell_h, label_w = 148, 104, 104
    w = label_w + 5 * cell_w + 60
    h = 96 + 52 + 5 * cell_h + 90
    hand = style == "hand"
    web = style == "web"
    if hand:
        img = Image.new("RGB", (w, h), (252, 248, 238))
        line_col, head_col, txt_col = (40, 60, 140), (40, 60, 140), (30, 30, 90)
        f_title, f_head, f_cell, f_sub = hand_font(34), hand_font(26), hand_font(24), hand_font(19)
    elif web:
        img = Image.new("RGB", (w, h), (250, 251, 253))
        line_col, head_col, txt_col = (200, 205, 215), (68, 114, 196), (50, 50, 50)
        f_title, f_head, f_cell, f_sub = print_font(32), print_font(24), print_font(21), print_font(17)
    else:
        img = Image.new("RGB", (w, h), "white")
        line_col, head_col, txt_col = (0, 0, 0), (0, 0, 0), (0, 0, 0)
        f_title, f_head, f_cell, f_sub = print_font(32), print_font(24), print_font(21), print_font(17)

    d = ImageDraw.Draw(img)
    d.text((w // 2 - 60, 26), "课程表", font=f_title, fill=txt_col)

    x0, y0 = 30, 96
    head_fill = (68, 114, 196) if web else (235, 240, 250) if not hand else None

    def rect(x1, y1, x2, y2, outline=line_col, width=2, fill=None):
        if web:
            d.rectangle([x1, y1, x2, y2], outline=(200, 205, 215), width=1, fill=fill)
        else:
            d.rectangle([x1, y1, x2, y2], outline=outline, width=width, fill=fill)

    # 表头
    rect(x0, y0, x0 + label_w, y0 + 52, fill=head_fill)
    d.text((x0 + label_w // 2 - 26, y0 + 12), "节次", font=f_head,
           fill=(255, 255, 255) if web else txt_col)
    for c, wd_cn in enumerate(WEEK_CN):
        x = x0 + label_w + c * cell_w
        rect(x, y0, x + cell_w, y0 + 52, fill=head_fill)
        d.text((x + cell_w // 2 - 26, y0 + 12), wd_cn, font=f_head,
               fill=(255, 255, 255) if web else txt_col)

    # 行与节次标签
    for r in range(5):
        y = y0 + 52 + r * cell_h
        fill = (242, 246, 252) if (web and r % 2 == 0) else None
        rect(x0, y, x0 + label_w, y + cell_h, fill=fill)
        d.text((x0 + 12, y + cell_h // 2 - 14), ROW_LABEL[r], font=f_cell, fill=txt_col)
        for c in range(5):
            x = x0 + label_w + c * cell_w
            rect(x, y, x + cell_w, y + cell_h, fill=fill)

    # 课程格子
    for idx, cinfo in enumerate(courses):
        col = cinfo["weekday"] - 1
        row0 = (cinfo["start_slot"] - 1) // 2
        span_rows = (cinfo["end_slot"] - cinfo["start_slot"] + 2 - 1) // 2 or 1
        x = x0 + label_w + col * cell_w
        y = y0 + 52 + row0 * cell_h
        y2 = y0 + 52 + (row0 + span_rows) * cell_h
        fill = None if hand else PASTEL[idx % len(PASTEL)]
        if web:
            d.rectangle([x + 1, y + 1, x + cell_w - 1, y2 - 1], fill=fill)
        else:
            d.rectangle([x + 3, y + 3, x + cell_w - 3, y2 - 3],
                        outline=line_col if hand else (150, 160, 175), width=2, fill=fill)
        name = cinfo["name"]
        if week_note and idx % 2 == 0:
            name += "（单周）" if idx % 4 == 0 else "（双周）"
        tx, ty = x + 10, y + 8
        d.text((tx, ty), name, font=f_cell, fill=txt_col)
        ty += 30
        d.text((tx, ty), cinfo["classroom"], font=f_sub, fill=(90, 90, 90) if not hand else txt_col)
        if show_teacher:
            ty += 24
            d.text((tx, ty), cinfo["teacher"], font=f_sub,
                   fill=(90, 90, 90) if not hand else txt_col)
        if week_note and idx % 2 == 0:
            ty += 24
            d.text((tx, ty), "每周都上", font=f_sub, fill=(90, 90, 90))
    return img


# ---------- 图像后处理 ----------
def find_coeffs(pa, pb):
    A, B = [], []
    for i in range(4):
        x, y = pb[i]; X, Y = pa[i]
        A.append([x, y, 1, 0, 0, 0, x * X, y * X]); B.append(X)
        A.append([0, 0, 0, x, y, 1, x * Y, y * Y]); B.append(Y)
    n = 8
    M = [A[i][:] + [B[i]] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c] or 1e-12
        M[c] = [v / pv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [rv - f * cv for rv, cv in zip(M[r], M[c])]
    return [M[i][8] for i in range(8)]


def perspective(img, strength, seed):
    rnd = random.Random(seed + 31)
    w, h = img.size
    s1, s2, s3, s4 = (rnd.uniform(0.5, 1.0) * strength for _ in range(4))
    pa = [(s1, s2 * 0.4), (w - s2, s3 * 0.6), (w - s3 * 0.7, h - s4), (s4 * 0.5, h - s3 * 0.8)]
    pb = [(0, 0), (w, 0), (w, h), (0, h)]
    return img.transform(img.size, Image.PERSPECTIVE, find_coeffs(pa, pb), Image.BICUBIC)


def add_noise(img, sigma):
    noise = Image.effect_noise(img.size, sigma).convert("RGB")
    return ImageChops.add(img, noise, scale=1.0, offset=-128)


def glare_band(img, seed):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = img.size
    rnd = random.Random(seed + 53)
    y_top = rnd.randint(-40, h // 4)
    for i, a in enumerate((28, 46, 60, 46, 28)):
        d.polygon([(0, y_top + i * 26), (w, y_top - 60 + i * 26),
                   (w, y_top - 34 + i * 26), (0, y_top + 26 + i * 26)],
                  fill=(255, 255, 255, a))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def shadow_grad(img):
    w, h = img.size
    mask = Image.new("L", (w, h))
    d = ImageDraw.Draw(mask)
    for x in range(w):
        v = int(255 * (0.45 + 0.55 * (x / w)))
        d.line([(x, 0), (x, h)], fill=v)
    dark = ImageChops.multiply(img, Image.merge("RGB", (mask, mask, mask)))
    return dark


def moire(img, period=4, amp=26):
    """叠加零均值正弦条纹（屏幕翻拍摩尔纹）"""
    w, h = img.size
    data = bytearray()
    for y in range(h):
        v = int(amp * math.sin(2 * math.pi * y / period)) + 128
        data.extend([v] * w)
    band = Image.frombytes("L", (w, h), bytes(data)).convert("RGB")
    return ImageChops.add(img, band, scale=1.0, offset=-128)


def scanlines(img):
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(0, img.size[1], 3):
        d.line([(0, y), (img.size[0], y)], fill=(0, 0, 0, 14))
    return img


def wrinkle(img, seed):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    rnd = random.Random(seed + 71)
    w, h = img.size
    for _ in range(26):
        x1, y1 = rnd.randint(0, w), rnd.randint(0, h)
        x2, y2 = x1 + rnd.randint(-260, 260), y1 + rnd.randint(-160, 160)
        a = rnd.randint(14, 34)
        if rnd.random() < 0.5:
            d.line([(x1, y1), (x2, y2)], fill=(120, 110, 95, a), width=rnd.randint(1, 3))
        else:
            d.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, a), width=rnd.randint(1, 3))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img.filter(ImageFilter.GaussianBlur(0.6))


def color_cast(img, mult):
    ch = list(img.split())
    ch = [c.point(lambda v, m=m: int(v * m)) for c, m in zip(ch, mult)]
    return Image.merge("RGB", ch)


def annotate_hand(img, seed):
    """手写批注（不属于课程，是错误案例素材）"""
    d = ImageDraw.Draw(img)
    f = hand_font(24)
    w, h = img.size
    rnd = random.Random(seed + 91)
    notes = ["※ 周四 19:30 组会 别忘", "※ 这页不是课表的部分：周五交作业", "※ 下周调课另行通知"]
    d.text((40, h - 66), rnd.choice(notes), font=f, fill=(190, 40, 40))
    return img


# ---------- 每张图的规格 ----------
SPECS = {
    "tt01.jpg": dict(landscape=True,  teacher=False, style="plain"),
    "tt02.jpg": dict(landscape=False, teacher=True,  style="plain"),
    "tt03.jpg": dict(landscape=True,  teacher=True,  style="web",   cross=True),
    "tt04.jpg": dict(landscape=False, teacher=False, style="plain", cross=True),
    "tt05.jpg": dict(landscape=False, teacher=False, style="plain", rotate=1.0, noise=6),
    "tt06.jpg": dict(landscape=True,  teacher=False, style="plain", rotate=-1.2, noise=6),
    "tt07.jpg": dict(landscape=False, teacher=False, style="plain", wrinkle=True),
    "tt08.jpg": dict(landscape=False, teacher=False, style="plain", annotate=True, noise=4),
    "tt09.jpg": dict(landscape=False, teacher=False, style="plain", persp=42),
    "tt10.jpg": dict(landscape=True,  teacher=False, style="plain", persp=72),
    "tt11.jpg": dict(landscape=False, teacher=False, style="plain", persp=36, glare=True),
    "tt12.jpg": dict(landscape=True,  teacher=False, style="plain", far=True, persp=30, noise=8),
    "tt13.jpg": dict(landscape=False, teacher=False, style="plain", dark=0.42, noise=18, quality=68),
    "tt14.jpg": dict(landscape=False, teacher=False, style="plain", shadow=True, dark=0.8),
    "tt15.jpg": dict(landscape=False, teacher=False, style="plain", cast=(1.12, 1.0, 0.72), dark=0.86),
    "tt16.jpg": dict(landscape=True,  teacher=False, style="web",   moire=True, scan=True, blur=0.7),
    "tt17.jpg": dict(landscape=False, teacher=False, style="web",   glare=True, moire=True),
    "tt18.jpg": dict(landscape=False, teacher=True,  style="plain", cross=True, week_note=True),
    "tt19.jpg": dict(landscape=True,  teacher=True,  style="plain", cross=True, week_note=True),
    "tt20.jpg": dict(landscape=False, teacher=False, style="hand",  rotate=0.8),
}


def build_one(fname):
    sp = SPECS[fname]
    idx = int(fname[2:4])
    n_target = 8 + (idx % 4)                       # 8~11 门
    cross_rows = (0, 2) if sp.get("cross") else ()
    courses = gen_schedule(1000 + idx, n_target=n_target, cross_rows=cross_rows)
    img = render_base(courses, landscape=sp["landscape"], show_teacher=sp["teacher"],
                      style=sp["style"], week_note=sp.get("week_note", False),
                      seed=1000 + idx)
    if sp.get("annotate"):
        img = annotate_hand(img, 1000 + idx)
    if sp.get("rotate"):
        img = img.rotate(sp["rotate"], expand=True, fillcolor="white" if sp["style"] != "hand" else (252, 248, 238))
    if sp.get("far"):                              # 远距：贴到墙上缩小
        big = Image.new("RGB", (img.width + 420, img.height + 340), (196, 189, 176))
        big.paste(img, (210, 170))
        img = big.resize((int(img.width * 0.72), int(img.height * 0.72)), Image.LANCZOS)
    if sp.get("persp"):
        img = perspective(img, sp["persp"], 1000 + idx)
    if sp.get("glare"):
        img = glare_band(img, 1000 + idx)
    if sp.get("moire"):
        img = moire(img)
    if sp.get("scan"):
        img = scanlines(img)
    if sp.get("wrinkle"):
        img = wrinkle(img, 1000 + idx)
    if sp.get("shadow"):
        img = shadow_grad(img)
    if sp.get("cast"):
        img = color_cast(img, sp["cast"])
    if sp.get("dark"):
        img = ImageEnhance.Brightness(img).enhance(sp["dark"])
    if sp.get("blur"):
        img = img.filter(ImageFilter.GaussianBlur(sp["blur"]))
    if sp.get("noise"):
        img = add_noise(img, sp["noise"])
    q = sp.get("quality", 88)
    img.save(NEED / fname, "JPEG", quality=q)
    # GT：图片没画的字段填 ""，与判分口径一致
    gt_courses = [{
        "name": c["name"], "weekday": c["weekday"],
        "start_slot": c["start_slot"], "end_slot": c["end_slot"],
        "classroom": c["classroom"] if sp["style"] != "hand" or True else "",
        "teacher": c["teacher"] if sp["teacher"] else "",
    } for c in courses]
    return gt_courses


def main():
    NEED.mkdir(parents=True, exist_ok=True)
    gt_path = CASES / "extract_gt.json"
    gt = json.loads(gt_path.read_text("utf-8"))
    for fname in SPECS:
        gt[fname]["courses"] = build_one(fname)
        print(f"{fname}: {len(gt[fname]['courses'])} 门课，已生成")
    gt_path.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v["courses"]) for v in gt.values())
    print(f"\n共 20 张图 → {NEED}")
    print(f"真值已写入 {gt_path}（合计 {total} 门课）")


if __name__ == "__main__":
    main()
