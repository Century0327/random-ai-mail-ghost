#!/usr/bin/env python3
"""手动生成日程脚本 - 供 GitHub Action 调用"""
import os
import sys
import json
import re
import requests
from datetime import datetime

def main():
    character = os.environ.get("CHARACTER", "maodie")
    mode = os.environ.get("MODE", "full")
    print(f"=== 开始生成日程: {character} (模式: {mode}) ===")
    
    # 读取AI配置
    api_key = os.environ.get("AI_API_KEY", "")
    api_url = os.environ.get("AI_API_URL", "")
    model = os.environ.get("AI_MODEL", "")
    
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

每条日程包含：
- time: 时间（如 "08:00"）
- activity: 活动描述（15字以内）
- location: 地点（5字以内）
- thought: 内心想法（20字以内）

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
        
        # 标记已过时间的日程为完成
        for item in schedule_items:
            item.setdefault("done", False)
            t = item.get("time", "00:00")
            try:
                h, m = map(int, t.split(":"))
                total = h * 60 + m
                if total < now_total:
                    item["done"] = True
            except:
                pass
        
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
    
    # 打印所有日程
    print("\n--- 完整日程 ---")
    for item in final_items:
        done_mark = "✓" if item.get("done") else "○"
        print(f"  {done_mark} {item['time']} - {item['activity']} @ {item.get('location', '')}")

if __name__ == "__main__":
    main()