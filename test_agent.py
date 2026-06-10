"""
离线验证脚本 — 测试 LLM 调用和 Agent 路由，不需要飞书。
用法: python test_agent.py
"""
import json
import sys
from agent.llm_client import chat
from agent.prompts import INTENT_PROMPT, EXTRACT_REELCLEAN_PROMPT, EXTRACT_PREDICTION_PROMPT
from agent.core import DataAnalysisAgent


def test_llm():
    """验证 DeepSeek API 连通性。"""
    print("=" * 50)
    print("1. LLM 连通性测试")
    print("=" * 50)

    try:
        resp = chat("你是一个助手，只回复一个单词", "hello")
        print(f"[OK] DeepSeek 响应: {resp[:100]}")
        return True
    except Exception as e:
        print(f"[FAIL] DeepSeek 调用失败: {e}")
        return False


def test_intent():
    """验证意图分类。"""
    print("\n" + "=" * 50)
    print("2. 意图分类测试")
    print("=" * 50)

    cases = [
        ("帮我清洗一下数据，总成本30万后台消耗32.8", "reelclean"),
        ("预测明天排片，封神2占17.6%大盘42万", "prediction"),
        ("看看这两个文件的数据 https://xxx.xlsx", "feishu_excel"),
        ("你好", "unknown"),
        ("今天天气不错", "unknown"),
    ]

    passed = 0
    for text, expected in cases:
        prompt = INTENT_PROMPT.format(user_message=text)
        try:
            raw = chat("返回纯 JSON。", prompt)
            result = json.loads(raw)
            actual = result.get("intent", "?")
            ok = actual == expected
            status = "[OK]" if ok else "[FAIL]"
            print(f"{status} \"{text[:40]}...\" → {actual} (期望 {expected})")
            if ok:
                passed += 1
        except Exception as e:
            print(f"[FAIL] \"{text[:40]}...\" → 异常: {e}")

    print(f"\n意图分类: {passed}/{len(cases)} 通过")


def test_extract():
    """验证参数提取。"""
    print("\n" + "=" * 50)
    print("3. 参数提取测试")
    print("=" * 50)

    # ReelClean 参数
    text = "D8是4.4，后台消耗32.8%，总成本300000，上一时段83.4"
    prompt = EXTRACT_REELCLEAN_PROMPT.format(user_message=text)
    try:
        raw = chat("返回纯 JSON。", prompt)
        result = json.loads(raw)
        params = result.get("params", {})
        print(f"[OK] ReelClean: {json.dumps(params, ensure_ascii=False)}")
        assert params.get("total_cost") == 300000, f"total_cost 应为 300000 实际 {params.get('total_cost')}"
        assert params.get("backend_consume") == 32.8
        assert params.get("prev_actual") == 83.4
        assert params.get("d8_pct") == 4.4
        print("   所有断言通过 OK")
    except Exception as e:
        print(f"[FAIL] ReelClean 提取失败: {e}")

    # Prediction 参数
    text = "预测6月15号排片，封神2:17.6%，哪吒=8.2%，大盘42万场"
    prompt = EXTRACT_PREDICTION_PROMPT.format(user_message=text, today="2026-06-10")
    try:
        raw = chat("返回纯 JSON。", prompt)
        result = json.loads(raw)
        params = result.get("params", {})
        print(f"[OK] Prediction: {json.dumps(params, ensure_ascii=False)}")
        assert params.get("dapan_total") == 420000
        assert len(params.get("movies", [])) == 2
        print("   所有断言通过 OK")
    except Exception as e:
        print(f"[FAIL] Prediction 提取失败: {e}")


def test_agent_flow():
    """验证 Agent 完整流程（不含工具执行）。"""
    print("\n" + "=" * 50)
    print("4. Agent 路由流程测试")
    print("=" * 50)

    agent = DataAnalysisAgent()

    # 模拟对话：第一次消息 → 意图识别
    resp = agent.handle_message("test_user", "test_chat", "帮我清洗数据，总成本30万")
    print(f"[意图识别] {resp['text'][:100]}...")
    assert not resp["done"], "第一次应返回追问"

    # 第二次消息 → 补充参数
    resp = agent.handle_message("test_user", "test_chat", "后台消耗32.8，上一时段83.4，D8 4.4")
    print(f"[参数补充] {resp['text'][:100]}...")

    print("\nAgent 流程验证完成 OK")


if __name__ == "__main__":
    print("DataAnalysis-Agent 验证脚本")
    print("-" * 50)

    if not test_llm():
        print("\n[STOP] LLM 不可用，停止测试。请检查 DEEPSEEK_API_KEY。")
        sys.exit(1)

    test_intent()
    test_extract()
    test_agent_flow()

    print("\n" + "=" * 50)
    print("验证完毕")
