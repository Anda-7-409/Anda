# 校园知识库 RAG：Knowledge.txt → bge-m3 向量化 → Knowledge.db → 余弦检索 → general 链作答
# 首次提问自动建索引；Knowledge.txt 更新后（mtime 变化）自动重建
import json
import re
import sqlite3
from pathlib import Path

from AI import model_router
from Backend.config import Knowledge_DB_PATH

KB_FILE = Path(__file__).parent.parent / "Data" / "Knowledge.txt"
TOP_K = 3
SIM_THRESHOLD = 0.56   # 余弦阈值：实测真实命中0.58~0.72、无关问题0.50~0.54，取区分带下沿保召回

# 容错解析：`N问：` 或 `N：` 开头为问题行（半/全角冒号都兼容），`答：`（含 `答·：`）开头为答案行
_Q_RE = re.compile(r"^(\d+)\s*问?\s*[：:]\s*(.+)$")
_A_RE = re.compile(r"^答[·\s]*[：:]\s*")


def _load_qa():
    # 每条 QA 一个 chunk：问题行后的所有行（含跨行）并入该条答案
    qa_list, cur_q, cur_a = [], None, []
    for line in KB_FILE.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("知识库更新时间"):
            continue
        qm = _Q_RE.match(line)
        if qm:
            if cur_q:
                qa_list.append((cur_q, "\n".join(cur_a)))
            cur_q, cur_a = qm.group(2).strip(), []
        elif cur_q:
            cur_a.append(_A_RE.sub("", line, count=1).strip())
    if cur_q:
        qa_list.append((cur_q, "\n".join(cur_a)))
    return qa_list


def _get_db():
    Knowledge_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Knowledge_DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS kb_chunk(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT, embedding TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS kb_meta(
        key TEXT PRIMARY KEY, value TEXT)""")
    return conn


def _rebuild(conn) -> int:
    qa_list = _load_qa()
    if not qa_list:
        raise RuntimeError("Knowledge.txt 未解析出任何问答条目")
    vectors = model_router.embed([f"问：{q}\n答：{a}" for q, a in qa_list])
    conn.execute("DELETE FROM kb_chunk")
    conn.execute("DELETE FROM kb_meta")
    for (q, a), vec in zip(qa_list, vectors):
        conn.execute("INSERT INTO kb_chunk(content, embedding) VALUES(?, ?)",
                     (f"问：{q}\n答：{a}", json.dumps(vec)))
    conn.execute("INSERT INTO kb_meta(key, value) VALUES('mtime', ?)",
                 (str(KB_FILE.stat().st_mtime),))
    conn.commit()
    return len(qa_list)


def _ensure_index(conn) -> int:
    mtime = str(KB_FILE.stat().st_mtime)
    row = conn.execute("SELECT value FROM kb_meta WHERE key='mtime'").fetchone()
    count = conn.execute("SELECT COUNT(*) FROM kb_chunk").fetchone()[0]
    if count == 0 or (row and row[0] != mtime):
        return _rebuild(conn)
    return count


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _search(query: str, top_k=TOP_K):
    # hits 不过滤直接取 top_k：阈值把关放在工具层（只看 top1），
    # 弱相关片段放行给生成层自行甄别（如"洗衣服"召回的"洗衣间"片段分数不高但最有用）
    conn = _get_db()
    try:
        total = _ensure_index(conn)
        qvec = model_router.embed([query])[0]
        hits = []
        for content, emb in conn.execute("SELECT content, embedding FROM kb_chunk"):
            hits.append((_cos(qvec, json.loads(emb)), content))
        hits.sort(key=lambda h: -h[0])
        return {"ok": True, "data": {"total": total, "hits": hits[:top_k]}}
    except model_router.NoModelError:
        return {"ok": False, "message": "向量化模型不可用，知识库暂时答不了哦 ~"}
    except Exception as exc:
        return {"ok": False, "message": f"知识库检索失败：{exc}"}
    finally:
        conn.close()


def knowledge_tool(utterance, user_id, **_):
    # 工具契约：fn(utterance, user_id, **_) -> dict；utterance 为 FC 生成的 task 参数
    if not (utterance or "").strip():
        return {"ok": False, "message": "问题不能为空哦 ~"}
    got = _search(utterance.strip())
    if not got["ok"]:
        return got
    hits = got["data"]["hits"]
    # 阈值只挡"一条相关都没有"：top1 低于阈值说明整个知识库与问题无关
    if not hits or hits[0][0] < SIM_THRESHOLD:
        return {"ok": True, "data": {
            "answer": "知识库里暂时没有相关内容，可以换个说法问问，或让我联网搜索哦 ~",
            "hits": []}}
    block = "\n\n".join(f"【片段{i + 1}】\n{c}" for i, (_, c) in enumerate(hits))
    try:
        msg, _ = model_router.chat("general", [
            {"role": "system", "content":
                "你是校园AI助手安答。根据给定的知识库片段回答问题：多个片段的信息可以互补综合；"
                "与问题无关的片段直接忽略；只有片段完全答不了才说不知道，不要编造。回答简洁友好。"},
            {"role": "user", "content": f"知识库片段：\n{block}\n\n问题：{utterance.strip()}"},
        ])
        answer = (msg.get("content") or "").strip()
    except Exception:
        # 生成链全挂时把检索片段原样给用户，检索结果不丢
        answer = block
    return {"ok": True, "data": {"answer": answer, "hits": [
        {"score": round(s, 3), "content": c} for s, c in hits]}}


def status():
    # /health 用：知识库索引状态
    if not KB_FILE.is_file():
        return {"ok": False, "chunks": 0, "reason": "Knowledge.txt 不存在"}
    if not Knowledge_DB_PATH.is_file():
        return {"ok": False, "chunks": 0, "reason": "尚未建索引（首次提问时自动构建）"}
    try:
        conn = _get_db()
        n = conn.execute("SELECT COUNT(*) FROM kb_chunk").fetchone()[0]
        conn.close()
        return {"ok": n > 0, "chunks": n}
    except Exception:
        return {"ok": False, "chunks": 0, "reason": "Knowledge.db 损坏"}
