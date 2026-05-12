import vk_api
import json
import os
import time
import threading
import re
import random
from datetime import datetime, timedelta
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from flask import Flask
from threading import Thread

# ==================== ВЕБ-СЕРВЕР ДЛЯ ХОСТИНГА ====================
app = Flask('')
@app.route('/')
def home():
    return "✅ Бот работает"

def run_web():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run_web, daemon=True)
    t.start()

keep_alive()

# ==================== НАСТРОЙКИ ====================
TOKEN = "vk1.a.yRwxK8Z3G0kPmkO_aylMbQQH2Z-JLPT3QlJIu9clvcjrU07uir28755AQ3Lkjp5M_KDxGi75qY2BdT5wJSPil5X8bH64XhY0gEa0_HWLwplgJa8hWcJaJNx37CxGL2UVHYBD9CK3yauwb6iySm5ncauGaW5gXxVCatEsK2cyUMIL0btfyVWv-VxKY2VH4ZORepzKBCWcboHK4NHlgSPevg"
GROUP_ID = 238578496
OWNER_ID = 621761287
DATA_FILE = "bot_data.json"

DEFAULT_ROLES = {
    100: "Владелец",
    80: "Главный Администратор",
    60: "Администратор",
    40: "Модератор",
    20: "Младший модератор"
}
DEFAULT_ROLE_NAMES = list(DEFAULT_ROLES.values())
PROTECTED_ROLES = DEFAULT_ROLE_NAMES

# ==================== ЗАГРУЗКА / СОХРАНЕНИЕ ДАННЫХ ====================
def load_data():
    default_data = {
        "active_chats": {}, "muted": {}, "banned": {}, "global_restricted": [],
        "warnings": {}, "user_stats": {}, "nicknames": {}, "roles": {}, "user_roles": {},
        "sys_roles": {}, "vip_users": [], "tickets": [], "next_ticket_id": 1,
        "marriages": {}, "marriage_proposals": {}, "divorce_requests": {},
        "spam_running": False, "user_names_cache": {}
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in default_data.items():
                if k not in loaded:
                    loaded[k] = v
            return loaded
        except:
            return default_data
    return default_data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load_data()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_user_name(user_id):
    if str(user_id) in data["user_names_cache"]:
        return data["user_names_cache"][str(user_id)]
    try:
        user = vk.users.get(user_ids=user_id)
        if user:
            name = f"{user[0]['first_name']} {user[0]['last_name']}"
            data["user_names_cache"][str(user_id)] = name
            save_data(data)
            return name
    except:
        pass
    return f"id{user_id}"

def get_user_mention(user_id):
    return f"[id{user_id}|{get_user_name(user_id)}]"

def get_chat_title(peer_id):
    try:
        conv = vk.messages.getConversationsById(peer_ids=peer_id)
        if conv['items']:
            return conv['items'][0].get('chat_settings', {}).get('title', f"Беседа {peer_id}")
    except:
        pass
    return f"Беседа {peer_id}"

def get_user_priority(peer_id, user_id):
    role = get_user_role(peer_id, user_id)
    return get_role_priority(peer_id, role)

def check_priority(actor_id, peer_id, required, action_name):
    actor_priority = get_user_priority(peer_id, actor_id)
    if actor_priority >= required:
        return True
    send_message(peer_id, f"❌ *Недостаточно прав!*\n━━━━━━━━━━━━━━━━━\n⚙️ Действие: `{action_name}`\n👤 Ваш приоритет: `{actor_priority}`\n🔒 Требуется приоритет: `{required}`")
    return False

def get_role_priority(peer_id, role_name):
    return data["roles"].get(str(peer_id), {}).get(role_name, -1)

def get_user_role(peer_id, user_id):
    return data["user_roles"].get(str(peer_id), {}).get(str(user_id), "Пользователь")

def set_user_role(peer_id, user_id, role_name):
    if str(peer_id) not in data["user_roles"]:
        data["user_roles"][str(peer_id)] = {}
    if role_name is None:
        if str(user_id) in data["user_roles"][str(peer_id)]:
            del data["user_roles"][str(peer_id)][str(user_id)]
    else:
        data["user_roles"][str(peer_id)][str(user_id)] = role_name
    save_data(data)

def get_all_roles(peer_id):
    return data["roles"].get(str(peer_id), {})

def find_role_by_priority(peer_id, priority):
    for name, prio in get_all_roles(peer_id).items():
        if prio == priority:
            return name
    return None

def init_default_roles(peer_id):
    peer_str = str(peer_id)
    if peer_str not in data["roles"]:
        data["roles"][peer_str] = {}
    need_save = False
    for priority, role_name in DEFAULT_ROLES.items():
        if role_name not in data["roles"][peer_str]:
            data["roles"][peer_str][role_name] = priority
            need_save = True
    if need_save:
        save_data(data)

def ensure_owner_role(peer_id):
    try:
        conv = vk.messages.getConversationsById(peer_ids=peer_id)
        if not conv['items']:
            return
        owner_id = conv['items'][0].get('chat_settings', {}).get('owner_id')
        if not owner_id:
            return
        if get_user_role(peer_id, owner_id) == "Пользователь":
            set_user_role(peer_id, owner_id, "Владелец")
    except:
        pass

def is_chat_active(peer_id):
    return data["active_chats"].get(str(peer_id), False)

def set_chat_active(peer_id, active):
    data["active_chats"][str(peer_id)] = active
    save_data(data)

def create_role(peer_id, role_name, priority):
    peer_str = str(peer_id)
    if peer_str not in data["roles"]:
        data["roles"][peer_str] = {}
    data["roles"][peer_str][role_name] = priority
    save_data(data)

def delete_role(peer_id, role_name):
    if role_name in PROTECTED_ROLES:
        return False
    peer_str = str(peer_id)
    if peer_str in data["roles"] and role_name in data["roles"][peer_str]:
        del data["roles"][peer_str][role_name]
        save_data(data)
        return True
    return False

def get_mute_end(peer_id, user_id):
    key = f"{peer_id},{user_id}"
    ts = data["muted"].get(key)
    return datetime.fromtimestamp(ts) if ts else None

def set_mute(peer_id, user_id, minutes):
    key = f"{peer_id},{user_id}"
    end = datetime.now() + timedelta(minutes=minutes)
    data["muted"][key] = end.timestamp()
    save_data(data)

def remove_mute(peer_id, user_id):
    key = f"{peer_id},{user_id}"
    if key in data["muted"]:
        del data["muted"][key]
        save_data(data)

def is_banned(peer_id, user_id):
    return data["banned"].get(f"{peer_id},{user_id}", False)

def set_ban(peer_id, user_id, banned=True):
    key = f"{peer_id},{user_id}"
    if banned:
        data["banned"][key] = True
    else:
        if key in data["banned"]:
            del data["banned"][key]
    save_data(data)

def get_warnings(peer_id, user_id):
    return data["warnings"].get(f"{peer_id},{user_id}", 0)

def add_warning(peer_id, user_id, delta=1):
    key = f"{peer_id},{user_id}"
    new_val = data["warnings"].get(key, 0) + delta
    if new_val <= 0:
        if key in data["warnings"]:
            del data["warnings"][key]
    else:
        data["warnings"][key] = new_val
    save_data(data)
    return new_val

def get_nick(peer_id, user_id):
    return data["nicknames"].get(f"{peer_id},{user_id}")

def set_nick(peer_id, user_id, nick):
    data["nicknames"][f"{peer_id},{user_id}"] = nick
    save_data(data)

def remove_nick(peer_id, user_id):
    key = f"{peer_id},{user_id}"
    if key in data["nicknames"]:
        del data["nicknames"][key]
        save_data(data)

def get_all_nicks(peer_id):
    result = {}
    prefix = f"{peer_id},"
    for k, v in data["nicknames"].items():
        if k.startswith(prefix):
            uid = int(k.split(",")[1])
            result[uid] = v
    return result

def can_moderate(actor_id, target_id, peer_id, action="view"):
    if actor_id == OWNER_ID:
        return True
    actor_priority = get_user_priority(peer_id, actor_id)
    required = {
        "view": 0, "nick": 20, "mute": 20, "unmute": 20,
        "warn": 40, "kick": 40, "role": 40, "ban": 60,
        "zov": 60, "masskick": 60
    }.get(action, 0)
    if actor_priority < required:
        return False
    if action in ("mute", "warn", "kick", "ban", "role", "masskick"):
        target_priority = get_user_priority(peer_id, target_id)
        if actor_priority <= target_priority:
            return False
    return True

def can_assign_role(actor_id, target_id, role_name, peer_id):
    if actor_id == OWNER_ID:
        return True
    if actor_id == target_id:
        return False
    actor_priority = get_user_priority(peer_id, actor_id)
    target_priority = get_user_priority(peer_id, target_id)
    role_priority = get_role_priority(peer_id, role_name)
    if actor_priority <= target_priority:
        return False
    if role_priority >= actor_priority:
        return False
    return actor_priority >= 40

def get_sys_role(user_id):
    return data["sys_roles"].get(str(user_id), 0)

def set_sys_role(user_id, level):
    if level <= 0:
        if str(user_id) in data["sys_roles"]:
            del data["sys_roles"][str(user_id)]
    else:
        data["sys_roles"][str(user_id)] = min(level, 10)
    save_data(data)

def can_use_sys_command(user_id, required_level):
    if user_id == OWNER_ID:
        return True
    return get_sys_role(user_id) >= required_level

def create_complaint(user_id, peer_id, text):
    cid = data["next_ticket_id"]
    data["tickets"].append({"id": cid, "user_id": user_id, "peer_id": peer_id, "text": text, "status": "open", "created": datetime.now().timestamp()})
    data["next_ticket_id"] += 1
    save_data(data)
    return cid

def answer_complaint(cid, answer_text):
    for t in data["tickets"]:
        if t["id"] == cid:
            t["status"] = "answered"
            save_data(data)
            try:
                vk.messages.send(user_id=t["user_id"], message=f"📬 Ответ на жалобу #{cid}:\n{answer_text}", random_id=0)
            except:
                pass
            return True
    return False

BADWORDS = set(["бля", "блять", "хуй", "пизда", "ебать", "нах", "хер", "залупа", "мудак", "говно", "сука", "тварь", "пидор", "гандон", "долбоеб", "уебок", "fuck", "shit", "bitch", "dick", "asshole", "cunt"])

def count_badwords(txt):
    text_lower = txt.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    return sum(1 for w in words if w in BADWORDS)

def update_stats(peer_id, user_id, text, attachments):
    if "user_stats" not in data:
        data["user_stats"] = {}
    key = f"{peer_id},{user_id}"
    if key not in data["user_stats"]:
        data["user_stats"][key] = {"msgs": 0, "chars": 0, "badwords": 0, "photos": 0, "videos": 0, "voices": 0}
    stats = data["user_stats"][key]
    stats["msgs"] += 1
    stats["chars"] += len(text)
    stats["badwords"] += count_badwords(text)
    if attachments:
        for att in attachments:
            if att.get('type') == 'photo':
                stats["photos"] += 1
            elif att.get('type') == 'video':
                stats["videos"] += 1
            elif att.get('type') == 'audio_message':
                stats["voices"] += 1
    save_data(data)

def get_user_stats(peer_id, user_id):
    if "user_stats" not in data:
        data["user_stats"] = {}
    key = f"{peer_id},{user_id}"
    return data["user_stats"].get(key, {"msgs": 0, "chars": 0, "badwords": 0, "photos": 0, "videos": 0, "voices": 0})

def format_profile(peer_id, user_id):
    nick = get_nick(peer_id, user_id) or "нет"
    role = get_user_role(peer_id, user_id)
    warns = get_warnings(peer_id, user_id)
    stats = get_user_stats(peer_id, user_id)
    mention = get_user_mention(user_id)
    return f"""🔰 *Профиль пользователя* {mention}
━━━━━━━━━━━━━━━━━
🔗 *Ник:* {nick}
👮 *Роль:* {role}
⚠️ *Предупреждений:* {warns}
━━━━━━━━━━━━━━━━━
📝 *Статистика сообщений:*
➖ Всего: {stats['msgs']}
➖ Символов: {stats['chars']}
➖ Нецензурных слов: {stats['badwords']}
➖ Фото: {stats['photos']}
➖ Видео: {stats['videos']}
➖ Голосовые: {stats['voices']}"""

def get_user_activity_score(peer_id, user_id):
    stats = get_user_stats(peer_id, user_id)
    return stats['msgs'] + stats['photos'] * 2 + stats['videos'] * 3 - stats['badwords'] * 5

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

def send_message(peer_id, text, reply_to=None):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=0, reply_to=reply_to)
    except Exception as e:
        print(f"Ошибка: {e}")

def kick_user(peer_id, user_id):
    try:
        vk.messages.removeChatUser(chat_id=peer_id - 2000000000, member_id=user_id)
        return True
    except:
        return False

def mute_user(peer_id, user_id, minutes):
    set_mute(peer_id, user_id, minutes)
    send_message(peer_id, f"🔇 {minutes} мин. мута для {get_user_mention(user_id)}")

def unmute_user(peer_id, user_id):
    remove_mute(peer_id, user_id)
    send_message(peer_id, f"🎤 Снят мут с {get_user_mention(user_id)}")

def ban_user(peer_id, user_id):
    set_ban(peer_id, user_id, True)
    kick_user(peer_id, user_id)
    send_message(peer_id, f"🚫 {get_user_mention(user_id)} забанен и кикнут")

def unban_user(peer_id, user_id):
    set_ban(peer_id, user_id, False)
    send_message(peer_id, f"✅ Снят бан с {get_user_mention(user_id)}")

def give_warning(peer_id, user_id, reason=""):
    count = add_warning(peer_id, user_id, 1)
    msg = f"⚠️ *Предупреждение* {count}/3 для {get_user_mention(user_id)}.\n➖ Причина: {reason}"
    if count >= 3:
        kick_user(peer_id, user_id)
        msg += "\n➖➖➖➖➖➖➖➖➖\n❗ *3 предупреждения → кик!*"
        add_warning(peer_id, user_id, -3)
    send_message(peer_id, msg)

def get_chat_members(peer_id):
    try:
        members = vk.messages.getConversationMembers(peer_id=peer_id)
        return [m['member_id'] for m in members['items'] if m['member_id'] > 0]
    except:
        return []

def zov_call(peer_id, actor_id):
    members = get_chat_members(peer_id)
    members = [m for m in members if m not in (-GROUP_ID, actor_id)]
    if not members:
        send_message(peer_id, "Нет участников для созыва.")
        return
    send_message(peer_id, f"🔔 *Созыв от* {get_user_mention(actor_id)}\n➖ Всего участников: {len(members)}")
    for uid in members:
        try:
            vk.messages.send(peer_id=peer_id, message=f"{get_user_mention(uid)}, вы были пингованы!", random_id=0)
            time.sleep(0.3)
        except:
            pass
    send_message(peer_id, "✅ *Созыв завершён!*")

def broadcast_to_all_chats(message):
    full = f"📢 *Важное уведомление от бота.*\n━━━━━━━━━━━━━━━━━\n{message}"
    sent = 0
    for pid, active in data["active_chats"].items():
        if active:
            try:
                send_message(int(pid), full)
                sent += 1
                time.sleep(0.3)
            except:
                pass
    return sent

def get_marriages(peer_id):
    return data["marriages"].get(str(peer_id), {})

def add_marriage(peer_id, user1, user2):
    peer_str = str(peer_id)
    if peer_str not in data["marriages"]:
        data["marriages"][peer_str] = {}
    key = f"{min(user1,user2)},{max(user1,user2)}"
    data["marriages"][peer_str][key] = {"users": [user1, user2], "date": datetime.now().timestamp()}
    save_data(data)

def remove_marriage(peer_id, user1, user2):
    peer_str = str(peer_id)
    key = f"{min(user1,user2)},{max(user1,user2)}"
    if peer_str in data["marriages"] and key in data["marriages"][peer_str]:
        del data["marriages"][peer_str][key]
        save_data(data)
        return True
    return False

def is_married(peer_id, user_id):
    for m in get_marriages(peer_id).values():
        if user_id in m["users"]:
            return m["users"]
    return None

def add_proposal(peer_id, proposer_id, target_id, expires_minutes=5):
    peer_str = str(peer_id)
    if peer_str not in data["marriage_proposals"]:
        data["marriage_proposals"][peer_str] = {}
    data["marriage_proposals"][peer_str][str(proposer_id)] = {"target_id": target_id, "expires": (datetime.now() + timedelta(minutes=expires_minutes)).timestamp()}
    save_data(data)

def remove_proposal(peer_id, proposer_id):
    peer_str = str(peer_id)
    if peer_str in data["marriage_proposals"] and str(proposer_id) in data["marriage_proposals"][peer_str]:
        del data["marriage_proposals"][peer_str][str(proposer_id)]
        save_data(data)

def get_random_joke():
    jokes = [
        "Почему программисты не любят природу? Слишком много багов.",
        "Что говорит один бит другому? Прикрой меня, я устал.",
        "Сколько программистов нужно, чтобы заменить лампочку? Ни одного — это аппаратная проблема.",
        "Почему бота назвали Чат-Менеджер? Потому что он менеджерит чат!",
        "Что будет, если скрестить бота и администратора? Бот-администратор, который пинает сам себя.",
        "Какой самый любимый язык у бота? JSON, он его понимает с полуслова.",
    ]
    return random.choice(jokes)

def calculate_expression(expr):
    try:
        expr = expr.replace(' ', '')
        if not re.match(r'^[\d\+\-\*\/\(\)\.]+$', expr):
            return None
        result = eval(expr)
        return round(result, 2)
    except:
        return None

# ==================== ОСНОВНОЙ ЦИКЛ ====================
print("✅ Бот запущен. Команды: /help или !помощь")

for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        msg = event.object.message
        peer_id = msg['peer_id']
        from_id = msg['from_id']
        text = msg.get('text', '').strip()
        lower_text = text.lower()
        attachments = msg.get('attachments', [])

        # ЛИЧНЫЕ СООБЩЕНИЯ
        if peer_id == from_id:
            if from_id != OWNER_ID:
                send_message(peer_id, "🤖 Я работаю только в беседах.\n➖ Добавьте меня в группу, выдайте права администратора и напишите /start")
            continue

        # ПРИВЕТСТВИЕ ПРИ ДОБАВЛЕНИИ БОТА
        if event.object.message.get('action') and event.object.message['action'].get('type') == 'chat_invite_user':
            invited_id = event.object.message['action'].get('member_id')
            if invited_id == -GROUP_ID:
                set_chat_active(peer_id, True)
                init_default_roles(peer_id)
                ensure_owner_role(peer_id)
                send_message(peer_id, "✨ *Привет!* Благодарю что добавили меня в беседу, я вас не подведу❤\n━━━━━━━━━━━━━━━━━\n👑 *Бот создан Павлом Мелентьевым.*\n⚠️ *ВАЖНО:* выдайте боту администратора и напишите `/start`")
                continue

        # ГЛОБАЛЬНЫЕ ОГРАНИЧЕНИЯ
        if from_id in data["global_restricted"]:
            send_message(peer_id, "🚫 Вы глобально заблокированы во всех чатах бота.", reply_to=msg['id'])
            continue

        # СТАТИСТИКА И БАН/МУТ
        update_stats(peer_id, from_id, text, attachments)
        if is_banned(peer_id, from_id):
            send_message(peer_id, "🚫 Вы забанены в этой беседе.", reply_to=msg['id'])
            continue
        mute_end = get_mute_end(peer_id, from_id)
        if mute_end and datetime.now() < mute_end:
            send_message(peer_id, "🔇 Вы замучены.", reply_to=msg['id'])
            continue
        elif mute_end:
            remove_mute(peer_id, from_id)

        if not (lower_text.startswith('/') or lower_text.startswith('!')):
            continue

        raw_cmd = lower_text[1:].strip()
        if not raw_cmd:
            continue
        parts = raw_cmd.split()
        cmd = parts[0]

        # АЛИАСЫ КОМАНД (русские и английские)
        cmd_translate = {
            "help": "помощь", "ping": "пинг", "chatid": "чатид", "stats": "статистика",
            "stat": "статистика", "staff": "стафф", "nick": "ник", "gnick": "гник",
            "rnick": "рник", "nlist": "нлист", "start": "начать", "ai": "ай",
            "kick": "кик", "mute": "мут", "unmute": "размут", "ban": "бан",
            "unban": "разбан", "warn": "варн", "roles": "роли", "role": "роль",
            "report": "репорт", "tickets": "тикеты", "complaint": "жалоба",
            "marry": "брак", "divorce": "развод", "marriages": "браки",
            "yes": "да", "no": "нет", "confirm_divorce": "подтвердить_развод",
            "whoami": "кто я", "newrole": "новаяроль", "delrole": "удалитьроль",
            "zov": "зови", "созыв": "зови", "clear": "очистить", "calculator": "калькулятор",
            "calc": "калькулятор", "time": "время", "joke": "шутка", "weather": "погода",
            "score": "баллы", "points": "баллы", "rating": "баллы"
        }
        if cmd in cmd_translate:
            cmd = cmd_translate[cmd]

        public_commands = ["помощь", "пинг", "чатид", "начать", "репорт", "тикеты", "жалоба",
                           "калькулятор", "время", "шутка", "погода", "баллы", "кто я", "статистика",
                           "стафф", "роли", "нлист", "гник", "брак", "да", "нет", "развод",
                           "подтвердить_развод", "браки"]

        if not is_chat_active(peer_id):
            if cmd not in public_commands and cmd != "начать":
                send_message(peer_id, "⚠️ Бот не активирован.\n➖ Напишите `/start`", reply_to=msg['id'])
                continue
            if cmd == "начать":
                set_chat_active(peer_id, True)
                init_default_roles(peer_id)
                ensure_owner_role(peer_id)
                send_message(peer_id, "✅ *Чат активирован!* Теперь бот работает.")
                continue

        handled = True

        # ==================== ОСНОВНЫЕ КОМАНДЫ ====================
        if cmd == "помощь":
            help_text = """🤖 *Команды бота (русские и английские)*
━━━━━━━━━━━━━━━━━
📌 *Основные:*
/ping — проверить бота
/chatid — ID беседы
/start — активировать бота
/whoami — мой профиль
/stat @user — статистика

📋 *Обращения:*
/report <текст> — жалоба
/complaint <текст> — жалоба владельцу
/tickets — мои жалобы

👑 *Роли:*
/staff — администрация
/roles — список ролей
/role <приоритет/название> @user
/newrole <название> <приоритет>
/delrole <название>

📛 *Ники:*
/nick <ник>, /gnick, /rnick, /nlist

💍 *Браки:*
/marry @user, /yes, /no, /divorce, /confirm_divorce

🔧 *Модерация:*
/mute, /unmute, /warn, /kick, /ban, /unban, /zov, /clear

🧠 *Развлечения:*
/calculator 2+2, /time, /joke, /weather <город>, /score @user

🛡️ *Системные:* /syshelp"""
            send_message(peer_id, help_text)

        elif cmd == "пинг":
            send_message(peer_id, "🏓 *Понг!* Бот работает.")
        elif cmd == "чатид":
            send_message(peer_id, f"🆔 *ID беседы:* `{peer_id}`")
        elif cmd == "кто я":
            send_message(peer_id, format_profile(peer_id, from_id))
        elif cmd == "статистика":
            target = from_id
            if msg.get('reply_message'):
                target = msg['reply_message']['from_id']
            else:
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
            send_message(peer_id, format_profile(peer_id, target))
        elif cmd in ("стафф", "роли"):
            roles_dict = get_all_roles(peer_id)
            if cmd == "стафф":
                lines = ["🏅 *Администрация чата:*"]
                for rname, prio in sorted(roles_dict.items(), key=lambda x: x[1], reverse=True):
                    users = [get_user_mention(int(uid)) for uid, r in data["user_roles"].get(str(peer_id), {}).items() if r == rname]
                    if users:
                        lines.append(f"➖ {rname} (приоритет {prio}): {', '.join(users)}")
                if len(lines) == 1:
                    lines.append("Нет назначенных ролей.")
                send_message(peer_id, "\n".join(lines))
            else:
                lines = ["📜 *Список ролей (приоритет):*"]
                for name, prio in sorted(roles_dict.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"➖ {name} — {prio}")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "нлист":
            nicks = get_all_nicks(peer_id)
            if not nicks:
                send_message(peer_id, "Никнеймов нет.")
            else:
                lines = ["📛 *Список никнеймов:*"]
                for uid, nick in nicks.items():
                    lines.append(f"➖ {get_user_mention(uid)}: {nick}")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "гник":
            target = from_id
            if msg.get('reply_message'):
                target = msg['reply_message']['from_id']
            nick = get_nick(peer_id, target)
            send_message(peer_id, f"🔗 Ник {get_user_mention(target)}: {nick if nick else 'нет'}")
        elif cmd == "репорт" and len(parts) >= 2:
            tid = create_complaint(from_id, peer_id, ' '.join(parts[1:]))
            try:
                vk.messages.send(user_id=OWNER_ID, message=f"📩 *Новая жалоба* #{tid} от {get_user_mention(from_id)}:\n{parts[1]}", random_id=0)
            except:
                pass
            send_message(peer_id, f"✅ *Жалоба #{tid}* отправлена администратору.")
        elif cmd == "тикеты":
            tickets = [t for t in data["tickets"] if t["user_id"] == from_id]
            if not tickets:
                send_message(peer_id, "У вас нет жалоб.")
            else:
                lines = ["📋 *Ваши жалобы:*"]
                for t in tickets:
                    lines.append(f"➖ #{t['id']}: {t['text'][:50]} ({t['status']})")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "жалоба" and len(parts) >= 2:
            tid = create_complaint(from_id, peer_id, ' '.join(parts[1:]))
            try:
                vk.messages.send(user_id=OWNER_ID, message=f"📩 *Жалоба* #{tid} от {get_user_mention(from_id)}:\n{parts[1]}", random_id=0)
            except:
                pass
            send_message(peer_id, f"✅ *Жалоба #{tid}* отправлена владельцу.")
        elif cmd == "калькулятор" and len(parts) >= 2:
            expr = ' '.join(parts[1:])
            res = calculate_expression(expr)
            if res is not None:
                send_message(peer_id, f"🧮 *{expr}* = {res}")
            else:
                send_message(peer_id, "❌ *Ошибка!* Проверьте выражение.")
        elif cmd == "время":
    now = datetime.now() + timedelta(hours=3)
    send_message(peer_id, f"🕐 МСК: {now.strftime('%H:%M:%S')}\n📅 Дата: {now.strftime('%d.%m.%Y')}")
import json
import os
import time
import threading
import re
import random
from datetime import datetime, timedelta
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from flask import Flask
from threading import Thread

# ==================== ВЕБ-СЕРВЕР ДЛЯ ХОСТИНГА ====================
app = Flask('')
@app.route('/')
def home():
    return "✅ Бот работает"
def run_web():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
def keep_alive():
    t = Thread(target=run_web, daemon=True)
    t.start()
keep_alive()

# ==================== НАСТРОЙКИ ====================
TOKEN = "vk1.a.yRwxK8Z3G0kPmkO_aylMbQQH2Z-JLPT3QlJIu9clvcjrU07uir28755AQ3Lkjp5M_KDxGi75qY2BdT5wJSPil5X8bH64XhY0gEa0_HWLwplgJa8hWcJaJNx37CxGL2UVHYBD9CK3yauwb6iySm5ncauGaW5gXxVCatEsK2cyUMIL0btfyVWv-VxKY2VH4ZORepzKBCWcboHK4NHlgSPevg"
GROUP_ID = 238578496
OWNER_ID = 621761287
DATA_FILE = "bot_data.json"

DEFAULT_ROLES = {100: "Владелец", 80: "Главный Администратор", 60: "Администратор", 40: "Модератор", 20: "Младший модератор"}
DEFAULT_ROLE_NAMES = list(DEFAULT_ROLES.values())
PROTECTED_ROLES = DEFAULT_ROLE_NAMES

def load_data():
    default_data = {
        "active_chats": {}, "muted": {}, "banned": {}, "global_restricted": [],
        "warnings": {}, "user_stats": {}, "nicknames": {}, "roles": {}, "user_roles": {},
        "sys_roles": {}, "vip_users": [], "tickets": [], "next_ticket_id": 1,
        "marriages": {}, "marriage_proposals": {}, "divorce_requests": {},
        "spam_running": False, "user_names_cache": {}
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in default_data.items():
                if k not in loaded:
                    loaded[k] = v
            return loaded
        except:
            return default_data
    return default_data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load_data()

def get_user_name(user_id):
    if str(user_id) in data["user_names_cache"]:
        return data["user_names_cache"][str(user_id)]
    try:
        user = vk.users.get(user_ids=user_id)
        if user:
            name = f"{user[0]['first_name']} {user[0]['last_name']}"
            data["user_names_cache"][str(user_id)] = name
            save_data(data)
            return name
    except:
        pass
    return f"id{user_id}"

def get_user_mention(user_id):
    return f"[id{user_id}|{get_user_name(user_id)}]"

def get_chat_title(peer_id):
    try:
        conv = vk.messages.getConversationsById(peer_ids=peer_id)
        if conv['items']:
            return conv['items'][0].get('chat_settings', {}).get('title', f"Беседа {peer_id}")
    except:
        pass
    return f"Беседа {peer_id}"

def get_user_priority(peer_id, user_id):
    role = get_user_role(peer_id, user_id)
    return get_role_priority(peer_id, role)

def get_role_priority(peer_id, role_name):
    return data["roles"].get(str(peer_id), {}).get(role_name, -1)

def get_user_role(peer_id, user_id):
    return data["user_roles"].get(str(peer_id), {}).get(str(user_id), "Пользователь")

def set_user_role(peer_id, user_id, role_name):
    if str(peer_id) not in data["user_roles"]:
        data["user_roles"][str(peer_id)] = {}
    if role_name is None:
        if str(user_id) in data["user_roles"][str(peer_id)]:
            del data["user_roles"][str(peer_id)][str(user_id)]
    else:
        data["user_roles"][str(peer_id)][str(user_id)] = role_name
    save_data(data)

def get_all_roles(peer_id):
    return data["roles"].get(str(peer_id), {})

def find_role_by_priority(peer_id, priority):
    for name, prio in get_all_roles(peer_id).items():
        if prio == priority:
            return name
    return None

def init_default_roles(peer_id):
    peer_str = str(peer_id)
    if peer_str not in data["roles"]:
        data["roles"][peer_str] = {}
    need_save = False
    for priority, role_name in DEFAULT_ROLES.items():
        if role_name not in data["roles"][peer_str]:
            data["roles"][peer_str][role_name] = priority
            need_save = True
    if need_save:
        save_data(data)

def ensure_owner_role(peer_id):
    try:
        conv = vk.messages.getConversationsById(peer_ids=peer_id)
        if not conv['items']:
            return
        owner_id = conv['items'][0].get('chat_settings', {}).get('owner_id')
        if not owner_id:
            return
        if get_user_role(peer_id, owner_id) == "Пользователь":
            set_user_role(peer_id, owner_id, "Владелец")
    except:
        pass

def is_chat_active(peer_id):
    return data["active_chats"].get(str(peer_id), False)

def set_chat_active(peer_id, active):
    data["active_chats"][str(peer_id)] = active
    save_data(data)

def create_role(peer_id, role_name, priority):
    peer_str = str(peer_id)
    if peer_str not in data["roles"]:
        data["roles"][peer_str] = {}
    data["roles"][peer_str][role_name] = priority
    save_data(data)

def delete_role(peer_id, role_name):
    if role_name in PROTECTED_ROLES:
        return False
    peer_str = str(peer_id)
    if peer_str in data["roles"] and role_name in data["roles"][peer_str]:
        del data["roles"][peer_str][role_name]
        save_data(data)
        return True
    return False

def get_mute_end(peer_id, user_id):
    key = f"{peer_id},{user_id}"
    ts = data["muted"].get(key)
    return datetime.fromtimestamp(ts) if ts else None

def set_mute(peer_id, user_id, minutes):
    key = f"{peer_id},{user_id}"
    end = datetime.now() + timedelta(minutes=minutes)
    data["muted"][key] = end.timestamp()
    save_data(data)

def remove_mute(peer_id, user_id):
    key = f"{peer_id},{user_id}"
    if key in data["muted"]:
        del data["muted"][key]
        save_data(data)

def is_banned(peer_id, user_id):
    return data["banned"].get(f"{peer_id},{user_id}", False)

def set_ban(peer_id, user_id, banned=True):
    key = f"{peer_id},{user_id}"
    if banned:
        data["banned"][key] = True
    else:
        if key in data["banned"]:
            del data["banned"][key]
    save_data(data)

def get_warnings(peer_id, user_id):
    return data["warnings"].get(f"{peer_id},{user_id}", 0)

def add_warning(peer_id, user_id, delta=1):
    key = f"{peer_id},{user_id}"
    new_val = data["warnings"].get(key, 0) + delta
    if new_val <= 0:
        if key in data["warnings"]:
            del data["warnings"][key]
    else:
        data["warnings"][key] = new_val
    save_data(data)
    return new_val

def get_nick(peer_id, user_id):
    return data["nicknames"].get(f"{peer_id},{user_id}")

def set_nick(peer_id, user_id, nick):
    data["nicknames"][f"{peer_id},{user_id}"] = nick
    save_data(data)

def remove_nick(peer_id, user_id):
    key = f"{peer_id},{user_id}"
    if key in data["nicknames"]:
        del data["nicknames"][key]
        save_data(data)

def get_all_nicks(peer_id):
    result = {}
    prefix = f"{peer_id},"
    for k, v in data["nicknames"].items():
        if k.startswith(prefix):
            uid = int(k.split(",")[1])
            result[uid] = v
    return result

def can_moderate(actor_id, target_id, peer_id, action="view"):
    if actor_id == OWNER_ID:
        return True
    actor_priority = get_user_priority(peer_id, actor_id)
    required = {"view": 0, "nick": 20, "mute": 20, "unmute": 20, "warn": 40, "kick": 40, "role": 40, "ban": 60, "zov": 60}.get(action, 0)
    if actor_priority < required:
        return False
    if action in ("mute", "warn", "kick", "ban", "role"):
        target_priority = get_user_priority(peer_id, target_id)
        if actor_priority <= target_priority:
            return False
    return True

def can_assign_role(actor_id, target_id, role_name, peer_id):
    if actor_id == OWNER_ID:
        return True
    if actor_id == target_id:
        return False
    actor_priority = get_user_priority(peer_id, actor_id)
    target_priority = get_user_priority(peer_id, target_id)
    role_priority = get_role_priority(peer_id, role_name)
    if actor_priority <= target_priority:
        return False
    if role_priority >= actor_priority:
        return False
    return actor_priority >= 40

def get_sys_role(user_id):
    return data["sys_roles"].get(str(user_id), 0)

def set_sys_role(user_id, level):
    if level <= 0:
        if str(user_id) in data["sys_roles"]:
            del data["sys_roles"][str(user_id)]
    else:
        data["sys_roles"][str(user_id)] = min(level, 10)
    save_data(data)

def can_use_sys_command(user_id, required_level):
    if user_id == OWNER_ID:
        return True
    return get_sys_role(user_id) >= required_level

def create_complaint(user_id, peer_id, text):
    cid = data["next_ticket_id"]
    data["tickets"].append({"id": cid, "user_id": user_id, "peer_id": peer_id, "text": text, "status": "open", "created": datetime.now().timestamp()})
    data["next_ticket_id"] += 1
    save_data(data)
    return cid

def answer_complaint(cid, answer_text):
    for t in data["tickets"]:
        if t["id"] == cid:
            t["status"] = "answered"
            save_data(data)
            try:
                vk.messages.send(user_id=t["user_id"], message=f"📬 Ответ на жалобу #{cid}:\n{answer_text}", random_id=0)
            except:
                pass
            return True
    return False

BADWORDS = set(["бля", "блять", "хуй", "пизда", "ебать", "нах", "хер", "залупа", "мудак", "говно", "сука", "тварь", "пидор", "гандон", "долбоеб", "уебок", "fuck", "shit", "bitch", "dick", "asshole", "cunt"])

def count_badwords(txt):
    text_lower = txt.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    return sum(1 for w in words if w in BADWORDS)

def update_stats(peer_id, user_id, text, attachments):
    if "user_stats" not in data:
        data["user_stats"] = {}
    key = f"{peer_id},{user_id}"
    if key not in data["user_stats"]:
        data["user_stats"][key] = {"msgs": 0, "chars": 0, "badwords": 0, "photos": 0, "videos": 0, "voices": 0}
    stats = data["user_stats"][key]
    stats["msgs"] += 1
    stats["chars"] += len(text)
    stats["badwords"] += count_badwords(text)
    if attachments:
        for att in attachments:
            if att.get('type') == 'photo':
                stats["photos"] += 1
            elif att.get('type') == 'video':
                stats["videos"] += 1
            elif att.get('type') == 'audio_message':
                stats["voices"] += 1
    save_data(data)

def get_user_stats(peer_id, user_id):
    if "user_stats" not in data:
        data["user_stats"] = {}
    key = f"{peer_id},{user_id}"
    return data["user_stats"].get(key, {"msgs": 0, "chars": 0, "badwords": 0, "photos": 0, "videos": 0, "voices": 0})

def format_profile(peer_id, user_id):
    nick = get_nick(peer_id, user_id) or "нет"
    role = get_user_role(peer_id, user_id)
    warns = get_warnings(peer_id, user_id)
    stats = get_user_stats(peer_id, user_id)
    return f"""🔰 Профиль пользователя {get_user_mention(user_id)}
━━━━━━━━━━━━━━━━━
🔗 Ник: {nick}
👮 Роль: {role}
⚠️ Предупреждений: {warns}
━━━━━━━━━━━━━━━━━
📝 Статистика сообщений:
➖ Всего: {stats['msgs']}
➖ Символов: {stats['chars']}
➖ Нецензурных слов: {stats['badwords']}
➖ Фото: {stats['photos']}
➖ Видео: {stats['videos']}
➖ Голосовые: {stats['voices']}"""

def get_user_activity_score(peer_id, user_id):
    stats = get_user_stats(peer_id, user_id)
    return stats['msgs'] + stats['photos'] * 2 + stats['videos'] * 3 - stats['badwords'] * 5

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

def send_message(peer_id, text, reply_to=None):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=0, reply_to=reply_to)
    except Exception as e:
        print(f"Ошибка: {e}")

def kick_user(peer_id, user_id):
    try:
        vk.messages.removeChatUser(chat_id=peer_id - 2000000000, member_id=user_id)
        return True
    except:
        return False

def mute_user(peer_id, user_id, minutes):
    set_mute(peer_id, user_id, minutes)
    send_message(peer_id, f"🔇 {minutes} мин. мута для {get_user_mention(user_id)}")

def unmute_user(peer_id, user_id):
    remove_mute(peer_id, user_id)
    send_message(peer_id, f"🎤 Снят мут с {get_user_mention(user_id)}")

def ban_user(peer_id, user_id):
    set_ban(peer_id, user_id, True)
    kick_user(peer_id, user_id)
    send_message(peer_id, f"🚫 {get_user_mention(user_id)} забанен и кикнут")

def unban_user(peer_id, user_id):
    set_ban(peer_id, user_id, False)
    send_message(peer_id, f"✅ Снят бан с {get_user_mention(user_id)}")

def give_warning(peer_id, user_id, reason=""):
    count = add_warning(peer_id, user_id, 1)
    msg = f"⚠️ Предупреждение {count}/3 для {get_user_mention(user_id)}.\n➖ Причина: {reason}"
    if count >= 3:
        kick_user(peer_id, user_id)
        msg += "\n➖➖➖➖➖➖➖➖➖\n❗ 3 предупреждения → кик!"
        add_warning(peer_id, user_id, -3)
    send_message(peer_id, msg)

def get_chat_members(peer_id):
    try:
        members = vk.messages.getConversationMembers(peer_id=peer_id)
        return [m['member_id'] for m in members['items'] if m['member_id'] > 0]
    except:
        return []

def zov_call(peer_id, actor_id):
    members = get_chat_members(peer_id)
    members = [m for m in members if m not in (-GROUP_ID, actor_id)]
    if not members:
        send_message(peer_id, "Нет участников для созыва.")
        return
    send_message(peer_id, f"🔔 Созыв от {get_user_mention(actor_id)}\n➖ Всего участников: {len(members)}")
    for uid in members:
        try:
            vk.messages.send(peer_id=peer_id, message=f"{get_user_mention(uid)}, вы были пингованы!", random_id=0)
            time.sleep(0.3)
        except:
            pass
    send_message(peer_id, "✅ Созыв завершён!")

def broadcast_to_all_chats(message):
    full = f"📢 Важное уведомление от бота.\n━━━━━━━━━━━━━━━━━\n{message}"
    sent = 0
    for pid, active in data["active_chats"].items():
        if active:
            try:
                send_message(int(pid), full)
                sent += 1
                time.sleep(0.3)
            except:
                pass
    return sent

def get_marriages(peer_id):
    return data["marriages"].get(str(peer_id), {})

def add_marriage(peer_id, user1, user2):
    peer_str = str(peer_id)
    if peer_str not in data["marriages"]:
        data["marriages"][peer_str] = {}
    key = f"{min(user1,user2)},{max(user1,user2)}"
    data["marriages"][peer_str][key] = {"users": [user1, user2], "date": datetime.now().timestamp()}
    save_data(data)

def remove_marriage(peer_id, user1, user2):
    peer_str = str(peer_id)
    key = f"{min(user1,user2)},{max(user1,user2)}"
    if peer_str in data["marriages"] and key in data["marriages"][peer_str]:
        del data["marriages"][peer_str][key]
        save_data(data)
        return True
    return False

def is_married(peer_id, user_id):
    for m in get_marriages(peer_id).values():
        if user_id in m["users"]:
            return m["users"]
    return None

def add_proposal(peer_id, proposer_id, target_id, expires_minutes=5):
    peer_str = str(peer_id)
    if peer_str not in data["marriage_proposals"]:
        data["marriage_proposals"][peer_str] = {}
    data["marriage_proposals"][peer_str][str(proposer_id)] = {"target_id": target_id, "expires": (datetime.now() + timedelta(minutes=expires_minutes)).timestamp()}
    save_data(data)

def remove_proposal(peer_id, proposer_id):
    peer_str = str(peer_id)
    if peer_str in data["marriage_proposals"] and str(proposer_id) in data["marriage_proposals"][peer_str]:
        del data["marriage_proposals"][peer_str][str(proposer_id)]
        save_data(data)

def get_random_joke():
    jokes = [
        "Почему программисты не любят природу? Слишком много багов.",
        "Что говорит один бит другому? Прикрой меня, я устал.",
        "Сколько программистов нужно, чтобы заменить лампочку? Ни одного — это аппаратная проблема.",
        "Почему бота назвали Чат-Менеджер? Потому что он менеджерит чат!",
        "Что будет, если скрестить бота и администратора? Бот-администратор, который пинает сам себя.",
    ]
    return random.choice(jokes)

def calculate_expression(expr):
    try:
        expr = expr.replace(' ', '')
        if not re.match(r'^[\d\+\-\*\/\(\)\.]+$', expr):
            return None
        result = eval(expr)
        return round(result, 2)
    except:
        return None
    # ==================== ОСНОВНОЙ ЦИКЛ ====================
print("✅ Бот запущен. Команды: /help или !помощь")

for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        msg = event.object.message
        peer_id = msg['peer_id']
        from_id = msg['from_id']
        text = msg.get('text', '').strip()
        lower_text = text.lower()
        attachments = msg.get('attachments', [])

        # ЛИЧНЫЕ СООБЩЕНИЯ
        if peer_id == from_id:
            if from_id != OWNER_ID:
                send_message(peer_id, "🤖 Я работаю только в беседах.\n➖ Добавьте меня в группу, выдайте права администратора и напишите /start")
            continue

        # ПРИВЕТСТВИЕ ПРИ ДОБАВЛЕНИИ БОТА
        if event.object.message.get('action') and event.object.message['action'].get('type') == 'chat_invite_user':
            invited_id = event.object.message['action'].get('member_id')
            if invited_id == -GROUP_ID:
                set_chat_active(peer_id, True)
                init_default_roles(peer_id)
                ensure_owner_role(peer_id)
                send_message(peer_id, "✨ Привет! Благодарю что добавили меня в беседу, я вас не подведу❤\n━━━━━━━━━━━━━━━━━\n👑 Бот создан Павлом Мелентьевым.\n⚠️ ВАЖНО: выдайте боту администратора и напишите /start")
                continue

        # ГЛОБАЛЬНЫЕ ОГРАНИЧЕНИЯ
        if from_id in data["global_restricted"]:
            send_message(peer_id, "🚫 Вы глобально заблокированы во всех чатах бота.", reply_to=msg['id'])
            continue

        # СТАТИСТИКА И БАН/МУТ
        update_stats(peer_id, from_id, text, attachments)
        if is_banned(peer_id, from_id):
            send_message(peer_id, "🚫 Вы забанены в этой беседе.", reply_to=msg['id'])
            continue
        mute_end = get_mute_end(peer_id, from_id)
        if mute_end and datetime.now() < mute_end:
            send_message(peer_id, "🔇 Вы замучены.", reply_to=msg['id'])
            continue
        elif mute_end:
            remove_mute(peer_id, from_id)

        if not (lower_text.startswith('/') or lower_text.startswith('!')):
            continue

        raw_cmd = lower_text[1:].strip()
        if not raw_cmd:
            continue
        parts = raw_cmd.split()
        cmd = parts[0]

        # АЛИАСЫ КОМАНД (русские и английские)
        cmd_translate = {
            "help": "помощь", "ping": "пинг", "chatid": "чатид", "stats": "статистика",
            "stat": "статистика", "staff": "стафф", "nick": "ник", "gnick": "гник",
            "rnick": "рник", "nlist": "нлист", "start": "начать", "ai": "ай",
            "kick": "кик", "mute": "мут", "unmute": "размут", "ban": "бан",
            "unban": "разбан", "warn": "варн", "roles": "роли", "role": "роль",
            "report": "репорт", "tickets": "тикеты", "complaint": "жалоба",
            "marry": "брак", "divorce": "развод", "marriages": "браки",
            "yes": "да", "no": "нет", "confirm_divorce": "подтвердить_развод",
            "whoami": "кто я", "newrole": "новаяроль", "delrole": "удалитьроль",
            "zov": "зови", "созыв": "зови", "clear": "очистить", "calculator": "калькулятор",
            "calc": "калькулятор", "time": "время", "joke": "шутка", "weather": "погода",
            "score": "баллы", "points": "баллы", "rating": "баллы"
        }
        if cmd in cmd_translate:
            cmd = cmd_translate[cmd]

        public_commands = ["помощь", "пинг", "чатид", "начать", "репорт", "тикеты", "жалоба",
                           "калькулятор", "время", "шутка", "погода", "баллы", "кто я", "статистика",
                           "стафф", "роли", "нлист", "гник", "брак", "да", "нет", "развод",
                           "подтвердить_развод", "браки"]

        if not is_chat_active(peer_id):
            if cmd not in public_commands and cmd != "начать":
                send_message(peer_id, "⚠️ Бот не активирован.\n➖ Напишите /start", reply_to=msg['id'])
                continue
            if cmd == "начать":
                set_chat_active(peer_id, True)
                init_default_roles(peer_id)
                ensure_owner_role(peer_id)
                send_message(peer_id, "✅ Чат активирован! Теперь бот работает.")
                continue

        handled = True

        # ==================== ОСНОВНЫЕ КОМАНДЫ ====================
        if cmd == "помощь":
            help_text = """🤖 КОМАНДЫ БОТА (можно / или !, рус/англ)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 Основные команды
➖ /ping или /пинг — проверить работу бота
➖ /chatid или /чатид — ID беседы
➖ /start или /начать — активировать бота
➖ /whoami или /кто я — мой профиль
➖ /stat или /статистика @user — статистика

📋 Обращения и жалобы
➖ /report или /репорт <текст> — жалоба администратору
➖ /complaint или /жалоба <текст> — жалоба владельцу
➖ /tickets или /тикеты — мои жалобы

👑 Управление ролями
➖ /staff или /стафф — список администрации
➖ /roles или /роли — список всех ролей
➖ /role или /роль <приоритет/название> @user — назначить роль
➖ /newrole или /новаяроль <название> <приоритет> — создать роль
➖ /delrole или /удалитьроль <название> — удалить роль

📛 Никнеймы
➖ /nick или /ник <текст> — установить ник
➖ /gnick или /гник — узнать ник
➖ /rnick или /рник — удалить ник
➖ /nlist или /нлист — список никнеймов

💍 Брачная система
➖ /marry или /брак @user — предложить брак
➖ /yes или /да — принять предложение
➖ /no или /нет — отклонить
➖ /divorce или /развод — начать развод
➖ /confirm_divorce или /подтвердить_развод — подтвердить
➖ /marriages или /браки — список браков

🔧 Модерация (требуют приоритет)
➖ /mute или /мут @user — замутить на 5 мин (20+)
➖ /unmute или /размут @user — снять мут (20+)
➖ /warn или /варн @user — предупреждение (40+)
➖ /kick или /кик @user — кикнуть (40+)
➖ /ban или /бан @user — забанить (60+)
➖ /unban или /разбан @user — снять бан (60+)
➖ /zov или /зови — пинг всех участников (60+)
➖ /clear или /очистить — очистить муты/варны (40+)

🧠 Развлечения
➖ /calculator или /калькулятор 2+2 — вычислить
➖ /time или /время — текущее время
➖ /joke или /шутка — случайная шутка
➖ /weather или /погода <город> — погода
➖ /score или /баллы @user — рейтинг активности

🛡️ Системные команды — /syshelp (только для владельца)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 Приоритеты: 20+ мутить, 40+ варн/кик/роль, 60+ бан/зови"""
            send_message(peer_id, help_text)

        elif cmd == "пинг":
            send_message(peer_id, "🏓 Понг! Бот работает.")
        elif cmd == "чатид":
            send_message(peer_id, f"🆔 ID беседы: {peer_id}")
        elif cmd == "кто я":
            send_message(peer_id, format_profile(peer_id, from_id))
        elif cmd == "статистика":
            target = from_id
            if msg.get('reply_message'):
                target = msg['reply_message']['from_id']
            else:
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
            send_message(peer_id, format_profile(peer_id, target))
        elif cmd in ("стафф", "роли"):
            roles_dict = get_all_roles(peer_id)
            if cmd == "стафф":
                lines = ["🏅 Администрация чата:"]
                for rname, prio in sorted(roles_dict.items(), key=lambda x: x[1], reverse=True):
                    users = [get_user_mention(int(uid)) for uid, r in data["user_roles"].get(str(peer_id), {}).items() if r == rname]
                    if users:
                        lines.append(f"➖ {rname} (приоритет {prio}): {', '.join(users)}")
                if len(lines) == 1:
                    lines.append("Нет назначенных ролей.")
                send_message(peer_id, "\n".join(lines))
            else:
                lines = ["📜 Список ролей (приоритет):"]
                for name, prio in sorted(roles_dict.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"➖ {name} — {prio}")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "нлист":
            nicks = get_all_nicks(peer_id)
            if not nicks:
                send_message(peer_id, "Никнеймов нет.")
            else:
                lines = ["📛 Список никнеймов:"]
                for uid, nick in nicks.items():
                    lines.append(f"➖ {get_user_mention(uid)}: {nick}")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "гник":
            target = from_id
            if msg.get('reply_message'):
                target = msg['reply_message']['from_id']
            nick = get_nick(peer_id, target)
            send_message(peer_id, f"🔗 Ник {get_user_mention(target)}: {nick if nick else 'нет'}")
        elif cmd == "репорт" and len(parts) >= 2:
            tid = create_complaint(from_id, peer_id, ' '.join(parts[1:]))
            try:
                vk.messages.send(user_id=OWNER_ID, message=f"📩 Новая жалоба #{tid} от {get_user_mention(from_id)}:\n{parts[1]}", random_id=0)
            except:
                pass
            send_message(peer_id, f"✅ Жалоба #{tid} отправлена администратору.")
        elif cmd == "тикеты":
            tickets = [t for t in data["tickets"] if t["user_id"] == from_id]
            if not tickets:
                send_message(peer_id, "У вас нет жалоб.")
            else:
                lines = ["📋 Ваши жалобы:"]
                for t in tickets:
                    lines.append(f"➖ #{t['id']}: {t['text'][:50]} ({t['status']})")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "жалоба" and len(parts) >= 2:
            tid = create_complaint(from_id, peer_id, ' '.join(parts[1:]))
            try:
                vk.messages.send(user_id=OWNER_ID, message=f"📩 Жалоба #{tid} от {get_user_mention(from_id)}:\n{parts[1]}", random_id=0)
            except:
                pass
            send_message(peer_id, f"✅ Жалоба #{tid} отправлена владельцу.")
        elif cmd == "калькулятор" and len(parts) >= 2:
            expr = ' '.join(parts[1:])
            res = calculate_expression(expr)
            if res is not None:
                send_message(peer_id, f"🧮 {expr} = {res}")
            else:
                send_message(peer_id, "❌ Ошибка! Проверьте выражение.")
        elif cmd == "время":
            now = datetime.now() + timedelta(hours=3)
            send_message(peer_id, f"🕐 МСК: {now.strftime('%H:%M:%S')}\n📅 Дата: {now.strftime('%d.%m.%Y')}")
        elif cmd == "шутка":
            send_message(peer_id, f"😂 {get_random_joke()}")
        elif cmd == "погода" and len(parts) >= 2:
            city = ' '.join(parts[1:])
            send_message(peer_id, f"🌤️ Погода в {city}: +22°C, облачно\n(Данные демонстрационные)")
        elif cmd == "баллы":
            target = from_id
            if msg.get('reply_message'):
                target = msg['reply_message']['from_id']
            else:
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
            score = max(0, get_user_activity_score(peer_id, target))
            send_message(peer_id, f"🏆 Рейтинг {get_user_mention(target)}: {score} баллов")

        # ==================== МОДЕРАЦИЯ ====================
        elif cmd == "ник" and can_moderate(from_id, from_id, peer_id, "nick") and len(parts) >= 2:
            set_nick(peer_id, from_id, ' '.join(parts[1:])[:30])
            send_message(peer_id, "✅ Ник установлен.")
        elif cmd == "рник" and can_moderate(from_id, from_id, peer_id, "nick"):
            remove_nick(peer_id, from_id)
            send_message(peer_id, "✅ Ник удалён.")
        elif cmd == "мут" and can_moderate(from_id, from_id, peer_id, "mute"):
            reply = msg.get('reply_message')
            if not reply:
                send_message(peer_id, "⚠️ Ответьте на сообщение пользователя.", reply_to=msg['id'])
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "mute"):
                send_message(peer_id, f"❌ Нельзя замутить {get_user_mention(target)} (его приоритет выше или равен вашему).")
                continue
            minutes = 5
            if len(parts) > 1 and parts[1].isdigit():
                minutes = int(parts[1])
            mute_user(peer_id, target, minutes)
        elif cmd == "размут" and can_moderate(from_id, from_id, peer_id, "unmute"):
            reply = msg.get('reply_message')
            if reply:
                unmute_user(peer_id, reply['from_id'])
        elif cmd == "варн" and can_moderate(from_id, from_id, peer_id, "warn"):
            reply = msg.get('reply_message')
            if not reply:
                send_message(peer_id, "⚠️ Ответьте на сообщение.")
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "warn"):
                send_message(peer_id, f"❌ Нельзя выдать предупреждение {get_user_mention(target)} (его приоритет выше или равен вашему).")
                continue
            reason = ' '.join(parts[1:]) if len(parts) > 1 else "без причины"
            give_warning(peer_id, target, reason)
        elif cmd == "кик" and can_moderate(from_id, from_id, peer_id, "kick"):
            reply = msg.get('reply_message')
            if not reply:
                send_message(peer_id, "⚠️ Ответьте на сообщение.")
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "kick"):
                send_message(peer_id, f"❌ Нельзя кикнуть {get_user_mention(target)} (его приоритет выше или равен вашему).")
                continue
            if kick_user(peer_id, target):
                send_message(peer_id, f"👢 {get_user_mention(target)} кикнут.")
        elif cmd == "роль" and can_moderate(from_id, from_id, peer_id, "role"):
            if len(parts) < 2:
                send_message(peer_id, "❌ /role <приоритет/название> @user")
                continue
            arg = parts[1]
            target = None
            if msg.get('reply_message'):
                target = msg['reply_message']['from_id']
            else:
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
            if not target:
                send_message(peer_id, "➖ Укажите пользователя (ответом или упоминанием).")
                continue
            if target == from_id and from_id != OWNER_ID:
                send_message(peer_id, "❌ Нельзя изменить свою роль.")
                continue
            role_name = None
            if arg.isdigit():
                role_name = find_role_by_priority(peer_id, int(arg))
            else:
                for rn in get_all_roles(peer_id).keys():
                    if rn.lower() == arg.lower():
                        role_name = rn
                        break
            if not role_name:
                send_message(peer_id, f"❌ Роль '{arg}' не найдена.")
                continue
            if not can_assign_role(from_id, target, role_name, peer_id):
                send_message(peer_id, "❌ Нельзя назначить эту роль (ваш приоритет ниже или равен роли цели, либо роль выше вашей).")
                continue
            set_user_role(peer_id, target, role_name)
            send_message(peer_id, f"🎭 {get_user_mention(target)} назначена роль '{role_name}'.")
        elif cmd == "бан" and can_moderate(from_id, from_id, peer_id, "ban"):
            reply = msg.get('reply_message')
            if not reply:
                send_message(peer_id, "⚠️ Ответьте на сообщение.")
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "ban"):
                send_message(peer_id, f"❌ Нельзя забанить {get_user_mention(target)} (его приоритет выше или равен вашему).")
                continue
            ban_user(peer_id, target)
        elif cmd == "разбан" and can_moderate(from_id, from_id, peer_id, "ban"):
            reply = msg.get('reply_message')
            if reply:
                unban_user(peer_id, reply['from_id'])
        elif cmd == "зови" and can_moderate(from_id, from_id, peer_id, "zov"):
            zov_call(peer_id, from_id)
        elif cmd == "новаяроль" and can_moderate(from_id, from_id, peer_id, "ban"):
            if len(parts) < 3:
                send_message(peer_id, "❌ /новаяроль <название> <приоритет>\n➖ Приоритет от 0 до 100")
                continue
            role_name = parts[1]
            if not role_name.isalpha():
                send_message(peer_id, "❌ Название роли должно содержать только буквы.")
                continue
            try:
                prio = int(parts[2])
                if prio < 0 or prio > 100:
                    raise ValueError
            except:
                send_message(peer_id, "❌ Приоритет должен быть целым числом от 0 до 100.")
                continue
            if any(r.lower() == role_name.lower() for r in get_all_roles(peer_id)):
                send_message(peer_id, f"❌ Роль '{role_name}' уже существует.")
                continue
            if any(p == prio for p in get_all_roles(peer_id).values()):
                send_message(peer_id, f"❌ Приоритет {prio} уже используется другой ролью.")
                continue
            create_role(peer_id, role_name, prio)
            send_message(peer_id, f"✅ Роль '{role_name}' (приоритет {prio}) создана!")
        elif cmd == "удалитьроль" and can_moderate(from_id, from_id, peer_id, "ban"):
            if len(parts) < 2:
                send_message(peer_id, "❌ /delrole <название>")
                continue
            rname = parts[1]
            if rname in PROTECTED_ROLES:
                send_message(peer_id, "❌ Нельзя удалить стандартную роль.")
                continue
            if delete_role(peer_id, rname):
                for uid, r in list(data["user_roles"].get(str(peer_id), {}).items()):
                    if r == rname:
                        del data["user_roles"][str(peer_id)][uid]
                save_data(data)
                send_message(peer_id, f"🗑️ Роль '{rname}' удалена.")
            else:
                send_message(peer_id, f"❌ Роль '{rname}' не найдена.")
        elif cmd == "очистить" and can_moderate(from_id, from_id, peer_id, "warn"):
            keys = [k for k in data["muted"] if k.startswith(f"{peer_id},")]
            for k in keys:
                del data["muted"][k]
            keys = [k for k in data["warnings"] if k.startswith(f"{peer_id},")]
            for k in keys:
                del data["warnings"][k]
            save_data(data)
            send_message(peer_id, "🧹 Муты и предупреждения очищены.")

        # ==================== БРАКИ ====================
        elif cmd == "брак":
            target = None
            m = re.search(r'\[id(\d+)\|', text)
            if m:
                target = int(m.group(1))
            if not target or target == from_id or is_married(peer_id, from_id) or is_married(peer_id, target):
                send_message(peer_id, "❌ Невозможно.")
                continue
            add_proposal(peer_id, from_id, target, 5)
            send_message(peer_id, f"💌 Предложение брака отправлено {get_user_mention(target)}\n➖ /yes или /no в течение 5 минут.")
        elif cmd == "да":
            found = None
            for pid, prop in data["marriage_proposals"].get(str(peer_id), {}).items():
                if prop["target_id"] == from_id and datetime.now().timestamp() < prop["expires"]:
                    found = int(pid)
                    break
            if not found:
                send_message(peer_id, "❌ Нет активных предложений.")
                continue
            add_marriage(peer_id, found, from_id)
            remove_proposal(peer_id, found)
            send_message(peer_id, f"💍 Брак заключён!")
        elif cmd == "нет":
            found = None
            for pid, prop in data["marriage_proposals"].get(str(peer_id), {}).items():
                if prop["target_id"] == from_id and datetime.now().timestamp() < prop["expires"]:
                    found = int(pid)
                    break
            if not found:
                send_message(peer_id, "❌ Нет активных предложений.")
                continue
            remove_proposal(peer_id, found)
            send_message(peer_id, "❌ Предложение отклонено.")
        elif cmd == "развод":
            partner = is_married(peer_id, from_id)
            if not partner:
                send_message(peer_id, "❌ Вы не в браке.")
                continue
            key = f"{peer_id},{from_id}"
            data["divorce_requests"][key] = {"partner": partner[0] if partner[0] != from_id else partner[1], "expires": (datetime.now() + timedelta(minutes=5)).timestamp()}
            save_data(data)
            send_message(peer_id, "📄 Заявка на развод создана.\n➖ /подтвердить_развод в течение 5 минут.")
        elif cmd == "подтвердить_развод":
            key = f"{peer_id},{from_id}"
            req = data["divorce_requests"].get(key)
            if not req or datetime.now().timestamp() > req["expires"]:
                if key in data["divorce_requests"]:
                    del data["divorce_requests"][key]
                    save_data(data)
                send_message(peer_id, "❌ Заявка не найдена или истекла.")
                continue
            partner_id = req["partner"]
            if remove_marriage(peer_id, from_id, partner_id):
                send_message(peer_id, "✅ Брак расторгнут.")
            else:
                send_message(peer_id, "❌ Ошибка.")
            del data["divorce_requests"][key]
            save_data(data)
        elif cmd == "браки":
            marriages = get_marriages(peer_id)
            if not marriages:
                send_message(peer_id, "📭 В этой беседе нет браков.")
            else:
                lines = ["💍 Список браков:"]
                for m in marriages.values():
                    u1, u2 = m["users"]
                    date_str = datetime.fromtimestamp(m["date"]).strftime("%d.%m.%Y")
                    lines.append(f"➖ {get_user_mention(u1)} + {get_user_mention(u2)} (с {date_str})")
                send_message(peer_id, "\n".join(lines))

        # ==================== AI ДЛЯ VIP ====================
        elif cmd == "ай":
            if from_id not in data["vip_users"] and from_id != OWNER_ID:
                send_message(peer_id, "❌ Команда доступна только VIP.")
                continue
            q = ' '.join(parts[1:]) if len(parts) > 1 else ""
            if not q:
                send_message(peer_id, "Задайте вопрос, например: /ai кто создал бота?")
                continue
            lower_q = q.lower()
            if "владелец" in lower_q or "создатель" in lower_q or "кто создал" in lower_q:
                answer = "👑 Тимофей Александрович и Павел Мелентьев — создатели и владельцы проекта BEST. Они разработали этого бота и продолжают его развивать!"
            else:
                answer = "Я чат-менеджер бот. Мои владельцы: Тимофей Александрович и Павел Мелентьев. Для списка команд введите /help"
            send_message(peer_id, answer)

        # ==================== СИСТЕМНЫЕ КОМАНДЫ ====================
        elif cmd.startswith("sys"):
            sub_cmd = cmd[3:]
            sys_aliases = {"help": "помощь", "staff": "стафф", "list": "список", "stat": "стата_бота", "backup": "резерв", "restart": "перезагрузка"}
            if sub_cmd in sys_aliases:
                sub_cmd = sys_aliases[sub_cmd]

            sys_levels = {"помощь": 1, "стафф": 1, "список": 1, "стата_бота": 1, "резерв": 8, "перезагрузка": 10}
            required = sys_levels.get(sub_cmd, 10)
            if not can_use_sys_command(from_id, required):
                send_message(peer_id, f"⛔ Недостаточно прав для этой команды.")
                continue

            if sub_cmd == "помощь":
                send_message(peer_id, "🛡️ СИСТЕМНЫЕ КОМАНДЫ:\n/sysстафф — список сусадминов\n/sysсписок — активные беседы\n/sysстата_бота — статистика бота\n/sysрезерв — резервная копия\n/sysперезагрузка — перезапуск\n/sysроль @user <уровень> — сус-роль")
            elif sub_cmd == "стафф":
                users = set(data["sys_admins"]) | {int(uid) for uid in data["sys_roles"].keys()}
                lines = ["🛡️ Суперадминистраторы:"]
                for uid in users:
                    lines.append(f"➖ {get_user_mention(uid)}")
                send_message(peer_id, "\n".join(lines) if users else "Нет суперадминистраторов.")
            elif sub_cmd == "список":
                active = [pid for pid, a in data["active_chats"].items() if a]
                lines = ["📋 Активные беседы:"] + [f"➖ {get_chat_title(int(pid))}" for pid in active[:10]]
                send_message(peer_id, "\n".join(lines) if active else "Нет активных бесед.")
            elif sub_cmd == "стата_бота":
                total_chats = len([p for p, a in data["active_chats"].items() if a])
                total_users = len(set([k.split(",")[1] for k in data["user_stats"].keys() if len(k.split(",")) == 2]))
                total_msgs = sum(s.get("msgs", 0) for s in data["user_stats"].values())
                send_message(peer_id, f"📊 Статистика бота:\nАктивных бесед: {total_chats}\nПользователей: {total_users}\nСообщений: {total_msgs}")
            elif sub_cmd == "резерв":
                filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(filename, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                send_message(peer_id, f"✅ Резервная копия: {filename}")
            elif sub_cmd == "перезагрузка":
                send_message(peer_id, "🔄 Перезагрузка...")
                time.sleep(1)
                os._exit(0)
            else:
                send_message(peer_id, "❌ Неизвестная системная команда. /syshelp")
            continue

        else:
            handled = False

        if not handled and cmd not in ["помощь", "пинг", "чатид", "начать", "кто я"]:
            send_message(peer_id, "❌ Неизвестная команда.\n➖ Введите /help или !помощь", reply_to=msg['id'])

    # ЛИЧНЫЕ СООБЩЕНИЯ ДЛЯ РАССЫЛКИ ВЛАДЕЛЬЦА
    elif event.type == VkBotEventType.MESSAGE_NEW and event.object.message['peer_id'] == event.object.message['from_id']:
        msg = event.object.message
        if msg['from_id'] == OWNER_ID and msg['text'].lower().startswith('/рассылка'):
            parts = msg['text'].split(maxsplit=1)
            if len(parts) >= 2:
                sent = broadcast_to_all_chats(parts[1])
                send_message(msg['peer_id'], f"✅ Рассылка выполнена в {sent} чатов.")