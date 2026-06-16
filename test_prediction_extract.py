"""
预测参数提取测试 — 覆盖各种混乱格式。
每次更新 agent 后运行:
    .venv\Scripts\python test_prediction_extract.py
"""
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

from agent.prompts import EXTRACT_PREDICTION_PROMPT, safe_format
from agent.llm_client import chat_json
from agent.core import _normalize_prediction_input

TODAY = "2026-06-16"
CONTEXT = "{}"
PASSED = FAILED = 0


def test(msg: str, expected_movies: int, expected_dapan: int | None = None):
    """单次测试：发送消息，检查 LLM 提取结果。"""
    global PASSED, FAILED

    # 预处理
    normalized = _normalize_prediction_input(msg)
    prompt = safe_format(EXTRACT_PREDICTION_PROMPT, user_message=normalized, today=TODAY, context=CONTEXT)

    try:
        raw = chat_json("返回纯 JSON，不要 markdown 包裹。", prompt)
        result = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        print(f"  ❌ JSON 解析失败: {e}")
        FAILED += 1
        return

    params = result.get("params", {})
    movies = params.get("movies", [])
    dapan = params.get("dapan_total")
    missing = result.get("missing", [])

    ok = True
    errors = []

    movie_count = len(movies)
    if movie_count != expected_movies:
        ok = False
        errors.append(f"影片数 {movie_count} != 期望 {expected_movies}")

    if expected_dapan is not None and dapan != expected_dapan:
        ok = False
        errors.append(f"大盘 {dapan} != 期望 {expected_dapan}")

    if ok:
        print(f"  ✅ [{movie_count}部][大盘={dapan}][missing={missing}] ← \"{msg[:60]}...\"")
        PASSED += 1
    else:
        print(f"  ❌ [{movie_count}部][大盘={dapan}][missing={missing}] ← \"{msg[:60]}...\"")
        for e in errors:
            print(f"     {e}")
        FAILED += 1


# ── 标准格式（baseline）──
print("=" * 60)
print("1. 标准格式")
print("=" * 60)

test("封神2:17.6%, 哪吒:8.2%, 大盘42万", expected_movies=2, expected_dapan=420000)
test("两朵云：16%，玩具总动员5:21.7%，大盘46万", expected_movies=2, expected_dapan=460000)
test("消失5.6 阿嫲3.5 星球大战5.6 火遮眼9.8 大盘46万", expected_movies=4, expected_dapan=460000)

# ── 混乱分隔符 ──
print("\n" + "=" * 60)
print("2. 混乱分隔符（句号、空格混用）")
print("=" * 60)

test(
    "两朵云：16%，玩具总动员5:21.7%。抓特务16.2。爱是愤怒：9%，绝密：3.8% 大盘46万",
    expected_movies=5, expected_dapan=460000,
)
test(
    "封神2:17.6%  哪吒 8.2%  唐探1900:9.5%  大盘42万",
    expected_movies=3, expected_dapan=420000,
)
test(
    "封神2 17.6%, 哪吒 8.2%, 唐探1900 9.5%, 大盘 42万",
    expected_movies=3, expected_dapan=420000,
)

# ── 书名号 ──
print("\n" + "=" * 60)
print("3. 书名号包裹片名")
print("=" * 60)

test(
    "《封神2》:17.6%, 《哪吒》:8.2%, 大盘42万",
    expected_movies=2, expected_dapan=420000,
)
test(
    "《消失》6.7 《星球大战》8.7 大盘46万",
    expected_movies=2, expected_dapan=460000,
)
test(
    "《两朵云》：16%，《玩具总动员5》:21.7%。《抓特务》16.2 大盘46万",
    expected_movies=3, expected_dapan=460000,
)

# ── 占比格式变体 ──
print("\n" + "=" * 60)
print("4. 占比格式变体（小数、百分号、整数）")
print("=" * 60)

test("封神2:0.176, 哪吒:0.082, 大盘42万", expected_movies=2, expected_dapan=420000)
test("封神2:17.6, 哪吒:8.2, 大盘42万", expected_movies=2, expected_dapan=420000)
test("封神2 17.6% 哪吒 8.2% 大盘42万", expected_movies=2, expected_dapan=420000)
test("封神2:17.6 哪吒:8.2 大盘42万", expected_movies=2, expected_dapan=420000)

# ── 大盘格式变体 ──
print("\n" + "=" * 60)
print("5. 大盘格式变体")
print("=" * 60)

test("封神2:17.6%, 大盘420000", expected_movies=1, expected_dapan=420000)
test("封神2:17.6%, 大盘42万", expected_movies=1, expected_dapan=420000)
test("封神2:17.6%, 大盘四十二万", expected_movies=1, expected_dapan=420000)
test("封神2:17.6%, 总场次42万", expected_movies=1, expected_dapan=420000)

# ── 现实场景组合 ──
print("\n" + "=" * 60)
print("6. 现实场景（用户实际输入）")
print("=" * 60)

test(
    "两朵云：16%，玩具总动员5:21.7%，抓特务：16.2%，爱是愤怒：9%，绝密：3.8% 大盘46万",
    expected_movies=5, expected_dapan=460000,
)
test(
    "消失5.6  阿嫲3.5  星球大战5.6  火遮眼 9.8  大盘46万",
    expected_movies=4, expected_dapan=460000,
)
test(
    "两朵云：16%，玩具总动员5:21.7%，抓特务16.2。爱是愤怒：9%，绝密：3.8% 《消失》6.7 星球大战8.7 大盘46万",
    expected_movies=7, expected_dapan=460000,
)

# ── Summary ──
print("\n" + "=" * 60)
total = PASSED + FAILED
print(f"结果: {PASSED}/{total} 通过, {FAILED} 失败")
if FAILED == 0:
    print("✅ All tests passed!")
else:
    print(f"❌ {FAILED} test(s) failed")
sys.exit(0 if FAILED == 0 else 1)
