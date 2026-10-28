
import re
import time
from pathlib import Path

from AI import model_router
from Backend.config import GLM_API_KEY, UPLOAD_DIR

MAX_CODE_CHARS = 50_000

# 语言标签 -> 文件扩展名（围栏块标注的 tag 一律小写后查表，查不到落到 .txt）
EXT_MAP = {
    "python": ".py", "python3": ".py", "py": ".py",
    "javascript": ".js", "js": ".js", "node": ".js", "nodejs": ".js",
    "typescript": ".ts", "ts": ".ts",
    "html": ".html", "css": ".css",
    "java": ".java", "c": ".c", "cpp": ".cpp", "c++": ".cpp",
    "c#": ".cs", "cs": ".cs", "go": ".go", "golang": ".go",
    "rust": ".rs", "rs": ".rs", "php": ".php",
    "sql": ".sql", "shell": ".sh", "bash": ".sh", "sh": ".sh",
    "json": ".json", "yaml": ".yml", "yml": ".yml",
    "markdown": ".md", "md": ".md", "matlab": ".m", "r": ".r",
    "text": ".txt", "txt": ".txt",
}

# 只认第一个围栏代码块；要求模型第一行就是 ```，避免把讲解文本误当代码
_CODE_RE = re.compile(r"```([A-Za-z+#.]*)[ \t]*\r?\n(.*?)```", re.S)

_GEN_SYSTEM = (
    "你是编程助手。用户会描述想要的一段代码，你只输出一个围栏代码块："
    "第一行是```加上语言标注（如 ```python），最后一行是```，"
    "代码块之外不要输出任何文字。代码要完整可保存、可直接运行或使用，"
    "关键步骤加简短中文注释。"
)


def code_gen_tool(utterance: str, user_id: int, refs=None) -> dict:
    if not GLM_API_KEY:
        return {"ok": False, "error": "未配置 GLM_API_KEY，代码生成不可用",
                "hint": "如实告知用户代码生成功能暂不可用，不要编造文件或链接"}
    if not utterance or not utterance.strip():
        return {"ok": False, "error": "没有收到代码需求",
                "hint": "请用户描述想要什么代码"}

    answer, _ = model_router.chat_text([
        {"role": "system", "content": _GEN_SYSTEM},
        {"role": "user", "content": utterance.strip()},
    ])
    if not answer:
        return {"ok": False, "error": "代码生成模型暂时不可用",
                "hint": "如实告知用户稍后再试，不要编造文件或链接"}

    m = _CODE_RE.search(answer)
    if not m or not m.group(2).strip():
        return {"ok": False, "error": "模型没有返回有效的代码块",
                "hint": "如实告知用户生成失败，建议换个更具体的描述重试"}
    tag, code = m.group(1).strip().lower(), m.group(2).rstrip()

    if len(code) > MAX_CODE_CHARS:
        return {"ok": False, "error": f"生成的代码超过 {MAX_CODE_CHARS} 字符上限",
                "hint": "建议用户把需求拆小一点再试"}

    ext = EXT_MAP.get(tag, ".txt")
    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    base = time.strftime("gen_%Y%m%d_%H%M%S")
    name = f"{base}{ext}"
    n = 1
    while (user_dir / name).exists():
        name = f"{base}_{n}{ext}"
        n += 1
    (user_dir / name).write_text(code, encoding="utf-8")

    lines = code.count("\n") + 1
    preview_lines = code.splitlines()[:10]
    return {
        "ok": True,
        "file_name": name,
        "language": tag or "未知",
        "lines": lines,
        "download_url": f"/upload/download/{name}",
        "preview": "\n".join(preview_lines) + ("\n..." if lines > 10 else ""),
        "note": ("代码已真实生成并保存为文件，把文件名、语言、行数和下载链接告诉用户即可；"
                 f"下载链接是 {name} 对应的 /upload/download/{name}，不要编造其他链接，"
                 "不要在回复里重复粘贴全部代码，只转述预览。"),
    }
