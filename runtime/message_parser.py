import re

from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.message.components import BaseMessageComponent

GROUP_MESSAGE = "GROUP_AT_MESSAGE_CREATE"
DIRECT_MESSAGE = "C2C_MESSAGE_CREATE"
INTERACTION = "INTERACTION_CREATE"
CHANNEL_MESSAGE = "AT_MESSAGE_CREATE"
CHANNEL_MESSAGE_CREATE = "MESSAGE_CREATE"
CHANNEL_DIRECT_MESSAGE = "DIRECT_MESSAGE_CREATE"
GROUP_MSG_REJECT = "GROUP_MSG_REJECT"
GROUP_MSG_RECEIVE = "GROUP_MSG_RECEIVE"
GROUP_ADD_ROBOT = "GROUP_ADD_ROBOT"
GROUP_DEL_ROBOT = "GROUP_DEL_ROBOT"
FRIEND_ADD = "FRIEND_ADD"
FRIEND_DEL = "FRIEND_DEL"
GUILD_CREATE = "GUILD_CREATE"
GUILD_UPDATE = "GUILD_UPDATE"
GUILD_DELETE = "GUILD_DELETE"
CHANNEL_CREATE = "CHANNEL_CREATE"
CHANNEL_UPDATE = "CHANNEL_UPDATE"
CHANNEL_DELETE = "CHANNEL_DELETE"
GUILD_MEMBER_ADD = "GUILD_MEMBER_ADD"
GUILD_MEMBER_UPDATE = "GUILD_MEMBER_UPDATE"
GUILD_MEMBER_REMOVE = "GUILD_MEMBER_REMOVE"
SUBSCRIBE_MESSAGE_STATUS = "SUBSCRIBE_MESSAGE_STATUS"
C2C_MSG_REJECT = "C2C_MSG_REJECT"
C2C_MSG_RECEIVE = "C2C_MSG_RECEIVE"
PUBLIC_MESSAGE_DELETE = "PUBLIC_MESSAGE_DELETE"
DIRECT_MESSAGE_DELETE = "DIRECT_MESSAGE_DELETE"
MESSAGE_REACTION_ADD = "MESSAGE_REACTION_ADD"
MESSAGE_REACTION_REMOVE = "MESSAGE_REACTION_REMOVE"
MESSAGE_AUDIT_PASS = "MESSAGE_AUDIT_PASS"
MESSAGE_AUDIT_REJECT = "MESSAGE_AUDIT_REJECT"
AUDIO_START = "AUDIO_START"
AUDIO_FINISH = "AUDIO_FINISH"
AUDIO_ON_MIC = "AUDIO_ON_MIC"
AUDIO_OFF_MIC = "AUDIO_OFF_MIC"
AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER = "AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER"
AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT = "AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT"
OPEN_FORUM_THREAD_CREATE = "OPEN_FORUM_THREAD_CREATE"
OPEN_FORUM_THREAD_UPDATE = "OPEN_FORUM_THREAD_UPDATE"
OPEN_FORUM_THREAD_DELETE = "OPEN_FORUM_THREAD_DELETE"
OPEN_FORUM_POST_CREATE = "OPEN_FORUM_POST_CREATE"
OPEN_FORUM_POST_DELETE = "OPEN_FORUM_POST_DELETE"
OPEN_FORUM_REPLY_CREATE = "OPEN_FORUM_REPLY_CREATE"
OPEN_FORUM_REPLY_DELETE = "OPEN_FORUM_REPLY_DELETE"


def _strip_bot_mention(raw: str, bot_id: str | None) -> str:
    if not raw:
        return ""
    content = raw
    if bot_id:
        for prefix in (f"<@!{bot_id}>", f"<@{bot_id}>"):
            if content.startswith(prefix):
                content = content[len(prefix):].lstrip()
                break
    if content.startswith("<@") and ">" in content:
        end = content.find(">")
        if end != -1:
            content = content[end + 1 :].lstrip()
    return content


def _swap_ids(uid: str | None, unid: str | None, should_swap: bool):
    if should_swap and unid:
        return unid, uid, uid
    return uid, unid or uid, uid


def _append_image_attachments(content: str, attachments) -> tuple[str, list[BaseMessageComponent]]:
    msg_chain: list[BaseMessageComponent] = []
    if attachments and isinstance(attachments, list):
        for att in attachments:
            if str(att.get("content_type", "")).startswith("image"):
                url = att.get("url", "")
                if url and not url.startswith("http"):
                    url = "https://" + url
                if content:
                    content = f"{content}<{url}>"
                else:
                    content = f"<{url}>"
                msg_chain.append(Image.fromURL(url))
                break
    return content, msg_chain


def _pick_value(data: dict, *keys):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _normalize_event_type(value) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value:
        return ""
    value = value.replace("-", "_").replace(".", "_").replace("/", "_")
    if "_" in value:
        return value.upper()
    if any(ch.isupper() for ch in value[1:]):
        value = re.sub(r"(?<!^)(?=[A-Z])", "_", value)
        return value.upper()
    return value.upper()


def parse_event(
    payload: dict,
    bot_id: str | None = None,
    use_union_id_for_group: bool = False,
    use_union_id_for_channel: bool = False,
) -> AstrBotMessage:
    """
    将 QQ 事件转换为 AstrBotMessage。
    覆盖：群 at、频道 at、私聊、C2C、频道 DM、按钮回调、加群/好友等事件。
    """
    raw_t = (
        payload.get("t")
        or payload.get("event_type")
        or payload.get("eventType")
        or payload.get("type")
        or ""
    )
    if not raw_t and isinstance(payload.get("d"), dict):
        raw_t = (
            payload["d"].get("t")
            or payload["d"].get("event_type")
            or payload["d"].get("eventType")
            or payload["d"].get("type")
            or ""
        )
    data = (
        payload.get("d")
        or payload.get("data")
        or payload.get("event_data")
        or payload.get("eventData")
        or {}
    )
    if isinstance(data, dict):
        inner_type = data.get("event_type") or data.get("eventType") or data.get("type")
        if not raw_t and inner_type:
            raw_t = inner_type
        inner_data = data.get("event_data") or data.get("eventData") or data.get("data")
        if isinstance(inner_data, dict):
            data = inner_data
    if not isinstance(data, dict):
        data = {}
    t = _normalize_event_type(raw_t)
    abm = AstrBotMessage()
    abm.raw_message = payload
    abm.message_id = data.get("id") or payload.get("id")
    abm.qq_event_id = payload.get("id")
    abm.timestamp = data.get("timestamp")
    abm.qq_event_type = t

    msg_chain: list[BaseMessageComponent] = []

    if t == GROUP_MESSAGE:
        abm.type = MessageType.GROUP_MESSAGE
        content = data.get("content", "") or ""
        content = content[1:] if content.startswith("/") else content
        content, attachment_chain = _append_image_attachments(content.strip(), data.get("attachments"))
        msg_chain.append(Plain(content.strip()))
        msg_chain.extend(attachment_chain)

        user_id, union_openid, raw_user_id = _swap_ids(
            data.get("author", {}).get("member_openid"),
            data.get("author", {}).get("union_openid"),
            use_union_id_for_group,
        )
        group_id = data.get("group_id") or data.get("group_openid")
        abm.sender = MessageMember(user_id or "", data.get("author", {}).get("username", ""))
        abm.group_id = group_id
        abm.message_str = content.strip()
        abm.message = msg_chain
        abm.session_id = abm.group_id
        abm.qq_scene = "group"
        abm.qq_union_openid = union_openid
        abm.qq_raw_user_id = raw_user_id
        abm.qq_is_group = True
        abm.qq_is_private = False
        abm.qq_supports_keyboard = True

    elif t in {GROUP_MSG_REJECT, GROUP_MSG_RECEIVE}:
        abm.type = MessageType.OTHER_MESSAGE
        group_id = _pick_value(data, "group_openid", "group_id", "groupId")
        op_user_id = _pick_value(data, "op_member_openid", "op_user_id", "opUserId")
        abm.group_id = group_id
        abm.sender = MessageMember(str(op_user_id or ""), "")
        abm.message_str = f"{t} group={group_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = group_id or ""
        abm.qq_scene = "group_msg_setting"
        abm.qq_op_user_id = op_user_id
        abm.qq_is_group = True
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {CHANNEL_MESSAGE, CHANNEL_MESSAGE_CREATE}:
        abm.type = MessageType.GROUP_MESSAGE
        raw_content = data.get("content", "") or ""
        mentions = data.get("mentions")
        if isinstance(mentions, list) and mentions:
            bot_id = bot_id or mentions[0].get("id")
        content = _strip_bot_mention(raw_content, bot_id)
        content = content[1:] if content.startswith("/") else content
        content, attachment_chain = _append_image_attachments(content.strip(), data.get("attachments"))
        msg_chain.append(Plain(content))
        msg_chain.extend(attachment_chain)

        user_id, union_openid, raw_user_id = _swap_ids(
            data.get("author", {}).get("id"),
            data.get("author", {}).get("union_openid"),
            use_union_id_for_channel,
        )
        abm.sender = MessageMember(str(user_id or ""), str(data.get("author", {}).get("username", "")))
        abm.group_id = data.get("channel_id")
        abm.channel_id = data.get("channel_id")
        abm.guild_id = data.get("guild_id")
        abm.message_str = content
        abm.message = msg_chain
        abm.session_id = abm.group_id
        abm.qq_scene = "channel"
        abm.qq_union_openid = union_openid
        abm.qq_raw_user_id = raw_user_id
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = True

    elif t == DIRECT_MESSAGE:
        abm.type = MessageType.FRIEND_MESSAGE
        content = data.get("content", "") or ""
        content = content[1:] if content.startswith("/") else content
        content, attachment_chain = _append_image_attachments(content.strip(), data.get("attachments"))
        msg_chain.append(Plain(content.strip()))
        msg_chain.extend(attachment_chain)

        user_id, union_openid, raw_user_id = _swap_ids(
            data.get("author", {}).get("user_openid"),
            data.get("author", {}).get("union_openid"),
            use_union_id_for_group,
        )
        abm.sender = MessageMember(user_id or "", data.get("author", {}).get("username", ""))
        abm.message_str = content.strip()
        abm.message = msg_chain
        abm.session_id = abm.sender.user_id
        abm.qq_scene = "c2c"
        abm.qq_union_openid = union_openid
        abm.qq_raw_user_id = raw_user_id
        abm.qq_is_group = False
        abm.qq_is_private = True
        abm.qq_supports_keyboard = True

    elif t == CHANNEL_DIRECT_MESSAGE:
        abm.type = MessageType.FRIEND_MESSAGE
        content = data.get("content", "") or ""
        content = content[1:] if content.startswith("/") else content
        content, attachment_chain = _append_image_attachments(content.strip(), data.get("attachments"))
        msg_chain.append(Plain(content.strip()))
        msg_chain.extend(attachment_chain)

        user_id, union_openid, raw_user_id = _swap_ids(
            data.get("author", {}).get("id"),
            data.get("author", {}).get("union_openid"),
            use_union_id_for_channel,
        )
        abm.sender = MessageMember(str(user_id or ""), str(data.get("author", {}).get("username", "")))
        abm.guild_id = data.get("guild_id")
        abm.channel_id = data.get("channel_id")
        abm.message_str = content.strip()
        abm.message = msg_chain
        abm.session_id = abm.guild_id or abm.sender.user_id
        abm.qq_scene = "channel_dm"
        abm.qq_union_openid = union_openid
        abm.qq_raw_user_id = raw_user_id
        abm.qq_is_group = False
        abm.qq_is_private = True
        abm.qq_supports_keyboard = False

    elif t == INTERACTION:
        if data.get("type") == 13:
            abm.qq_ignore = True
            abm.message_str = ""
            abm.message = []
            abm.session_id = ""
            return abm
        chat_type = data.get("chat_type")
        scene = data.get("scene")
        button_data = data.get("data", {}).get("resolved", {}).get("button_data")
        content = button_data or ""
        content = content[1:] if content.startswith("/") else content
        msg_chain.append(Plain(content))

        if chat_type == 1 or scene == "group":
            abm.type = MessageType.GROUP_MESSAGE
            group_id = data.get("group_openid") or data.get("group_id")
            user_id = data.get("group_member_openid") or data.get("author", {}).get("id")
            abm.group_id = group_id
            abm.session_id = abm.group_id
            abm.qq_scene = "group"
            abm.qq_is_group = True
            abm.qq_is_private = False
        elif chat_type == 2 or scene == "c2c":
            abm.type = MessageType.FRIEND_MESSAGE
            user_id = data.get("user_openid") or data.get("author", {}).get("id")
            abm.session_id = user_id
            abm.qq_scene = "c2c"
            abm.qq_is_group = False
            abm.qq_is_private = True
        else:
            group_id = data.get("group_openid") or data.get("group_id")
            user_id = (
                data.get("group_member_openid")
                or data.get("user_openid")
                or data.get("author", {}).get("id")
            )
            if group_id:
                abm.type = MessageType.GROUP_MESSAGE
                abm.group_id = group_id
                abm.session_id = group_id
                abm.qq_scene = "group"
                abm.qq_is_group = True
                abm.qq_is_private = False
            else:
                abm.type = MessageType.FRIEND_MESSAGE
                abm.session_id = user_id or ""
                abm.qq_scene = "c2c"
                abm.qq_is_group = False
                abm.qq_is_private = True

        abm.sender = MessageMember(str(user_id or ""), "")
        abm.message_str = content
        abm.message = msg_chain
        abm.qq_supports_keyboard = True

    elif t in {MESSAGE_REACTION_ADD, MESSAGE_REACTION_REMOVE}:
        abm.type = MessageType.OTHER_MESSAGE
        guild_id = _pick_value(data, "guild_id", "guildId")
        channel_id = _pick_value(data, "channel_id", "channelId")
        user_id = _pick_value(data, "user_id", "userId")
        emoji = data.get("emoji") or {}
        target = data.get("target") or {}
        abm.guild_id = guild_id
        abm.channel_id = channel_id
        abm.sender = MessageMember(str(user_id or ""), "")
        abm.message_str = f"{t} user={user_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = channel_id or guild_id or ""
        abm.qq_scene = "reaction"
        abm.qq_raw_user_id = user_id
        abm.qq_reaction_emoji_id = _pick_value(emoji, "id")
        abm.qq_reaction_emoji_type = _pick_value(emoji, "type")
        abm.qq_reaction_target_id = _pick_value(target, "id")
        abm.qq_reaction_target_type = _pick_value(target, "type")
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {MESSAGE_AUDIT_PASS, MESSAGE_AUDIT_REJECT}:
        abm.type = MessageType.OTHER_MESSAGE
        guild_id = _pick_value(data, "guild_id", "guildId")
        channel_id = _pick_value(data, "channel_id", "channelId")
        audit_id = _pick_value(data, "audit_id", "auditId")
        message_id = _pick_value(data, "message_id", "msg_id", "id")
        audit_time = _pick_value(data, "audit_time", "auditTime")
        abm.guild_id = guild_id
        abm.channel_id = channel_id
        abm.sender = MessageMember("", "")
        abm.message_str = f"{t} audit={audit_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = channel_id or guild_id or ""
        abm.qq_scene = "audit"
        abm.qq_audit_id = audit_id
        abm.qq_audit_time = audit_time
        abm.qq_audit_message_id = message_id
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t == GROUP_ADD_ROBOT:
        abm.type = MessageType.GROUP_MESSAGE
        group_id = data.get("group_openid")
        user_id = data.get("op_member_openid")
        abm.group_id = group_id
        abm.sender = MessageMember(str(user_id or ""), "")
        abm.message_str = f"机器人被邀请加入群聊 {group_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = group_id or ""
        abm.qq_scene = "group"
        abm.qq_union_openid = user_id
        abm.qq_raw_user_id = user_id
        abm.qq_is_group = True
        abm.qq_is_private = False
        abm.qq_supports_keyboard = True

    elif t == GROUP_DEL_ROBOT:
        abm.type = MessageType.GROUP_MESSAGE
        group_id = data.get("group_openid")
        user_id = data.get("op_member_openid")
        abm.group_id = group_id
        abm.sender = MessageMember(str(user_id or ""), "")
        abm.message_str = f"机器人被移出群聊 {group_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = group_id or ""
        abm.qq_scene = "group"
        abm.qq_union_openid = user_id
        abm.qq_raw_user_id = user_id
        abm.qq_is_group = True
        abm.qq_is_private = False
        abm.qq_supports_keyboard = True

    elif t == FRIEND_ADD:
        abm.type = MessageType.FRIEND_MESSAGE
        user_id = data.get("openid")
        abm.sender = MessageMember(str(user_id or ""), "")
        abm.message_str = f"用户 {user_id} 添加机器人为好友"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = user_id or ""
        abm.qq_scene = "c2c"
        abm.qq_union_openid = user_id
        abm.qq_raw_user_id = user_id
        abm.qq_is_group = False
        abm.qq_is_private = True
        abm.qq_supports_keyboard = False

    elif t == FRIEND_DEL:
        abm.type = MessageType.FRIEND_MESSAGE
        user_id = data.get("openid")
        abm.sender = MessageMember(str(user_id or ""), "")
        abm.message_str = f"用户 {user_id} 删除机器人好友"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = user_id or ""
        abm.qq_scene = "c2c"
        abm.qq_union_openid = user_id
        abm.qq_raw_user_id = user_id
        abm.qq_is_group = False
        abm.qq_is_private = True
        abm.qq_supports_keyboard = False

    elif t in {GUILD_CREATE, GUILD_UPDATE, GUILD_DELETE}:
        abm.type = MessageType.OTHER_MESSAGE
        guild_id = _pick_value(data, "id", "guild_id", "guildId")
        op_user_id = _pick_value(data, "op_user_id", "opUserId")
        abm.guild_id = guild_id
        abm.sender = MessageMember(str(op_user_id or ""), "")
        abm.message_str = f"{t} guild={guild_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = guild_id or ""
        abm.qq_scene = "guild"
        abm.qq_op_user_id = op_user_id
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {CHANNEL_CREATE, CHANNEL_UPDATE, CHANNEL_DELETE}:
        abm.type = MessageType.OTHER_MESSAGE
        channel_id = _pick_value(data, "id", "channel_id", "channelId")
        guild_id = _pick_value(data, "guild_id", "guildId")
        op_user_id = _pick_value(data, "op_user_id", "opUserId")
        abm.channel_id = channel_id
        abm.guild_id = guild_id
        abm.sender = MessageMember(str(op_user_id or ""), "")
        abm.message_str = f"{t} channel={channel_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = channel_id or guild_id or ""
        abm.qq_scene = "channel_event"
        abm.qq_op_user_id = op_user_id
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {GUILD_MEMBER_ADD, GUILD_MEMBER_UPDATE, GUILD_MEMBER_REMOVE}:
        abm.type = MessageType.OTHER_MESSAGE
        guild_id = _pick_value(data, "guild_id", "guildId")
        op_user_id = _pick_value(data, "op_user_id", "opUserId", "op_member_openid")
        user_info = data.get("user") or data.get("member") or {}
        user_id = _pick_value(user_info, "id", "user_id", "userId", "user_openid", "openid")
        if not user_id:
            user_id = _pick_value(data, "user_id", "userId", "member_openid", "user_openid", "openid")
        union_openid = _pick_value(user_info, "union_openid", "unionOpenid")
        abm.guild_id = guild_id
        abm.sender = MessageMember(str(user_id or ""), str(user_info.get("username", "")))
        abm.message_str = f"{t} user={user_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = guild_id or ""
        abm.qq_scene = "guild_member"
        abm.qq_op_user_id = op_user_id
        abm.qq_union_openid = union_openid
        abm.qq_raw_user_id = user_id
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {
        OPEN_FORUM_THREAD_CREATE,
        OPEN_FORUM_THREAD_UPDATE,
        OPEN_FORUM_THREAD_DELETE,
        OPEN_FORUM_POST_CREATE,
        OPEN_FORUM_POST_DELETE,
        OPEN_FORUM_REPLY_CREATE,
        OPEN_FORUM_REPLY_DELETE,
    }:
        abm.type = MessageType.OTHER_MESSAGE
        guild_id = _pick_value(data, "guild_id", "guildId")
        channel_id = _pick_value(data, "channel_id", "channelId")
        author_id = _pick_value(data, "author_id", "authorId", "user_id", "userId")
        abm.guild_id = guild_id
        abm.channel_id = channel_id
        abm.sender = MessageMember(str(author_id or ""), "")
        abm.message_str = f"{t} author={author_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = channel_id or guild_id or ""
        abm.qq_scene = "forum"
        abm.qq_raw_user_id = author_id
        abm.qq_forum_event = t
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {PUBLIC_MESSAGE_DELETE, DIRECT_MESSAGE_DELETE}:
        abm.type = MessageType.OTHER_MESSAGE
        guild_id = data.get("guild_id")
        channel_id = data.get("channel_id")
        op_user_id = _pick_value(data, "op_user_id", "opUserId")
        recall_message_id = _pick_value(data, "message_id", "msg_id", "id")
        abm.guild_id = guild_id
        abm.channel_id = channel_id
        abm.sender = MessageMember(str(op_user_id or ""), "")
        abm.message_str = f"{t} message={recall_message_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = channel_id or guild_id or ""
        abm.qq_scene = "channel_recall" if t == PUBLIC_MESSAGE_DELETE else "channel_dm_recall"
        abm.qq_op_user_id = op_user_id
        abm.qq_recall_message_id = recall_message_id
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {SUBSCRIBE_MESSAGE_STATUS, C2C_MSG_REJECT, C2C_MSG_RECEIVE}:
        abm.type = MessageType.OTHER_MESSAGE
        user_id = _pick_value(data, "user_id", "openid", "user_openid", "id")
        union_openid = data.get("union_openid")
        status = _pick_value(data, "subscribe_status", "status")
        if t == C2C_MSG_REJECT:
            status = status or "reject"
        if t == C2C_MSG_RECEIVE:
            status = status or "receive"
        abm.sender = MessageMember(str(user_id or ""), "")
        abm.message_str = f"{t} status={status}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = user_id or ""
        abm.qq_scene = "subscribe"
        abm.qq_union_openid = union_openid
        abm.qq_raw_user_id = user_id
        abm.qq_subscribe_status = status
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    elif t in {
        AUDIO_START,
        AUDIO_FINISH,
        AUDIO_ON_MIC,
        AUDIO_OFF_MIC,
        AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER,
        AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT,
    }:
        abm.type = MessageType.OTHER_MESSAGE
        guild_id = data.get("guild_id")
        channel_id = data.get("channel_id")
        op_user_id = _pick_value(data, "op_user_id", "opUserId")
        user_info = data.get("user") or {}
        user_id = _pick_value(user_info, "id") or _pick_value(data, "user_id", "member_id", "id")
        union_openid = _pick_value(user_info, "union_openid")
        channel_type = _pick_value(data, "channel_type")
        abm.guild_id = guild_id
        abm.channel_id = channel_id
        abm.sender = MessageMember(str(user_id or op_user_id or ""), "")
        abm.message_str = f"{t} user={user_id}"
        abm.message = [Plain(abm.message_str)]
        abm.session_id = channel_id or guild_id or ""
        abm.qq_scene = "audio"
        abm.qq_op_user_id = op_user_id
        abm.qq_union_openid = union_openid
        abm.qq_raw_user_id = user_id
        abm.qq_audio_event = t
        abm.qq_audio_channel_type = channel_type
        abm.qq_is_group = False
        abm.qq_is_private = False
        abm.qq_supports_keyboard = False

    else:
        abm.type = MessageType.GROUP_MESSAGE
        abm.message_str = ""
        abm.message = []
        abm.session_id = ""

    abm.self_id = bot_id or getattr(abm, "self_id", None) or "qq_restapi"
    if t in {GROUP_MESSAGE, CHANNEL_MESSAGE}:
        if not any(isinstance(comp, At) for comp in msg_chain):
            msg_chain.insert(0, At(qq=abm.self_id))
            abm.message = msg_chain
    return abm
