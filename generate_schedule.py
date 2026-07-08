#!/usr/bin/env python3
"""手动生成日程脚本 - 供 GitHub Action 调用"""
import os
import sys
import json
import re
import requests
from datetime import datetime

def main():
    character = os.environ.get("CHARACTER", "kitty")
    mode = os.environ.get("MODE", "full")
    print(f"=== 开始生成日程: {character} (模式: {mode}) ===")
    
    # 读取AI配置：key 从环境变量（支持 key1/key2/key3），供应商/模型从 config.py
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import AI_PROVIDER, AI_MODEL, AI_CUSTOM_URL, AI_KEY_SELECTOR
    
    api_key = os.environ.get(f"AI_API_KEY_{AI_KEY_SELECTOR}", os.environ.get("AI_API_KEY", ""))
    
    AI_PROVIDER_URLS = {
        "siliconflow": "https://api.siliconflow.cn/v1/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "moonshot": "https://api.moonshot.cn/v1/chat/completions",
        "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "deepseek": "https://api.deepseek.com/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    }
    
    if AI_PROVIDER == "custom":
        api_url = AI_CUSTOM_URL
    else:
        api_url = AI_PROVIDER_URLS.get(AI_PROVIDER, AI_PROVIDER_URLS["siliconflow"])
    
    model = AI_MODEL
    
    print(f"[DEBUG] AI_API_KEY: {'***' if api_key else '未设置'}")
    print(f"[DEBUG] AI_API_URL: {api_url}")
    print(f"[DEBUG] AI_MODEL: {model}")
    
    if not api_key or not api_url or not model:
        print("[ERROR] AI API 未配置，请设置 AI_API_KEY、AI_API_URL、AI_MODEL")
        sys.exit(1)
    
    # 读取人设
    script_dir = os.path.dirname(os.path.abspath(__file__))
    persona_path = os.path.join(script_dir, "personas", f"{character}.md")
    
    persona_text = ""
    persona_name = character
    if os.path.exists(persona_path):
        with open(persona_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = [l for l in content.splitlines() if not l.startswith("#")]
        persona_text = "\n".join(lines).strip()
        persona_name = character
        print(f"[DEBUG] 人设文件路径: {persona_path}")
        print(f"[DEBUG] 人设内容长度: {len(persona_text)}字")
    else:
        print(f"[WARN] 未找到人设文件: {persona_path}，使用默认人设")
        persona_text = "一只可爱的小猫，性格温柔，喜欢睡觉和玩毛线球。"
    
    print(f"[1/5] 人设已加载: {persona_name}")
    
    # 读取上次日程
    data_dir = os.path.join(script_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    schedules_path = os.path.join(data_dir, "schedules.json")
    
    print(f"[DEBUG] 日程文件路径: {schedules_path}")
    
    all_schedules = {}
    if os.path.exists(schedules_path):
        with open(schedules_path, "r", encoding="utf-8") as f:
            all_schedules = json.load(f)
        print(f"[DEBUG] 已读取历史日程，共 {len(all_schedules)} 个角色")
    print(f"[2/5] 已读取历史日程数据")
    
    # 读取近期信件
    letters_path = os.path.join(data_dir, "letters.json")
    recent_letters = []
    if os.path.exists(letters_path):
        with open(letters_path, "r", encoding="utf-8") as f:
            all_letters = json.load(f)
        if isinstance(all_letters, list):
            char_letters = [l for l in all_letters if l.get("character_id") == character]
            char_letters.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            recent_letters = char_letters[:5]
        print(f"[DEBUG] 信件文件路径: {letters_path}，找到 {len(recent_letters)} 封相关信件")
    print(f"[3/5] 已读取近期信件: {len(recent_letters)}封")
    
    # 构建提示词
    today = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H:%M")
    
    print(f"[DEBUG] 当前日期: {today}")
    print(f"[DEBUG] 当前时间: {current_time}")
    
    letter_summary = ""
    if recent_letters:
        letter_summary = "近期收到的信件摘要：\n"
        for i, letter in enumerate(recent_letters[:3]):
            subject = letter.get("subject", "无主题")
            body = letter.get("body", "")[:80]
            letter_summary += f"{i+1}. 《{subject}》: {body}...\n"
    
    # 获取上次日程
    prev_schedule_text = ""
    char_schedules = all_schedules.get(character, {})
    if isinstance(char_schedules, dict):
        dates = sorted(char_schedules.keys(), reverse=True)
        if dates:
            prev_date = dates[0]
            prev_items = char_schedules[prev_date].get("items", [])
            prev_schedule_text = f"上次日程（{prev_date}）：\n"
            for item in prev_items[:5]:
                done_mark = "[已完成]" if item.get("done") else "[未完成]"
                prev_schedule_text += f"- {item.get('time', '??:??')} {item.get('activity', '')} {done_mark}\n"
    
    prompt = f"""请为角色'{persona_name}'生成今天（{today}）的日程安排。

角色设定：
{persona_text[:800]}

{prev_schedule_text}

{letter_summary}

当前时间：{current_time}

请生成 8-12 条日程，时间跨度覆盖全天（从早上起床到晚上睡觉）。
注意：
1. 必须生成完整一天的日程，过去的时间也要有
2. 日程要符合角色性格
3. 可以参考近期信件内容，信件会影响角色的心情和想法
4. 活动要多样化，包括休息、进食、玩耍、发呆等日常行为
5. 重要：activity 活动描述必须使用现在时或将来时，绝对不能使用过去时、完成时（如"吃了"、"睡了"、"看完了"等），因为这是计划日程，不是已发生的记录
6. 重要：activity 中不能出现感受描述（如"心满意足"、"很开心"、"好舒服"等），感受和心情只能放在 thought 内心想法里

每条日程包含：
- time: 时间（如 "08:00"）
- activity: 活动描述（15字以内，现在时/将来时，不含感受）
- location: 地点（5字以内）
- thought: 内心想法（20字以内，可以有感受）

请只返回 JSON 数组格式，不要其他文字。例如：
[
  {{"time": "07:00", "activity": "伸懒腰起床", "location": "猫窝", "thought": "新的一天开始啦"}},
  {{"time": "08:30", "activity": "吃早餐", "location": "食盆旁", "thought": "今天的小鱼干真香"}}
]
"""
    
    print(f"[DEBUG] 提示词长度: {len(prompt)}字")
    print(f"[4/5] 正在调用 AI 生成...")
    
    # 调用AI API
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个日程规划助手，擅长根据角色性格生成自然、有趣的日程安排。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "max_tokens": 1500
    }
    
    try:
        print(f"[DEBUG] 发送请求到: {api_url}")
        print(f"[DEBUG] 请求模型: {model}")
        
        from urllib3.util.retry import Retry
        from requests.adapters import HTTPAdapter
        
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        resp = session.post(api_url, headers=headers, json=payload, timeout=120)
        print(f"[DEBUG] HTTP 状态码: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"[ERROR] HTTP 错误: {resp.status_code}")
            print(f"[ERROR] 响应内容: {resp.text[:500]}")
            sys.exit(1)
            
        data = resp.json()
        ai_response = data["choices"][0]["message"]["content"].strip()
        print(f"[DEBUG] AI 响应长度: {len(ai_response)}字")
        print(f"[DEBUG] AI 响应前200字: {ai_response[:200]}")
        
    except Exception as e:
        print(f"[ERROR] AI 调用失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 解析JSON
    schedule_items = []
    json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
    if json_match:
        print(f"[DEBUG] 找到 JSON 数组，长度: {len(json_match.group())}")
        try:
            schedule_items = json.loads(json_match.group())
            print(f"[DEBUG] JSON 解析成功，共 {len(schedule_items)} 条")
        except Exception as e:
            print(f"[ERROR] JSON 解析失败: {e}")
            print(f"[ERROR] AI 返回完整内容:\n{ai_response}")
    
    if not schedule_items:
        print("[ERROR] 未能解析出有效日程")
        sys.exit(1)
    
    print(f"[5/5] 生成成功，共 {len(schedule_items)} 条日程")
    
    # 按时间排序
    schedule_items.sort(key=lambda x: x.get("time", ""))
    
    # 获取当前时间（用于判断已过时）
    now_hour = datetime.now().hour
    now_min = datetime.now().minute
    now_total = now_hour * 60 + now_min
    
    final_items = []
    
    if mode == "future":
        # 模式：只生成未来日程，保留已过时的
        print(f"[DEBUG] 模式: 只生成未来日程")
        
        # 检查是否已有今日日程，如果有，保留已过时的部分
        existing_items = []
        char_schedules = all_schedules.get(character, {})
        if isinstance(char_schedules, dict) and today in char_schedules:
            existing_items = char_schedules[today].get("items", [])
            print(f"[DEBUG] 找到今日已有日程，共 {len(existing_items)} 条")
        
        # 合并：保留已过时的日程，用新生成的替换未过时的
        existing_done_times = set()
        
        # 收集已过时的时间点
        for item in existing_items:
            t = item.get("time", "00:00")
            try:
                h, m = map(int, t.split(":"))
                total = h * 60 + m
                if total < now_total:
                    existing_done_times.add(t)
                    final_items.append(item)
                    print(f"[DEBUG] 保留已过时日程: {t} - {item.get('activity', '')}")
            except:
                pass
        
        # 添加新生成的未过时日程（跳过已保留的时间点）
        for item in schedule_items:
            t = item.get("time", "00:00")
            if t in existing_done_times:
                continue
            
            # 标记为未完成
            item.setdefault("done", False)
            
            # 计算时间是否已过
            try:
                h, m = map(int, t.split(":"))
                total = h * 60 + m
                if total < now_total:
                    item["done"] = True
            except:
                pass
            
            final_items.append(item)
            done_mark = "✓" if item.get("done") else "○"
            print(f"[DEBUG] 添加新日程: {done_mark} {t} - {item.get('activity', '')}")
    else:
        # 模式：生成完整一天（默认）
        print(f"[DEBUG] 模式: 生成完整一天")
        
        # 不自动标记完成状态，让用户手动标记
        # 过去的时间默认也是未完成，用户可以手动勾选完成
        for item in schedule_items:
            item.setdefault("done", False)
        
        final_items = schedule_items
    
    # 按时间重新排序
    final_items.sort(key=lambda x: x.get("time", ""))
    
    # 保存
    if character not in all_schedules or not isinstance(all_schedules[character], dict):
        all_schedules[character] = {}
    all_schedules[character][today] = {
        "items": final_items,
        "generated_at": datetime.now().isoformat()
    }
    
    with open(schedules_path, "w", encoding="utf-8") as f:
        json.dump(all_schedules, f, indent=2, ensure_ascii=False)
    
    print(f"=== 已保存到 data/schedules.json ===")
    print(f"日期: {today}")
    print(f"角色: {character}")
    print(f"日程数: {len(final_items)}")
    
    # 如果配置了数据库，也保存到数据库
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        print("[DB] 检测到 DATABASE_URL，保存到数据库...")
        try:
            import psycopg2
            conn = psycopg2.connect(database_url, sslmode="require")
            cur = conn.cursor()
            
            # 先删除今天的旧数据
            cur.execute("DELETE FROM schedules WHERE character_id = %s AND date = %s", (character, today))
            print(f"[DB] 已删除旧数据 {cur.rowcount} 条")
            
            # 插入新数据
            for item in final_items:
                cur.execute(
                    "INSERT INTO schedules (character_id, date, time, activity, location, thought, done) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (character, today, item.get("time", "00:00"), item.get("activity", ""), item.get("location", ""), item.get("thought", ""), item.get("done", False))
                )
            conn.commit()
            print(f"[DB] 成功插入 {len(final_items)} 条日程")
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] 数据库保存失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("[DB] 未配置 DATABASE_URL，跳过数据库保存")
    
    # 打印所有日程
    print("\n--- 完整日程 ---")
    for item in final_items:
        done_mark = "✓" if item.get("done") else "○"
        print(f"  {done_mark} {item['time']} - {item['activity']} @ {item.get('location', '')}")

if __name__ == "__main__":
    main()