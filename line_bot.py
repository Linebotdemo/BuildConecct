from dotenv import load_dotenv
load_dotenv()

import os
import uuid
import tempfile
import datetime
import asyncio
import logging
import textwrap
from main import get_line_user, create_line_user, update_line_user
from datetime import datetime as dt
from datetime import UTC
from fastapi import APIRouter, Request
from linebot import LineBotApi, WebhookParser
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
import openai

# インポートする crud 関数
from database import SessionLocal
from crud import (
    create_report, get_company_by_code, get_project,
    get_line_user, create_line_user, update_line_user
)
# WebSocket 関連のマネージャー
from websockets_manager import report_manager

# ロギング設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# LINE Bot 設定
LINE_API_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
line_api = LineBotApi(LINE_API_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

router = APIRouter()

# ユーザー情報の管理
user_context: dict[str, dict] = {}         # 連携済みの企業・プロジェクト情報
pending_context: dict[str, dict] = {}        # 新しい情報を受け付け中
pending_report: dict[str, dict] = {}
pending_image: dict[str, str] = {}

# JST タイムゾーン設定
JST = datetime.timezone(datetime.timedelta(hours=+9))

def format_dt(dt_obj: datetime.datetime) -> str:
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=datetime.timezone.utc)
    return dt_obj.astimezone(JST).strftime("%Y/%m/%d %H:%M")

@router.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        events = parser.parse(body.decode(), signature)
    except Exception:
        return {"message": "Invalid signature"}
    for event in events:
        if isinstance(event, MessageEvent):
            if isinstance(event.message, ImageMessage):
                asyncio.create_task(handle_image(event))
            elif isinstance(event.message, AudioMessage):
                asyncio.create_task(handle_audio(event))
            elif isinstance(event.message, TextMessage):
                asyncio.create_task(handle_text(event))
    return {"message": "ok"}

async def handle_text(event: MessageEvent):
    user = event.source.user_id
    text = event.message.text.strip()

    # /登録 または /変更 で現在の連携情報をクリアして、新たな情報を受け付ける
    if text in ("/登録", "/変更"):
        user_context.pop(user, None)
        pending_context.pop(user, None)
        pending_report.pop(user, None)
        pending_image.pop(user, None)
        return line_api.reply_message(
            event.reply_token,
            TextSendMessage(text="新しい企業コードとプロジェクトIDを送信してください\n例: 94102a2c 2")
        )

    # pending_context に情報がある場合は、確認応答待ち状態
    if user in pending_context:
        if text == "はい":
            # ユーザーが「はい」と答えたら連携情報として登録
            user_context[user] = pending_context.pop(user)
            comp = user_context[user]["company"]
            proj = user_context[user]["project"]
            # LINE ユーザー情報を更新（既に登録済みなら update、なければ create）
            db = SessionLocal()
            try:
                line_user = get_line_user(db, user)
                if not line_user:
                    line_user = create_line_user(db, user, "")
                update_line_user(db, line_user, {
                    "company_code": comp.company_code,
                    "project_id": proj.id,
                    "current_state": "registered"
                })
            finally:
                db.close()
            return line_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"✅ 設定完了\n企業: {comp.company_name}\nプロジェクト: {proj.name}")
            )
        # それ以外（「いいえ」など）の場合、キャンセル
        pending_context.pop(user, None)
        return line_api.reply_message(
            event.reply_token,
            TextSendMessage(text="設定をキャンセルしました")
        )

    # まだ連携情報がない場合は、新規登録用の企業コードとプロジェクトIDを受信
    if user not in user_context:
        parts = text.split()
        if len(parts) == 2:
            code, pid_str = parts
            try:
                pid = int(pid_str)
                db = SessionLocal()
                comp = get_company_by_code(db, code)
                proj = get_project(db, pid)
                if not comp or not proj or proj.company_id != comp.id:
                    raise ValueError("無効な企業コードまたはプロジェクトIDです")
                pending_context[user] = {"company": comp, "project": proj}
                quick = QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="はい", text="はい")),
                    QuickReplyButton(action=MessageAction(label="いいえ", text="いいえ"))
                ])
                return line_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text=f"この設定でよろしいですか？\n企業: {comp.company_name}\nプロジェクト: {proj.name}",
                        quick_reply=quick
                    )
                )
            except Exception as e:
                return line_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=str(e))
                )
            finally:
                db.close()
        return line_api.reply_message(
            event.reply_token,
            TextSendMessage(text="初回は「企業コード プロジェクトID」を送信してください")
        )

    # 既に連携済みの場合は、通常の報告メッセージとして処理
    comp = user_context[user]["company"]
    proj = user_context[user]["project"]
    db = SessionLocal()
    try:
        photo = pending_image.pop(user, None)
        profile = line_api.get_profile(user)
        logger.debug(f"handle_text: profile for {user}: {profile.__dict__}")
        user_name = getattr(profile, "display_name", None)
        if not user_name:
            logger.error(f"handle_text: display_name not found, falling back to user: {user}")
            user_name = user
        report = create_report(db, {
            "project_id": proj.id,
            "report_text": text,
            "photo_url": photo.replace("C:/1gyakuten/files", "/files") if photo else None,
            "audio_url": None,
            "status": "pending",
            "reporter": user_name,
            "company_id": comp.id
        })
        ts = format_dt(report.created_at)
        await report_manager.broadcast("NEW_REPORT")
        return line_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"✅ 報告登録完了\n企業: {comp.company_name}\nプロジェクト: {proj.name}\n内容: {text}\n日時: {ts}"
            )
        )
    finally:
        db.close()

async def handle_image(event: MessageEvent):
    user = event.source.user_id
    content = line_api.get_message_content(event.message.id)
    path = f"C:/1gyakuten/files/{uuid.uuid4()}.jpg"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)
    pending_image[user] = path
    return line_api.reply_message(
        event.reply_token,
        TextSendMessage(text="✅ 写真受信 — 続けて本文を送信してください")
    )

async def handle_audio(event: MessageEvent):
    user = event.source.user_id
    content = line_api.get_message_content(event.message.id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".m4a")
    tmp.write(b"".join(chunk for chunk in content.iter_content()))
    tmp.close()
    transcript = openai.Audio.transcribe("whisper-1", open(tmp.name, "rb")).get("text", "")
    fake = MessageEvent(
        source=event.source,
        message=TextMessage(text=transcript),
        reply_token=event.reply_token
    )
    await handle_text(fake)
