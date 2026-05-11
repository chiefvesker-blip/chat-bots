import vk_api
import json
import os
import time
import threading
import re
import random
from datetime import datetime, timedelta
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

# ===== НАСТРОЙКИ =====
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

# ===== ЗАГРУЗКА ДАННЫХ =====
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

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
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

def get_user_activity_score(peer_id, user_id):
    stats = get_user_stats(peer_id, user_id)
    score = stats['msgs'] + stats['photos'] * 2 + stats['videos'] * 3 - stats['badwords'] * 5
    return max(0, score)

def get_global_user_stats(user_id):
    """Собирает статистику пользователя по всем чатам"""
    total_msgs = 0
    total_chars = 0
    total_badwords = 0
    total_photos = 0
    total_videos = 0
    total_voices = 0
    chats = []
    for key, stats in data["user_stats"].items():
        parts = key.split(",")
        if len(parts) == 2:
            try:
                uid = int(parts[1])
                if uid == user_id:
                    peer_id = int(parts[0])
                    chats.append(peer_id)
                    total_msgs += stats.get("msgs", 0)
                    total_chars += stats.get("chars", 0)
                    total_badwords += stats.get("badwords", 0)
                    total_photos += stats.get("photos", 0)
                    total_videos += stats.get("videos", 0)
                    total_voices += stats.get("voices", 0)
            except:
                pass
    return {
        "msgs": total_msgs, "chars": total_chars, "badwords": total_badwords,
        "photos": total_photos, "videos": total_videos, "voices": total_voices,
        "chats_count": len(set(chats))
    }

def get_user_chats(user_id):
    """Возвращает список peer_id чатов, где есть пользователь"""
    chats = []
    for key in data["user_stats"].keys():
        parts = key.split(",")
        if len(parts) == 2:
            try:
                uid = int(parts[1])
                if uid == user_id:
                    chats.append(int(parts[0]))
            except:
                pass
    return list(set(chats))

def export_chat_stats(peer_id):
    """Экспортирует статистику беседы в JSON файл"""
    chat_title = get_chat_title(peer_id)
    users_stats = {}
    for key, stats in data["user_stats"].items():
        parts = key.split(",")
        if len(parts) == 2:
            try:
                pid = int(parts[0])
                if pid == peer_id:
                    users_stats[parts[1]] = stats
            except:
                pass
    export_data = {
        "chat_id": peer_id,
        "chat_title": chat_title,
        "export_date": datetime.now().isoformat(),
        "users": users_stats,
        "roles": get_all_roles(peer_id),
        "user_roles": data["user_roles"].get(str(peer_id), {})
    }
    filename = f"export_chat_{peer_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    return filename

def mute_all_chat(peer_id, minutes, actor_id):
    """Мутит всех участников чата, кого может замутить actor"""
    members = get_chat_members(peer_id)
    bot_id = -GROUP_ID
    muted_count = 0
    failed = 0
    for uid in members:
        if uid == actor_id or uid == bot_id or uid == OWNER_ID:
            continue
        if can_moderate(actor_id, uid, peer_id, "mute"):
            set_mute(peer_id, uid, minutes)
            muted_count += 1
            time.sleep(0.2)
        else:
            failed += 1
    return muted_count, failed

def ban_all_chat(peer_id, actor_id):
    """Банит и кикает всех участников чата, кого может забанить actor"""
    members = get_chat_members(peer_id)
    bot_id = -GROUP_ID
    banned_count = 0
    failed = 0
    for uid in members:
        if uid == actor_id or uid == bot_id or uid == OWNER_ID:
            continue
        if can_moderate(actor_id, uid, peer_id, "ban"):
            set_ban(peer_id, uid, True)
            if kick_user(peer_id, uid):
                banned_count += 1
            else:
                failed += 1
            time.sleep(0.3)
        else:
            failed += 1
    return banned_count, failed

def copy_role(peer_id, source_id, target_id, actor_id):
    """Копирует роль с одного пользователя на другого"""
    source_role = get_user_role(peer_id, source_id)
    if not can_assign_role(actor_id, target_id, source_role, peer_id):
        return False, "Недостаточно прав"
    set_user_role(peer_id, target_id, source_role)
    return True, source_role

def send_to_user(user_id, message):
    """Отправляет сообщение пользователю в ЛС"""
    try:
        vk.messages.send(user_id=user_id, message=message, random_id=0)
        return True
    except:
        return False

def get_top_users(peer_id, limit=10):
    """Топ пользователей по активности в беседе"""
    users = []
    prefix = f"{peer_id},"
    for key, stats in data["user_stats"].items():
        if key.startswith(prefix):
            uid = int(key.split(",")[1])
            score = stats.get("msgs", 0) + stats.get("photos", 0) * 2 + stats.get("videos", 0) * 3 - stats.get("badwords", 0) * 5
            users.append({"id": uid, "score": max(0, score)})
    users.sort(key=lambda x: x["score"], reverse=True)
    return users[:limit]

def sys_zov(actor_id):
    """Глобальный созыв – пинг каждого участника во всех чатах"""
    all_users = set()
    for key in data["user_stats"].keys():
        parts = key.split(",")
        if len(parts) == 2:
            try:
                all_users.add(int(parts[1]))
            except:
                pass
    # Убираем владельца бота и самого актора
    all_users.discard(OWNER_ID)
    all_users.discard(actor_id)
    
    sent = 0
    for uid in all_users:
        try:
            vk.messages.send(user_id=uid, message=f"🔔 Глобальный созыв от {get_user_mention(actor_id)}! Бот активен во всех чатах.", random_id=0)
            sent += 1
            time.sleep(0.3)
        except:
            pass
    return sent

# ===== ФУНКЦИИ ДЛЯ ПРАВ И РОЛЕЙ =====
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

def is_global_restricted(user_id):
    return user_id in data["global_restricted"]

def set_global_restricted(user_id, restricted=True):
    if restricted:
        if user_id not in data["global_restricted"]:
            data["global_restricted"].append(user_id)
    else:
        if user_id in data["global_restricted"]:
            data["global_restricted"].remove(user_id)
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

def get_all_roles(peer_id):
    return data["roles"].get(str(peer_id), {})

def find_role_by_priority(peer_id, priority):
    for name, prio in get_all_roles(peer_id).items():
        if prio == priority:
            return name
    return None

def get_user_priority(peer_id, user_id):
    role = get_user_role(peer_id, user_id)
    return get_role_priority(peer_id, role)

def can_moderate(actor_id, target_id, peer_id, action="view"):
    if actor_id == OWNER_ID:
        return True
    actor_priority = get_user_priority(peer_id, actor_id)
    min_priority = {
        "view": 0, "nick": 20, "mute": 20, "unmute": 20,
        "warn": 40, "kick": 40, "role": 40, "ban": 60,
        "zov": 60, "masskick": 60, "mutall": 70, "banall": 80
    }.get(action, 0)
    if actor_priority < min_priority:
        return False
    if action in ("mute", "warn", "kick", "ban", "role", "masskick", "mutall", "banall"):
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

# ===== ЖАЛОБЫ =====
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

# ===== СТАТИСТИКА =====
BADWORDS = set(["бля", "блять", "хуй", "пизда", "ебать", "ебан", "нах", "хер", "залупа", "мудак", "говно", "сука", "тварь", "пидор", "гандон", "долбоеб", "уебок", "fuck", "shit", "bitch", "dick", "asshole", "cunt"])

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
    return f"""🔰 Профиль пользователя {mention}
🔗 Ник: {nick}
👮‍♂️ Роль: {role}
⚠️ Предупреждений: {warns}

📝 Статистика сообщений:
- Всего: {stats['msgs']}
- Символов: {stats['chars']}
- Нецензурных слов: {stats['badwords']}
- Фото: {stats['photos']}
- Видео: {stats['videos']}
- Голосовые: {stats['voices']}"""

# ===== VK API ФУНКЦИИ =====
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

def send_message(peer_id, text, reply_to=None):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=0, reply_to=reply_to)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def get_chat_members(peer_id):
    try:
        members = vk.messages.getConversationMembers(peer_id=peer_id)
        return [m['member_id'] for m in members['items'] if m['member_id'] > 0]
    except:
        return []

def kick_user(peer_id, user_id):
    try:
        vk.messages.removeChatUser(chat_id=peer_id - 2000000000, member_id=user_id)
        return True
    except Exception:
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
    send_message(peer_id, f"🚫 {get_user_mention(user_id)} забанен и кикнут.")

def unban_user(peer_id, user_id):
    set_ban(peer_id, user_id, False)
    send_message(peer_id, f"✅ Снят бан с {get_user_mention(user_id)}")

def give_warning(peer_id, user_id, reason=""):
    count = add_warning(peer_id, user_id, 1)
    msg = f"⚠️ Предупреждение {count}/3 для {get_user_mention(user_id)}. {reason}"
    if count >= 3:
        kick_user(peer_id, user_id)
        msg += "\n❗ 3 предупреждения → кик."
        add_warning(peer_id, user_id, -3)
    send_message(peer_id, msg)

def broadcast_to_all_chats(message):
    full = f"📢 Важное уведомление от бота.\nОтправитель: владелец бота.\n\n{message}"
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

def zov_call(peer_id, actor_id):
    members = get_chat_members(peer_id)
    bot_id = -GROUP_ID
    members = [m for m in members if m != bot_id and m != actor_id]
    if not members:
        send_message(peer_id, "Нет других участников для созыва.")
        return
    send_message(peer_id, f"🔔 Созыв от {get_user_mention(actor_id)}. Всего участников: {len(members)}")
    for uid in members:
        mention = get_user_mention(uid)
        try:
            vk.messages.send(peer_id=peer_id, message=f"{mention}, вы были пингованы!", random_id=0)
            time.sleep(0.4)
        except:
            pass
    send_message(peer_id, "✅ Созыв завершён.")

# ===== БРАЧНАЯ СИСТЕМА =====
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
    marriages = get_marriages(peer_id)
    for m in marriages.values():
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
    if peer_str in data["marriage_proposals"]:
        if str(proposer_id) in data["marriage_proposals"][peer_str]:
            del data["marriage_proposals"][peer_str][str(proposer_id)]
            save_data(data)

# ===== ОСНОВНОЙ ЦИКЛ =====
print("Бот запущен. /help")

for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        msg = event.object.message
        peer_id = msg['peer_id']
        from_id = msg['from_id']
        text = msg.get('text', '').strip()
        lower_text = text.lower()
        attachments = msg.get('attachments', [])

        # ===== ЛИЧНЫЕ СООБЩЕНИЯ (ЛС) =====
        if peer_id == from_id:  # ЛС
            if from_id != OWNER_ID:
                send_message(peer_id, "Привет! Я работаю только в беседах. Добавьте меня в группу, выдайте права администратора и напишите /start")
            continue

        # Приветствие при добавлении бота
        if event.object.message.get('action') and event.object.message['action'].get('type') == 'chat_invite_user':
            invited_id = event.object.message['action'].get('member_id')
            if invited_id == -GROUP_ID:
                set_chat_active(peer_id, True)
                init_default_roles(peer_id)
                ensure_owner_role(peer_id)
                send_message(peer_id, "Привет! Благодарю что добавили меня в беседу, я вас не подведу❤\nБот создан Павлом Мелентьевым.\n⚠️ Чтобы начать работу, выдайте боту администратора в беседе и напишите /start")
                continue

        # Глобальное ограничение
        if is_global_restricted(from_id):
            send_message(peer_id, "🚫 Вы глобально заблокированы во всех чатах бота.", reply_to=msg['id'])
            continue

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

        # Алиасы
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
            "zov": "зови", "созыв": "зови", "clear": "очистить",
            "calculator": "калькулятор", "time": "время", "joke": "шутка", "weather": "погода", "score": "баллы"
        }
        if cmd in cmd_translate:
            cmd = cmd_translate[cmd]

        public_commands = ["помощь", "пинг", "чатид", "начать", "репорт", "тикеты", "жалоба", "калькулятор", "время", "шутка", "погода", "баллы",
                           "брак", "да", "нет", "развод", "подтвердить_развод", "браки", "кто я", "статистика", "стафф", "роли", "нлист", "гник"]

        if not is_chat_active(peer_id):
            if cmd not in public_commands and cmd != "начать":
                send_message(peer_id, "⚠️ Бот не активирован. /start", reply_to=msg['id'])
                continue
            if cmd == "начать":
                set_chat_active(peer_id, True)
                init_default_roles(peer_id)
                ensure_owner_role(peer_id)
                send_message(peer_id, "✅ Чат активирован!")
                continue

        handled = True

        # ==================== ПОМОЩЬ ====================
        if cmd == "помощь":
            help_text = """🤖 Команды бота (можно / или !):

📌 Основные:
/ping — Проверить бота
/chatid — ID беседы
/start — Активировать бота
/whoami — Мой профиль
/stat @user — Статистика

📋 Обращения:
/report <текст> — Жалоба администратору
/complaint <текст> — Жалоба владельцу
/tickets — Мои жалобы

👑 Роли:
/staff — Администрация
/roles — Список ролей
/role <приоритет/название> @user
/newrole <название> <приоритет>
/delrole <название>

📛 Ники:
/nick <ник>, /gnick, /rnick, /nlist

💍 Браки:
/marry @user, /yes, /no, /divorce, /confirm_divorce, /marriages

🔧 Модерация:
/mute @user, /unmute, /warn, /kick, /ban, /unban, /zov, /clear

🧠 Развлечения:
/calculator 2+2, /time, /joke, /weather <город>, /score @user

🛡️ Системные: /syshelp (только сусадмины)"""
            send_message(peer_id, help_text)

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
            elif "бот" in lower_q and ("кто" in lower_q or "автор" in lower_q):
                answer = "Бот создан Павлом Мелентьевым по заказу Тимофея Александровича. Вместе они создали Grand Chat Manager для удобного управления беседами ВКонтакте."
            elif "команды" in lower_q or "что умеет" in lower_q:
                answer = "Бот умеет: модерация (кик, мут, бан, варн), роли, ники, браки, тикеты, статистика, рассылка, созывы, калькулятор, шутки, погода, рейтинг и многое другое. /help"
            else:
                answer = "Я чат-менеджер бот. Мои владельцы: Тимофей Александрович и Павел Мелентьев. Для списка команд введите /help"
            send_message(peer_id, answer)

        # ==================== ОСТАЛЬНЫЕ КОМАНДЫ ====================
        elif cmd == "пинг":
            send_message(peer_id, "🏓 Понг!")
        elif cmd == "чатид":
            send_message(peer_id, f"🆔 ID: {peer_id}")
        elif cmd == "кто я":
            send_message(peer_id, format_profile(peer_id, from_id))
        elif cmd == "статистика":
            target = from_id
            reply = msg.get('reply_message')
            if reply:
                target = reply['from_id']
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
                        lines.append(f"{rname} (приоритет {prio}): {', '.join(users)}")
                if len(lines) == 1:
                    lines.append("Нет назначенных ролей.")
                send_message(peer_id, "\n".join(lines))
            else:
                lines = ["📜 Роли (приоритет):"]
                for name, prio in sorted(roles_dict.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"{name} — {prio}")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "нлист":
            nicks = get_all_nicks(peer_id)
            if not nicks:
                send_message(peer_id, "Никнеймов нет.")
            else:
                lines = ["📛 Никнеймы:"]
                for uid, nick in nicks.items():
                    lines.append(f"{get_user_mention(uid)}: {nick}")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "гник":
            target = from_id
            reply = msg.get('reply_message')
            if reply:
                target = reply['from_id']
            nick = get_nick(peer_id, target)
            send_message(peer_id, f"Ник {get_user_mention(target)}: {nick if nick else 'нет'}")
        elif cmd == "репорт":
            if len(parts) < 2:
                send_message(peer_id, "❌ /report <текст>", reply_to=msg['id'])
                continue
            tid = create_complaint(from_id, peer_id, ' '.join(parts[1:]))
            try:
                vk.messages.send(user_id=OWNER_ID, message=f"📩 Новая жалоба #{tid} от {get_user_mention(from_id)}:\n{parts[1]}", random_id=0)
            except:
                pass
            send_message(peer_id, f"✅ Жалоба #{tid} отправлена.")
        elif cmd == "тикеты":
            tickets = [t for t in data["tickets"] if t["user_id"] == from_id]
            if not tickets:
                send_message(peer_id, "Нет жалоб.")
            else:
                lines = ["📋 Ваши жалобы:"]
                for t in tickets:
                    lines.append(f"#{t['id']}: {t['text'][:50]} ({t['status']})")
                send_message(peer_id, "\n".join(lines))
        elif cmd == "жалоба":
            if len(parts) < 2:
                send_message(peer_id, "❌ /complaint <текст>", reply_to=msg['id'])
                continue
            tid = create_complaint(from_id, peer_id, ' '.join(parts[1:]))
            try:
                vk.messages.send(user_id=OWNER_ID, message=f"📩 Жалоба #{tid} от {get_user_mention(from_id)}:\n{parts[1]}", random_id=0)
            except:
                pass
            send_message(peer_id, f"✅ Жалоба #{tid} отправлена владельцу.")
        elif cmd == "калькулятор" and len(parts) >= 2:
            expr = ' '.join(parts[1:])
            try:
                expr = expr.replace(' ', '')
                if re.match(r'^[\d\+\-\*\/\(\)\.]+$', expr):
                    res = eval(expr)
                    send_message(peer_id, f"🧮 {expr} = {round(res, 2)}")
                else:
                    send_message(peer_id, "❌ Недопустимые символы")
            except:
                send_message(peer_id, "❌ Ошибка в выражении")
        elif cmd == "время":
            now = datetime.now() + timedelta(hours=3)
            send_message(peer_id, f"🕐 МСК: {now.strftime('%H:%M:%S')}\n📅 {now.strftime('%d.%m.%Y')}")
        elif cmd == "шутка":
            jokes = ["Почему программисты не любят природу? Слишком много багов.", "Что говорит один бит другому? Прикрой меня, я устал.", "Сколько программистов нужно, чтобы заменить лампочку? Ни одного — это аппаратная проблема.", "Почему бота назвали Чат-Менеджер? Потому что он менеджерит чат!", "Что будет, если скрестить бота и администратора? Бот-администратор, который пинает сам себя."]
            send_message(peer_id, f"😂 {random.choice(jokes)}")
        elif cmd == "погода" and len(parts) >= 2:
            city = ' '.join(parts[1:])
            send_message(peer_id, f"🌤️ Погода в {city}: +22°C, облачно\n(Данные демо, подключите API OpenWeatherMap)")
        elif cmd == "баллы":
            target = from_id
            reply = msg.get('reply_message')
            if reply:
                target = reply['from_id']
            else:
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
            score = get_user_activity_score(peer_id, target)
            send_message(peer_id, f"🏆 Рейтинг {get_user_mention(target)}: {score} баллов")

        # ==================== МОДЕРАЦИЯ ====================
        elif cmd == "ник" and can_moderate(from_id, from_id, peer_id, "nick") and len(parts) >= 2:
            set_nick(peer_id, from_id, ' '.join(parts[1:])[:30])
            send_message(peer_id, "✅ Ник установлен.")
        elif cmd == "рник" and can_moderate(from_id, from_id, peer_id, "nick"):
            remove_nick(peer_id, from_id)
            send_message(peer_id, "Ник удалён.")
        elif cmd == "мут" and can_moderate(from_id, from_id, peer_id, "mute"):
            reply = msg.get('reply_message')
            if not reply:
                send_message(peer_id, "⚠️ Ответьте на сообщение.")
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "mute"):
                send_message(peer_id, "❌ Нельзя замутить (цель выше).")
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
                send_message(peer_id, "⚠️ Ответьте.")
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "warn"):
                send_message(peer_id, "❌ Нельзя выдать предупреждение (цель выше).")
                continue
            reason = ' '.join(parts[1:]) if len(parts) > 1 else "без причины"
            give_warning(peer_id, target, reason)
        elif cmd == "кик" and can_moderate(from_id, from_id, peer_id, "kick"):
            reply = msg.get('reply_message')
            if not reply:
                send_message(peer_id, "⚠️ Ответьте.")
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "kick"):
                send_message(peer_id, "❌ Нельзя кикнуть (цель выше).")
                continue
            kick_user(peer_id, target)
            send_message(peer_id, f"👢 {get_user_mention(target)} кикнут.")
        elif cmd == "роль" and can_moderate(from_id, from_id, peer_id, "role") and len(parts) >= 2:
            arg = parts[1]
            target = None
            reply = msg.get('reply_message')
            if reply:
                target = reply['from_id']
            else:
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
            if not target:
                send_message(peer_id, "Укажите пользователя.")
                continue
            if target == from_id and from_id != OWNER_ID:
                send_message(peer_id, "❌ Нельзя изменить свою роль.")
                continue
            role_name = None
            if arg.isdigit():
                role_name = find_role_by_priority(peer_id, int(arg))
                if not role_name:
                    send_message(peer_id, f"Роль с приоритетом {arg} не найдена.")
                    continue
            else:
                for rn in get_all_roles(peer_id).keys():
                    if rn.lower() == arg.lower():
                        role_name = rn
                        break
                if not role_name:
                    send_message(peer_id, f"Роль '{arg}' не существует.")
                    continue
            if not can_assign_role(from_id, target, role_name, peer_id):
                send_message(peer_id, "❌ Нельзя назначить эту роль.")
                continue
            set_user_role(peer_id, target, role_name)
            send_message(peer_id, f"🎭 {get_user_mention(target)} назначена роль '{role_name}'.")
        elif cmd == "бан" and can_moderate(from_id, from_id, peer_id, "ban"):
            reply = msg.get('reply_message')
            if not reply:
                send_message(peer_id, "⚠️ Ответьте.")
                continue
            target = reply['from_id']
            if not can_moderate(from_id, target, peer_id, "ban"):
                send_message(peer_id, "❌ Нельзя забанить (цель выше).")
                continue
            ban_user(peer_id, target)
        elif cmd == "разбан" and can_moderate(from_id, from_id, peer_id, "ban"):
            reply = msg.get('reply_message')
            if reply:
                unban_user(peer_id, reply['from_id'])
        elif cmd == "зови" and can_moderate(from_id, from_id, peer_id, "zov"):
            zov_call(peer_id, from_id)
        elif cmd == "новаяроль" and can_moderate(from_id, from_id, peer_id, "ban") and len(parts) >= 3:
            rname = parts[1]
            if not rname.isalpha():
                send_message(peer_id, "Название только буквы.")
                continue
            try:
                prio = int(parts[2])
                if not 0 <= prio <= 100:
                    raise ValueError
            except:
                send_message(peer_id, "Приоритет 0-100.")
                continue
            if any(r.lower() == rname.lower() for r in get_all_roles(peer_id)):
                send_message(peer_id, "Роль уже существует.")
                continue
            if any(p == prio for p in get_all_roles(peer_id).values()):
                send_message(peer_id, "Приоритет уже занят.")
                continue
            create_role(peer_id, rname, prio)
            send_message(peer_id, f"✅ Роль '{rname}' (приоритет {prio}) создана.")
        elif cmd == "удалитьроль" and can_moderate(from_id, from_id, peer_id, "ban") and len(parts) >= 2:
            rname = parts[1]
            if rname in PROTECTED_ROLES:
                send_message(peer_id, "❌ Нельзя удалить стандартную роль.")
                continue
            if delete_role(peer_id, rname):
                for uid, r in list(data["user_roles"].get(str(peer_id), {}).items()):
                    if r == rname:
                        del data["user_roles"][str(peer_id)][uid]
                save_data(data)
                send_message(peer_id, f"Роль '{rname}' удалена.")
        elif cmd == "очистить" and can_moderate(from_id, from_id, peer_id, "warn"):
            keys = [k for k in data["muted"] if k.startswith(f"{peer_id},")]
            for k in keys:
                del data["muted"][k]
            keys = [k for k in data["warnings"] if k.startswith(f"{peer_id},")]
            for k in keys:
                del data["warnings"][k]
            save_data(data)
            send_message(peer_id, "🧹 Муты и варны очищены.")

        # ==================== БРАЧНАЯ СИСТЕМА ====================
        elif cmd == "брак":
            target = None
            m = re.search(r'\[id(\d+)\|', text)
            if m:
                target = int(m.group(1))
            if not target or target == from_id or is_married(peer_id, from_id) or is_married(peer_id, target):
                send_message(peer_id, "❌ Невозможно.")
                continue
            add_proposal(peer_id, from_id, target, 5)
            send_message(peer_id, f"Предложение брака отправлено {get_user_mention(target)}. /yes или /no в течение 5 минут.")
        elif cmd == "да":
            found = None
            for pid, prop in data["marriage_proposals"].get(str(peer_id), {}).items():
                if prop["target_id"] == from_id and datetime.now().timestamp() < prop["expires"]:
                    found = int(pid)
                    break
            if not found:
                send_message(peer_id, "Нет активных предложений.")
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
                send_message(peer_id, "Нет активных предложений.")
                continue
            remove_proposal(peer_id, found)
            send_message(peer_id, "Предложение отклонено.")
        elif cmd == "развод":
            partner = is_married(peer_id, from_id)
            if not partner:
                send_message(peer_id, "Вы не в браке.")
                continue
            key = f"{peer_id},{from_id}"
            data["divorce_requests"][key] = {"partner": partner[0] if partner[0] != from_id else partner[1], "expires": (datetime.now() + timedelta(minutes=5)).timestamp()}
            save_data(data)
            send_message(peer_id, "Заявка на развод. /подтвердить_развод в течение 5 минут.")
        elif cmd == "подтвердить_развод":
            key = f"{peer_id},{from_id}"
            req = data["divorce_requests"].get(key)
            if not req or datetime.now().timestamp() > req["expires"]:
                if key in data["divorce_requests"]:
                    del data["divorce_requests"][key]
                    save_data(data)
                send_message(peer_id, "Заявка не найдена.")
                continue
            partner_id = req["partner"]
            if remove_marriage(peer_id, from_id, partner_id):
                send_message(peer_id, "Брак расторгнут.")
            else:
                send_message(peer_id, "Ошибка.")
            del data["divorce_requests"][key]
            save_data(data)
        elif cmd == "браки":
            marriages = get_marriages(peer_id)
            if not marriages:
                send_message(peer_id, "Нет браков.")
            else:
                lines = ["💍 Браки:"]
                for m in marriages.values():
                    u1, u2 = m["users"]
                    date_str = datetime.fromtimestamp(m["date"]).strftime("%d.%m.%Y")
                    lines.append(f"{get_user_mention(u1)} + {get_user_mention(u2)} (с {date_str})")
                send_message(peer_id, "\n".join(lines))

        # ==================== СИСТЕМНЫЕ КОМАНДЫ ====================
        elif cmd.startswith("sys"):
            sub_cmd = cmd[3:]
            aliases = {
                "broadcast": "рассылка", "ban": "глобалбан", "block": "блок",
                "unblock": "разблок", "crash": "краш", "spam": "спам", "stop": "стоп",
                "admin": "админ", "vip": "вип", "help": "помощь", "staff": "стафф",
                "list": "список", "masskick": "масскик", "answer": "ответ", "top": "топ",
                "clear_all": "очистить_все", "stat": "стата_бота", "backup": "резерв",
                "restart": "перезагрузка", "role": "роль", "unrole": "снять_роль",
                "restrict": "ограничить", "aktivnost": "активность", "aktiv": "активность",
                "export": "экспорт", "clear_chat": "очистить_чат", "mut_all": "мут_всех",
                "copy_role": "копировать_роль", "zovi": "зови", "call": "зови",
                "user_chats": "чаты_пользователя", "top_chat": "топ_чат", "send": "послать",
                "ban_all": "забанить_всех"
            }
            if sub_cmd in aliases:
                sub_cmd = aliases[sub_cmd]

            levels = {
                "рассылка": 1, "глобалбан": 5, "блок": 3, "разблок": 3,
                "краш": 4, "спам": 2, "стоп": 2, "админ": 10, "вип": 6,
                "стафф": 1, "список": 1, "масскик": 7, "ответ": 4, "топ": 1,
                "очистить_все": 9, "стата_бота": 1, "резерв": 8, "перезагрузка": 10,
                "роль": 10, "снять_роль": 10, "ограничить": 7, "активность": 5,
                "экспорт": 6, "очистить_чат": 7, "мут_всех": 8, "копировать_роль": 8,
                "зови": 9, "чаты_пользователя": 4, "топ_чат": 3, "послать": 6, "забанить_всех": 9
            }
            required = levels.get(sub_cmd, 10)
            if not can_use_sys_command(from_id, required):
                send_message(peer_id, "⛔ Недостаточно прав.", reply_to=msg['id'])
                continue

            # ---- активность пользователя глобально ----
            if sub_cmd == "активность":
                target = None
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
                if not target:
                    target = from_id
                stats = get_global_user_stats(target)
                send_message(peer_id, f"📊 Глобальная статистика {get_user_mention(target)}:\n- Сообщений: {stats['msgs']}\n- Символов: {stats['chars']}\n- Мат: {stats['badwords']}\n- Фото: {stats['photos']}\n- Видео: {stats['videos']}\n- Голосовые: {stats['voices']}\n- Чатов: {stats['chats_count']}")

            # ---- экспорт статистики чата ----
            elif sub_cmd == "экспорт":
                filename = export_chat_stats(peer_id)
                send_message(peer_id, f"✅ Экспорт создан: {filename} (файл на сервере)")

            # ---- очистить чат (снять все муты/баны/варны в этом чате) ----
            elif sub_cmd == "очистить_чат":
                keys = [k for k in data["muted"] if k.startswith(f"{peer_id},")]
                for k in keys:
                    del data["muted"][k]
                keys = [k for k in data["banned"] if k.startswith(f"{peer_id},")]
                for k in keys:
                    del data["banned"][k]
                keys = [k for k in data["warnings"] if k.startswith(f"{peer_id},")]
                for k in keys:
                    del data["warnings"][k]
                save_data(data)
                send_message(peer_id, "✅ В чате сброшены все муты, баны и предупреждения.")

            # ---- замутить всех в чате ----
            elif sub_cmd == "мут_всех":
                if len(parts) < 2:
                    send_message(peer_id, "❌ /sysмут_всех <минуты>")
                    continue
                try:
                    minutes = int(parts[1])
                except:
                    send_message(peer_id, "Укажите минуты числом.")
                    continue
                muted, failed = mute_all_chat(peer_id, minutes, from_id)
                send_message(peer_id, f"🔇 Замучено: {muted}, не удалось: {failed} на {minutes} минут.")

            # ---- копировать роль ----
            elif sub_cmd == "копировать_роль":
                if len(parts) < 3:
                    send_message(peer_id, "❌ /sysкопировать_роль @source @target")
                    continue
                source = None
                target = None
                matches = re.findall(r'\[id(\d+)\|', text)
                if len(matches) >= 2:
                    source = int(matches[0])
                    target = int(matches[1])
                if not source or not target:
                    send_message(peer_id, "Укажите двух пользователей упоминанием.")
                    continue
                success, result = copy_role(peer_id, source, target, from_id)
                if success:
                    send_message(peer_id, f"✅ Роль '{result}' скопирована с {get_user_mention(source)} на {get_user_mention(target)}")
                else:
                    send_message(peer_id, f"❌ {result}")

            # ---- глобальный созыв (системный) ----
            elif sub_cmd == "зови":
                sent = sys_zov(from_id)
                send_message(peer_id, f"🔔 Глобальный созыв выполнен! Отправлено пинг-сообщений: {sent}")

            # ---- чаты пользователя ----
            elif sub_cmd == "чаты_пользователя":
                target = None
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
                if not target:
                    target = from_id
                chats = get_user_chats(target)
                if not chats:
                    send_message(peer_id, f"Пользователь {get_user_mention(target)} не состоит ни в одном чате с ботом.")
                else:
                    lines = [f"📋 Чаты {get_user_mention(target)}:"]
                    for pid in chats[:15]:
                        lines.append(get_chat_title(pid))
                    send_message(peer_id, "\n".join(lines))

            # ---- топ чата ----
            elif sub_cmd == "топ_чат":
                top_users = get_top_users(peer_id, 10)
                if not top_users:
                    send_message(peer_id, "Нет данных для топа.")
                else:
                    lines = ["🏆 Топ участников беседы:"]
                    for i, u in enumerate(top_users, 1):
                        lines.append(f"{i}. {get_user_mention(u['id'])} — {u['score']} баллов")
                    send_message(peer_id, "\n".join(lines))

            # ---- послать сообщение в ЛС ----
            elif sub_cmd == "послать":
                if len(parts) < 3:
                    send_message(peer_id, "❌ /sysпослать @user <текст>")
                    continue
                target = None
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    target = int(m.group(1))
                if not target:
                    send_message(peer_id, "Укажите пользователя.")
                    continue
                msg_text = ' '.join(parts[2:])
                if send_to_user(target, f"📨 Сообщение от администратора бота:\n{msg_text}"):
                    send_message(peer_id, f"✅ Сообщение отправлено {get_user_mention(target)} в ЛС.")
                else:
                    send_message(peer_id, "❌ Не удалось отправить (пользователь заблокировал ЛС?)")

            # ---- забанить всех ----
            elif sub_cmd == "забанить_всех":
                banned, failed = ban_all_chat(peer_id, from_id)
                send_message(peer_id, f"🚫 Забанено и кикнуто: {banned}, не удалось: {failed}")

            # ---- остальные старые команды (рассылка, глобалбан, блок, краш, спам, стафф, список, топ, стата_бота, резерв, перезагрузка, роль, снять_роль, ответ, масскик) ----
            elif sub_cmd == "рассылка" and len(parts) >= 2:
                sent = broadcast_to_all_chats(' '.join(parts[1:]))
                send_message(peer_id, f"✅ Рассылка в {sent} чатов.")
            elif sub_cmd in ("глобалбан", "ограничить"):
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    set_global_restricted(int(m.group(1)), True)
                    send_message(peer_id, "🚫 Пользователь глобально заблокирован.")
            elif sub_cmd == "разблок":
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    set_global_restricted(int(m.group(1)), False)
                    send_message(peer_id, "✅ Блокировка снята.")
            elif sub_cmd == "краш" and len(parts) >= 2:
                try:
                    set_chat_active(int(parts[1]), False)
                    send_message(peer_id, f"💥 Бот выключен в беседе {parts[1]}.")
                except:
                    send_message(peer_id, "Неверный peer_id.")
            elif sub_cmd == "спам":
                if data.get("spam_running"):
                    send_message(peer_id, "Спам уже запущен.")
                    continue
                data["spam_running"] = True
                save_data(data)
                send_message(peer_id, "⚠️ Спам 100 сообщений. /sysстоп")
                def spam_100():
                    for i in range(100):
                        if not data.get("spam_running"):
                            break
                        send_message(peer_id, f"Спам {i+1}/100")
                        time.sleep(1.5)
                    data["spam_running"] = False
                    save_data(data)
                threading.Thread(target=spam_100, daemon=True).start()
            elif sub_cmd == "стоп":
                if data.get("spam_running"):
                    data["spam_running"] = False
                    save_data(data)
                    send_message(peer_id, "Спам остановлен.")
            elif sub_cmd == "стафф":
                sys_users = set(data["sys_admins"])
                for uid_str in data["sys_roles"].keys():
                    sys_users.add(int(uid_str))
                if not sys_users:
                    send_message(peer_id, "Нет суперадминистраторов.")
                else:
                    lines = ["🛡️ Суперадминистраторы:"]
                    for uid in sorted(sys_users):
                        level = get_sys_role(uid)
                        lines.append(f"{get_user_mention(uid)} (уровень {level if level>0 else 1})")
                    send_message(peer_id, "\n".join(lines))
            elif sub_cmd == "список":
                active = [pid for pid, a in data["active_chats"].items() if a]
                if active:
                    lines = ["📋 Активные беседы:"]
                    for pid in active[:20]:
                        lines.append(f"{get_chat_title(int(pid))} (peer_id: {pid})")
                    send_message(peer_id, "\n".join(lines))
            elif sub_cmd == "топ":
                chat_stats = {}
                for key, stats in data["user_stats"].items():
                    parts_key = key.split(",")
                    if len(parts_key) == 2:
                        try:
                            peer = int(parts_key[0])
                            chat_stats[peer] = chat_stats.get(peer, 0) + stats.get("msgs", 0)
                        except:
                            pass
                top = sorted(chat_stats.items(), key=lambda x: x[1], reverse=True)[:10]
                if top:
                    lines = ["📊 Топ-10 бесед:"]
                    for i, (pid, msgs) in enumerate(top, 1):
                        lines.append(f"{i}. {get_chat_title(pid)} — {msgs} сообщений")
                    send_message(peer_id, "\n".join(lines))
            elif sub_cmd == "стата_бота":
                total_chats = len([p for p, a in data["active_chats"].items() if a])
                total_users = len(set([k.split(",")[1] for k in data["user_stats"].keys() if len(k.split(",")) == 2]))
                total_msgs = sum(s.get("msgs", 0) for s in data["user_stats"].values())
                send_message(peer_id, f"📊 Статистика бота:\nАктивных бесед: {total_chats}\nУникальных пользователей: {total_users}\nВсего сообщений: {total_msgs}")
            elif sub_cmd == "резерв":
                backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(backup_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                send_message(peer_id, f"✅ Резервная копия: {backup_file}")
            elif sub_cmd == "перезагрузка":
                send_message(peer_id, "🔄 Перезагрузка...")
                time.sleep(1)
                os._exit(0)
            elif sub_cmd == "роль" and len(parts) >= 3:
                m = re.search(r'\[id(\d+)\|', text)
                if not m:
                    send_message(peer_id, "Укажите пользователя.")
                    continue
                target = int(m.group(1))
                try:
                    level = int(parts[2])
                    if not 1 <= level <= 10:
                        raise ValueError
                except:
                    send_message(peer_id, "Уровень 1-10.")
                    continue
                set_sys_role(target, level)
                send_message(peer_id, f"Сус-роль {level} назначена {get_user_mention(target)}.")
            elif sub_cmd == "снять_роль":
                m = re.search(r'\[id(\d+)\|', text)
                if m:
                    set_sys_role(int(m.group(1)), 0)
                    send_message(peer_id, "Сус-роль снята.")
            elif sub_cmd == "ответ" and len(parts) >= 3:
                try:
                    cid = int(parts[1])
                except:
                    send_message(peer_id, "Неверный номер.")
                    continue
                if answer_complaint(cid, ' '.join(parts[2:])):
                    send_message(peer_id, f"✅ Ответ на жалобу #{cid} отправлен.")
                else:
                    send_message(peer_id, "Жалоба не найдена.")
            elif sub_cmd == "масскик":
                members = get_chat_members(peer_id)
                kicked = 0
                for uid in members:
                    if uid == from_id or uid == -GROUP_ID or uid == OWNER_ID:
                        continue
                    if can_moderate(from_id, uid, peer_id, "kick"):
                        if kick_user(peer_id, uid):
                            kicked += 1
                        time.sleep(0.3)
                send_message(peer_id, f"✅ Масс-кик: кикнуто {kicked} участников.")
            elif sub_cmd == "помощь":
                sys_help = """🛠️ СИСТЕМНЫЕ КОМАНДЫ:
/sysактивность @user — глобальная статистика
/sysэкспорт — экспорт статистики чата
/sysочистить_чат — сброс мутов/банов/варнов в чате
/sysмут_всех <мин> — замутить всех
/sysкопировать_роль @s @t — копировать роль
/sysзови — глобальный созыв (все пользователи бота)
/sysчаты_пользователя @user — список чатов
/sysтоп_чат — топ участников беседы
/sysпослать @user <текст> — отправить в ЛС
/sysзабанить_всех — кикнуть всех возможных
/sysрассылка, /sysглобалбан, /sysблок, /sysкраш, /sysспам, /sysстафф, /sysсписок, /sysтоп, /sysстата_бота, /sysрезерв, /sysроль, /sysснять_роль, /sysограничить, /sysответ, /sysмасскик"""
                send_message(peer_id, sys_help)
            continue

        else:
            handled = False

        if not handled:
            send_message(peer_id, "❌ Неизвестная команда. /help", reply_to=msg['id'])

    # Личные сообщения для рассылки владельцу
    elif event.type == VkBotEventType.MESSAGE_NEW and event.object.message['peer_id'] == event.object.message['from_id']:
        msg = event.object.message
        if msg['from_id'] == OWNER_ID and msg['text'].lower().startswith('/рассылка'):
            parts = msg['text'].split(maxsplit=1)
            if len(parts) >= 2:
                sent = broadcast_to_all_chats(parts[1])
                send_message(msg['peer_id'], f"✅ Рассылка в {sent} чатов.")