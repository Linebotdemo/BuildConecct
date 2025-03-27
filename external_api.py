import openai
import json
import logging
from config import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

openai.api_key = settings.OPENAI_API_KEY

def analyze_project_detail(project_data: dict):
    prompt_template = (
        "以下のプロジェクト情報に基づいて、親タスクと子タスクで構成される詳細な工程計画を生成してください。\n"
        "【プロジェクト名】: {プロジェクト名}\n"
        "【所在地】: {所在地}\n"
        "【建物種別】: {建物種別}\n"
        "【地上階数】: {地上階数}\n"
        "【地下階数】: {地下階数}\n"
        "【延床面積】: {延床面積} ㎡\n"
        "【開始日】: {開始日}\n"
        "【完了日】: {完了日}\n"
        "【担当者】: {担当者}\n\n"
        "以下のJSON形式で出力してください：\n"
        "{{\n"
        '  "detail": "<工程計画の詳細な説明>",\n'
        '  "gantt_chart": [\n'
        "      {{\n"
        '          "id": 1, \n'
        '          "text": "<親タスク名>", \n'
        '          "start_date": "YYYY-MM-DD", \n'
        '          "duration": <日数>, \n'
        '          "progress": <進捗割合>, \n'
        '          "children": [\n'
        "              {{\n"
        '                  "id": 2, \n'
        '                  "text": "<子タスク名>", \n'
        '                  "start_date": "YYYY-MM-DD", \n'
        '                  "duration": <日数>, \n'
        '                  "progress": <進捗割合>\n'
        "              }},\n"
        "              ...\n"
        "          ]\n"
        "      }},\n"
        "      ...\n"
        "  ]\n"
        "}}"
    )
    prompt = prompt_template.format(
        プロジェクト名=project_data.get("name", ""),
        所在地=project_data.get("location", ""),
        建物種別=project_data.get("building_type", ""),
        地上階数=project_data.get("ground_floors", ""),
        地下階数=project_data.get("basement_floors", ""),
        延床面積=project_data.get("total_floor_area", ""),
        開始日=project_data.get("start_date", ""),
        完了日=project_data.get("end_date", ""),
        担当者=project_data.get("project_manager", "")
    )
    logger.debug("AI生成用プロンプト:\n%s", prompt)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert construction project planner."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.7,
        )
        result_text = response.choices[0].message.content.strip()
        logger.debug("AI生成結果:\n%s", result_text)
        result_json = json.loads(result_text)
        return result_json
    except Exception as e:
        logger.error("AI生成エラー: %s", e, exc_info=True)
        return {"detail": "AI生成エラー", "gantt_chart": []}

def send_line_notification(message: str, recipients: list):
    logger.debug("LINE通知送信: %s, 送信先: %s", message, recipients)
    print(f"LINE通知: {message} - {recipients}")

def generate_order_proposal(company_id: int):
    return {"proposal": "在庫状況に基づく新規発注の提案内容"}

def analyze_inventory(company_id: int):
    return {"analysis": "最新の在庫分析結果"}

def check_stock_alert(company_id: int):
    return {"alert": "在庫に関するアラート情報"}

def create_backup_file():
    return "backup_file_name.zip"

def restore_backup_file(backup_id: str):
    print(f"バックアップからのリストア: {backup_id}")

def generate_2fa_qr(email: str):
    return "https://example.com/qr-code"

def verify_2fa_code(email: str, code: str):
    return True

def create_checkout_session(email: str, plan_id: str):
    return "https://stripe.com/checkout_session"

def handle_billing_webhook(payload: dict):
    print("Webhook処理:", payload)
