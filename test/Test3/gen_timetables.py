# -*- coding: utf-8 -*-
"""gen_timetables.py — 程序化生成 20 张评测课表 need/tt01.jpg ~ tt20.jpg，并自动填充真值

覆盖类型分配表的全部 20 种难度（高清/拍照/斜拍/弱光/翻拍/手写），
效果用 PIL 后处理模拟；生成图与真值天然一致（extract_gt.json 由本脚本直接写出）。
用法：python test/Test3/gen_timetables.py
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
random.seed(42)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FONT_DIR = Path("C:/Windows/Fonts")


def font(size, hand=False):
    names = ["STXINGKA.TTF", "simkai.ttf"] if hand else ["msyh.ttc", "simhei.ttf"]
    for n in names:
        p = FONT_DIR / n
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---------- 课程集（name, weekday 1-5, start, end, classroom, teacher, note） ----------
SET_A = [
    ("高等数学", 1, 1, 2, "教A101", "王明", ""),
    ("大学英语", 2, 1, 2, "外语楼204", "李华", ""),
    ("数据结构", 3, 1, 2, "实验楼302", "张伟", ""),
    ("大学物理", 4, 3, 4, "教C303", "陈芳", ""),
    ("高等数学", 3, 3, 4, "教A101", "王明", ""),
    ("体育", 5, 3, 4, "操场", "刘强", ""),
    ("操作系统", 1, 5, 6, "实验楼405", "赵强", ""),
    ("概率统计", 4, 7, 8, "教B202", "孙丽", ""),
]
SET_B = [
    ("线性代数", 1, 3, 4, "教D105", "周杰", ""),
    ("计算机网络", 2, 3, 4, "实验楼501", "吴敏", ""),
    ("线性代数", 3, 1, 2, "教D105", "周杰", ""),
    ("软件工程", 3, 5, 6, "教A302", "郑涛", ""),
    ("数据库原理", 4, 1, 2, "实验楼303", "冯雪", ""),
    ("大学语文", 5, 1, 2, "教E201", "许晴", ""),
    ("电路分析", 2, 7, 8, "实验楼102", "何军", ""),
    ("体育", 4, 5, 6, "体育馆", "马涛", ""),
    ("汇编语言", 5, 7, 8, "实验楼206", "高峰", ""),
]
SET_C = [
    ("算法设计", 1, 1, 4, "教B101", "钱进", ""),        # 连堂 1-4
    ("算法设计", 3, 1, 2, "教B101", "钱进", ""),
    ("大学英语", 2, 3, 4, "外语楼308", "林芳", ""),
    ("计算机组成", 4, 1, 2, "实验楼402", "罗成", ""),
    ("毛概", 2, 5, 6, "教A201", "蒋红", ""),
    ("数据结构", 5, 3, 4, "实验楼301", "张伟", "单周"),
    ("编译原理", 3, 7, 8, "教C103", "沈艳", "双周"),
    ("离散数学", 1, 7, 8, "教B203", "韩梅", ""),
]
SET_D = [
    ("微机原理", 1, 5, 6, "实验楼205", "杜鹏", ""),
    ("大学物理", 2, 1, 2, "教C302", "陈芳", ""),
    ("大学物理", 4, 1, 2, "教C302", "陈芳", ""),
    ("体育", 3, 3, 4, "操场", "刘强", ""),
    ("英语听力", 4, 3, 4, "外语楼401", "白雪", ""),
    ("C++程序设计", 5, 5, 6, "实验楼303", "谭浩", ""),
    ("电工电子", 2, 5, 6, "实验楼108", "田甜", ""),
    ("形势政策", 5, 1, 2, "教A101", "国强", ""),
]
SET_E = [
    ("深度学习", 1, 1, 4, "实验楼502", "严智", ""),     # 连堂
    ("机器学习", 2, 1, 2, "实验楼502", "严智", ""),
    ("计算机视觉", 3, 3, 4, "实验楼505", "康维", ""),
    ("自然语言处理", 4, 1, 2, "实验楼505", "康维", ""),
    ("机器学习", 4, 5, 6, "实验楼502", "严智", ""),
    ("数据挖掘", 5, 1, 2, "实验楼508", "金矿", ""),
    ("深度学习", 3, 5, 6, "实验楼502", "严智", ""),
    ("论文写作", 5, 7, 8, "教B302", "温书", ""),
    ("大数据平台", 2, 7, 8, "实验楼506", "涂数", ""),
]

DAYS = ["周一", "周二", "周三", "周四", "周五"]
SLOTS = ["第1-2节", "第3-4节", "第5-6节", "第7-8节", "第9-10节"]
PALETTE = [(222, 235, 247), (226, 240, 217), (253, 236, 230),
           (245, 233, 250), (255, 246, 219)]


# ---------- 渲染 ----------
def render_grid(courses, W=1300, H=920, transpose=False, color=False,
                hand=False, title="我的课表"):
    """网格课表：默认横版（星期为列）；transpose=True 时竖版（星期为行）"""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    fh, fc, fr = font(40, hand), font(26, hand), font(17)
    mx, my = 90, 118
    d.text((W // 2 - 110, 34), title, font=fh, fill="black")
    rowlab, collab = (DAYS, SLOTS) if transpose else (SLOTS, DAYS)
    lab_w = 160 if transpose else 150
    lab_h = 60 if transpose else 64
    gw, gh = W - mx * 2 - lab_w, H - my - lab_h - 20
    cw, ch = gw / 5, gh / 5
    for i, lab in enumerate(collab):
        x, y = mx + lab_w + i * cw, my
        d.rectangle([x, y, x + cw, y + lab_h], outline="black", width=3)
        d.text((x + cw / 2 - 26, y + lab_h / 2 - 15), lab, font=fc, fill="black")
    for i, lab in enumerate(rowlab):
        x, y = mx, my + lab_h + i * ch
        d.rectangle([x, y, x + lab_w, y + ch], outline="black", width=3)
        d.text((x + lab_w / 2 - 32, y + ch / 2 - 14), lab, font=fc, fill="black")
    for r in range(6):
        d.line([mx, my + lab_h + r * ch, mx + lab_w + 5 * cw, my + lab_h + r * ch],
               fill="black", width=3)
    for c in range(6):
        d.line([mx + lab_w + c * cw, my, mx + lab_w + c * cw, my + lab_h + 5 * ch],
               fill="black", width=3)
    d.rectangle([mx, my, mx + lab_w + 5 * cw, my + lab_h + 5 * ch],
                outline="black", width=4)
    for name, wd, s, e, room, tea, note in courses:
        ridx, rsp = (s - 1) // 2, (e - s + 2) // 2
        cx, cy = (ridx, wd - 1) if transpose else (wd - 1, ridx)
        x, y = mx + lab_w + cx * cw, my + lab_h + cy * ch
        w, h = cw, ch * rsp
        if color:
            d.rectangle([x + 3, y + 3, x + w - 3, y + h - 3], fill=PALETTE[wd % 5])
        d.text((x + w / 2 - len(name) * 13 / 2, y + h / 2 - 30), name, font=fc, fill="black")
        rt = f"{room} {tea}".strip()
        if rt:
            d.text((x + w / 2 - len(rt) * 8.5 / 2, y + h / 2 + 4), rt, font=fr, fill=(70, 70, 70))
        if note:
            d.text((x + 10, y + 6), note, font=font(16), fill=(200, 30, 30))
    return img


def render_list(courses, W=1160, H=1250, hand=False):
    """清单式课表：行=课程，列=课程名/星期/节次/教室/教师（tt02 用）"""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    fh, fc, fr = font(44, hand), font(26, hand), font(24, hand)
    d.text((W // 2 - 120, 36), "课程表", font=fh, fill="black")
    headers = ["课程名", "星期", "节次", "教室", "教师"]
    widths = [280, 140, 240, 240, 150]
    x0, y0 = 45, 130
    rh, row_h = 64, 105
    x = x0
    for hd, wd in zip(headers, widths):
        d.rectangle([x, y0, x + wd, y0 + rh], outline="black", width=3)
        d.text((x + wd / 2 - len(hd) * 13, y0 + 18), hd, font=fc, fill="black")
        x += wd
    for r, (name, wd_, s, e, room, tea, note) in enumerate(courses):
        y = y0 + rh + r * row_h
        slot = f"第{s}-{e}节" if e > s else f"第{s}节"
        vals = [name, f"周{['一','二','三','四','五'][wd_ - 1]}", slot, room, tea]
        x = x0
        for v, wd in zip(vals, widths):
            d.rectangle([x, y, x + wd, y + row_h], outline="black", width=3)
            d.text((x + 18, y + row_h / 2 - 16), v, font=fr, fill="black")
            x += wd
        if note:
            d.text((x0 + 300, y + 8), note, font=font(17), fill=(200, 30, 30))
    return img


# ---------- 效果 ----------
def noise(img, amp=1.0):
    # PIL 的 add 是 (img+n)/scale+offset，会把整图除暗；改为先重缩放噪声再叠加
    n = Image.effect_noise(img.size, 60).convert("RGB")
    d = n.point(lambda v: int(128 + (v - 128) * amp))
    return ImageChops.add(img, d, 1, -128)


def darken(img, f):
    return ImageEnhance.Brightness(img).enhance(f)


def tint_yellow(img):
    r, g, b = img.split()
    return Image.merge("RGB", (r, g, b.point(lambda v: int(v * 0.72))))


def vignette(img, depth=150):
    w, h = img.size
    sw, sh = w // 8, h // 8
    mask = Image.new("L", (sw, sh))
    mask.putdata([min(255, int(depth * math.hypot(x - sw / 2, y - sh / 2) / (sw / 2)))
                  for y in range(sh) for x in range(sw)])
    mask = mask.resize(img.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(30))
    return ImageChops.subtract(img, Image.merge("RGB", (mask, mask, mask)))


def glare(img, boxes):
    m = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(m)
    for b in boxes:
        d.ellipse(b, fill=105)
    m = m.filter(ImageFilter.GaussianBlur(45))
    return ImageChops.screen(img, Image.merge("RGB", (m, m, m)))


def moire(img, amp=36, freq=0.33):
    w, h = img.size
    pat = Image.new("L", (w, h))
    pat.putdata([128 + int(amp * math.sin((x + y) * freq)) for y in range(h) for x in range(w)])
    return ImageChops.add(img, Image.merge("RGB", (pat,) * 3), 1, -128)


def fold(img):
    """纸张褶皱：明暗条纹 + 折线"""
    w, h = img.size
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    for fx in (0.31, 0.62, 0.83):
        x = int(w * fx)
        d.line([x, 0, x - int(w * 0.05), h], fill=60, width=3)
    bands = Image.new("L", (w // 4, h // 4))
    bands.putdata([int(18 * math.sin(y * 0.9)) for y in range(h // 4) for _ in range(w // 4)])
    bands = bands.resize((w, h))
    m = ImageChops.add(m, bands)
    m = m.filter(ImageFilter.GaussianBlur(2))
    return ImageChops.subtract(img, Image.merge("RGB", (m,) * 3))


def _gauss_solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[piv] = M[piv], M[i]
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                M[r] = [a - f * c for a, c in zip(M[r], M[i])]
    return [M[i][n] / M[i][i] for i in range(n)]


def perspective(img, quad):
    """quad = 原四角在输出平面上的目标位置 [(x,y)*4]（左上、右上、右下、左下）"""
    W, H = img.size
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    A, b = [], []
    for (px, py), (qx, qy) in zip(quad, src):
        A.append([px, py, 1, 0, 0, 0, -qx * px, -qx * py]); b.append(qx)
        A.append([0, 0, 0, px, py, 1, -qy * px, -qy * py]); b.append(qy)
    return img.transform((W, H), Image.PERSPECTIVE, _gauss_solve(A, b), Image.BICUBIC)


def paper_bg(img, color=(246, 241, 228)):
    w, h = img.size
    bg = Image.new("RGB", (w + 60, h + 60), color)
    bg.paste(img, (30, 30))
    return bg


def rotate_small(img, deg):
    return img.rotate(deg, expand=True, fillcolor=(255, 255, 255))


def wall_mount(img):
    """贴墙远拍：缩小 + 米黄墙面 + 图钉 + 阴影"""
    w, h = img.size
    tw, th = int(w * 0.55), int(h * 0.55)
    tab = img.resize((tw, th), Image.LANCZOS)
    bg = Image.new("RGB", (w, h), (203, 197, 184))
    d = ImageDraw.Draw(bg)
    for gy in range(0, h, 90):                     # 墙面细纹
        d.line([0, gy, w, gy], fill=(196, 190, 177), width=1)
    x, y = (w - tw) // 2, (h - th) // 2
    d.rectangle([x + 8, y + 10, x + tw + 8, y + th + 10], fill=(120, 116, 106))  # 阴影
    bg.paste(tab, (x, y))
    d.rectangle([x, y, x + tw, y + th], outline=(90, 88, 82), width=3)
    for px, py in ((x + 20, y + 18), (x + tw - 20, y + 18)):                     # 图钉
        d.ellipse([px - 8, py - 8, px + 8, py + 8], fill=(180, 60, 50),
                  outline=(120, 40, 34), width=2)
    return noise(bg, 0.8)


def phone_frame(img):
    """手机翻拍：深色边框 + 顶部开孔 + 斜向反光条"""
    w, h = img.size
    fw, fh = w + 90, h + 190
    frame = Image.new("RGB", (fw, fh), (28, 28, 30))
    frame.paste(img, (45, 95))
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle([10, 10, fw - 10, fh - 10], radius=40, outline=(60, 60, 64), width=4)
    d.ellipse([fw // 2 - 30, 40, fw // 2 + 30, 78], fill=(15, 15, 17))  # 摄像头开孔
    band = Image.new("L", (fw, fh), 0)
    bd = ImageDraw.Draw(band)
    bd.polygon([(fw * 0.55, 0), (fw * 0.8, 0), (fw * 0.25, fh), (fw * 0.0, fh)], fill=70)
    band = band.filter(ImageFilter.GaussianBlur(35))
    return noise(ImageChops.screen(frame, Image.merge("RGB", (band,) * 3)), 0.5)


def hand_annotate(img, texts):
    """手写批注：红色楷体/行楷，整图层旋转（小条带旋转会把文字裁掉）"""
    rgba = img.convert("RGBA")
    f = font(38, hand=True)
    for t, (fx, fy), deg in texts:
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((int(img.size[0] * fx), int(img.size[1] * fy)),
                                 t, font=f, fill=(190, 30, 30, 235))
        lay = lay.rotate(deg, expand=False, resample=Image.BICUBIC)
        rgba = Image.alpha_composite(rgba, lay)
    return rgba.convert("RGB")


def handwritten(img):
    """整张手写风：米色纸底 + 轻噪点 + 微斜"""
    img = rotate_small(paper_bg(img, (248, 244, 232)), 1.6)
    return noise(img, 0.5)


# ---------- 20 张的规格：(tag, 底图渲染, 效果链, 保存质量) ----------


SPEC = {
    "tt01.jpg": ("高清扫描_横版_无畸变", lambda: render_grid(SET_A), [], 90),
    "tt02.jpg": ("高清扫描_竖版_含教师地点列", lambda: render_list(SET_B), [], 90),
    "tt03.jpg": ("高清截图_教务系统导出_合并单元格",
                 lambda: render_grid(SET_C, color=True), [], 92),
    "tt04.jpg": ("高清截图_PDF转图片_含跨节课程",
                 lambda: render_grid(SET_E, color=True, title="本学期课表"), [], 92),
    "tt05.jpg": ("正常拍照_竖版_光线好",
                 lambda: render_grid(SET_D, transpose=True),
                 [lambda i: rotate_small(i, 1.0), lambda i: noise(i, 0.6)], 65),
    "tt06.jpg": ("正常拍照_横版_光线好",
                 lambda: render_grid(SET_A, title="2026春季学期课表"),
                 [lambda i: rotate_small(i, -0.8), lambda i: noise(i, 0.6)], 65),
    "tt07.jpg": ("正常拍照_竖版_纸张略皱",
                 lambda: render_grid(SET_B, transpose=True),
                 [fold, lambda i: noise(i, 0.7), lambda i: darken(i, 0.96)], 60),
    "tt08.jpg": ("正常拍照_含手写批注",
                 lambda: render_grid(SET_D),
                 [lambda i: hand_annotate(i, [("第16周考试", (0.55, 0.02), -6),
                                              ("记得带实验报告!", (0.03, 0.86), 3)]),
                  lambda i: noise(i, 0.5)], 68),
    "tt09.jpg": ("斜拍_竖版_明显透视",
                 lambda: render_grid(SET_A, transpose=True),
                 [lambda i: perspective(i, [(int(i.width * 0.10), int(i.height * 0.04)),
                                            (int(i.width * 0.97), 0),
                                            (i.width, int(i.height * 0.93)),
                                            (0, int(i.height * 0.99))]),
                  lambda i: noise(i, 0.7), lambda i: darken(i, 0.93)], 58),
    "tt10.jpg": ("斜拍_横版_角度大",
                 lambda: render_grid(SET_B),
                 [lambda i: perspective(i, [(int(i.width * 0.16), int(i.height * 0.10)),
                                            (i.width, int(i.height * 0.02)),
                                            (int(i.width * 0.92), i.height),
                                            (int(i.width * 0.02), int(i.height * 0.88))]),
                  lambda i: noise(i, 0.8), lambda i: darken(i, 0.9)], 55),
    "tt11.jpg": ("斜拍_竖版_部分反光",
                 lambda: render_grid(SET_C),
                 [lambda i: rotate_small(i, 2.2),
                  lambda i: glare(i, [(i.width * 0.5, -80, i.width * 1.05, i.height * 0.4),
                                      (-60, i.height * 0.6, i.width * 0.4, i.height * 1.05)]),
                  lambda i: noise(i, 0.5)], 58),
    "tt12.jpg": ("斜拍_贴墙课表_远距拍摄",
                 lambda: render_grid(SET_D), [wall_mount], 55),
    "tt13.jpg": ("弱光_室内夜晚_噪点明显",
                 lambda: render_grid(SET_A),
                 [lambda i: darken(i, 0.52), lambda i: noise(i, 1.6),
                  lambda i: tint_yellow(i)], 55),
    "tt14.jpg": ("弱光_阴影遮挡_边缘发暗",
                 lambda: render_grid(SET_B),
                 [lambda i: darken(i, 0.62), vignette, lambda i: noise(i, 0.9)], 58),
    "tt15.jpg": ("弱光_灯光偏黄_色偏",
                 lambda: render_grid(SET_C, color=True),
                 [lambda i: darken(i, 0.72), tint_yellow, lambda i: noise(i, 0.8)], 58),
    "tt16.jpg": ("屏幕翻拍_电脑屏_摩尔纹",
                 lambda: render_grid(SET_D, color=True),
                 [moire, lambda i: noise(i, 0.5), lambda i: darken(i, 0.94)], 60),
    "tt17.jpg": ("屏幕翻拍_手机屏_反光",
                 lambda: render_grid(SET_B, title="教务在线"), [phone_frame], 60),
    "tt18.jpg": ("复杂样式_合并单元格_单双周标注",
                 lambda: render_grid(SET_C, color=True, title="班级课表(含单双周)"), [], 85),
    "tt19.jpg": ("复杂样式_跨节连堂_教师地点齐全",
                 lambda: render_grid(SET_E, color=True, title="研究生课表"), [], 85),
    "tt20.jpg": ("手写课表_白板或纸手写",
                 lambda: render_grid(SET_A, hand=True, title="我的课表"), [handwritten], 65),
}


def main():
    NEED.mkdir(parents=True, exist_ok=True)
    gt = {}
    for fname, (tag, base, effects, quality) in sorted(SPEC.items()):
        img = base()
        for fx in effects:
            img = fx(img)
        out = NEED / fname
        img.save(out, "JPEG", quality=quality)
        gt[fname] = {"tag": tag}
        print(f"已生成 {fname}  [{tag}]  {img.size[0]}x{img.size[1]}")
    # 真值：按 SPEC 里 base 闭包对应的 SET 写出
    set_map = {
        "tt01.jpg": SET_A, "tt02.jpg": SET_B, "tt03.jpg": SET_C, "tt04.jpg": SET_E,
        "tt05.jpg": SET_D, "tt06.jpg": SET_A, "tt07.jpg": SET_B, "tt08.jpg": SET_D,
        "tt09.jpg": SET_A, "tt10.jpg": SET_B, "tt11.jpg": SET_C, "tt12.jpg": SET_D,
        "tt13.jpg": SET_A, "tt14.jpg": SET_B, "tt15.jpg": SET_C, "tt16.jpg": SET_D,
        "tt17.jpg": SET_B, "tt18.jpg": SET_C, "tt19.jpg": SET_E, "tt20.jpg": SET_A,
    }
    for fname, (tag, _, _, _) in SPEC.items():
        gt[fname]["courses"] = [
            {"name": n, "weekday": w, "start_slot": s, "end_slot": e,
             "classroom": r, "teacher": t}
            for n, w, s, e, r, t, _ in set_map[fname]]
    CASES.mkdir(parents=True, exist_ok=True)
    (CASES / "extract_gt.json").write_text(
        json.dumps(dict(sorted(gt.items())), ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v["courses"]) for v in gt.values())
    print(f"\n已写出真值：{CASES / 'extract_gt.json'}（20 张 / 共 {total} 门课程真值）")


if __name__ == "__main__":
    main()
