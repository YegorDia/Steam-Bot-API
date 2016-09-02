from flask import Flask, url_for, request, jsonify, redirect, session, abort
from celery import Celery, shared_task
from redis import StrictRedis
from pymongo import MongoClient

import random
import sys
import json
import os
import cPickle
import time

from simple_crypto import simple_decode, simple_encode
from utils import generate_code, report, report_inventory
from bots import DatabaseBots
from config.config import Configurator

from celery_steam_bot import CelerySteamBot

if sys.platform == 'win32':
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..\\cfg\\default.json')
else:
    CONFIG_PATH = '/usr/share/www/steam-bot-api/cfg/deploy.json'

CONFIG = Configurator(CONFIG_PATH)

mongodb = MongoClient(CONFIG.get("MONGODB_HOST", "localhost:27017"))["botapi"]
redis = StrictRedis(CONFIG["REDIS_HOST"], port=int(CONFIG["REDIS_PORT"]), db=int(CONFIG["REDIS_DB"]), password=CONFIG["REDIS_PASSWORD"])
db_bots = DatabaseBots(mongodb)


def make_celery(app):
    celery = Celery(app.import_name)
    celery.config_from_object("wsgi_app.celery_config")
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery


app = Flask("botapi")
app.debug = True
app.config.update(
    SECRET_KEY=CONFIG['APP_SECRET']
)
celery = make_celery(app)


# @celery.task(name="report_task")
# def report_task(service_url, report_url, status, error):
#     report(
#         service_url=service_url,
#         report_url=report_url,
#         status=status,
#         error=error,
#         token=CONFIG["ACCESS_TOKEN"]
#     )


@celery.task(name="update_inventories_task")
def update_inventories_task():
    access_token = str(CONFIG["ACCESS_TOKEN"])
    bots = db_bots.get_all()
    updated = 0

    for bot in bots:
        print(bot["username"])
        bot["password"] = simple_decode(CONFIG["CRYPTO_SALT"], bot["password"])
        bot["shared_secret"] = simple_decode(CONFIG["CRYPTO_SALT"], bot["shared_secret"])
        bot["identity_secret"] = simple_decode(CONFIG["CRYPTO_SALT"], bot["identity_secret"])
        celery_bot = CelerySteamBot(
            str(bot["username"]),
            str(bot["password"]),
            str(bot["device_id"]),
            str(bot["shared_secret"]),
            str(bot["identity_secret"])
        )

        bot_inventory = {"success": False, "rgInventory": {}, "rgDescriptions": {}}

        if bot.get("active", False):
            try:
                celery_bot.authorize()
                bot_inventory = celery_bot.load_inventory(730)
            except:
                pass
        else:
            bot_inventory["success"] = True

        if bot_inventory.get("success", False):
            redis.set("bot_%s_invnetory_%s" % (str(bot["username"]), 730), cPickle.dumps({
                "inventory": bot_inventory["rgInventory"],
                "descriptions": bot_inventory["rgDescriptions"],
            }))
            redis.set("bot_%s_invnetory_%s_length" % (str(bot["username"]), 730), int(len(bot_inventory["rgInventory"])))

            service_url = "http://%s/trade/inventory/%s/report" % (CONFIG["SERVICE_HOST"], 730)
            report_inventory(
                service_url=service_url,
                bot_username=str(bot["username"]),
                token=access_token
            )
            updated += 1

    return {"updated": updated, "length": len(bots)}


@celery.task(bind=True, name="check_tradeoffer_task")
def check_tradeoffer_task(self, bot, steam_id, report_url, additional, is_deposit, checking_time):
    access_token = str(CONFIG["ACCESS_TOKEN"])
    tradeoffer_id = additional["tradeoffer_id"]

    celery_bot = CelerySteamBot(
        str(bot["username"]),
        str(bot["password"]),
        str(bot["device_id"]),
        str(bot["shared_secret"]),
        str(bot["identity_secret"])
    )

    if is_deposit:
        service_url = "http://%s/trade/deposits/%s/report" % (CONFIG["SERVICE_HOST"], steam_id)
        data = {"steam_id": steam_id}
        checking_time_limit = 300
    else:
        service_url = "http://%s/trade/withdrawals/%s/report" % (CONFIG["SERVICE_HOST"], steam_id)
        data = {"steam_id": steam_id, "bot": str(bot["username"]), "points": additional["points"]}
        checking_time_limit = 120

    result = celery_bot.get_tradeoffer(tradeoffer_id)
    if result.get("success", False):
        tradeoffer_state = int(result["tradeoffer"]['offer']['trade_offer_state'])
        print "State: %s" % tradeoffer_state
        if tradeoffer_state == 1:
            report(
                service_url=service_url,
                report_url=report_url,
                status=6,
                error="Invalid trade offer",
                token=access_token,
                data=data
            )
            return {"status": "Invalid trade offer"}
        elif tradeoffer_state == 2:
            if not is_deposit and not additional.get("confirmed", False):
                message = "Trade offer confirmed %s" % tradeoffer_id
                report(
                    service_url=service_url,
                    report_url=report_url,
                    status=2,
                    error=message,
                    token=access_token,
                    data={
                        "steam_id": steam_id,
                        "bot": str(bot["username"]),
                        "security_code": additional["security_code"],
                        "celery_task_id": "-",
                        "tradeoffer_id": tradeoffer_id,
                        "points": additional["points"]
                    }
                )
                additional["confirmed"] = True
        elif tradeoffer_state == 3:
            data["points"] = additional["points"]
            report(
                service_url=service_url,
                report_url=report_url,
                status=3,
                error="Completed",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer completed"}
        elif tradeoffer_state == 4:
            celery_bot.cancel_tradeoffer(tradeoffer_id)
            report(
                service_url=service_url,
                report_url=report_url,
                status=5,
                error="Trade offer declined",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer countered"}
        elif tradeoffer_state == 5:
            report(
                service_url=service_url,
                report_url=report_url,
                status=5,
                error="Trade offer expired",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer expired"}
        elif tradeoffer_state == 6:
            report(
                service_url=service_url,
                report_url=report_url,
                status=7,
                error="Bot cancelled offer",
                token=access_token,
                data=data
            )
            return {"status": "Bot cancelled offer"}
        elif tradeoffer_state == 7:
            report(
                service_url=service_url,
                report_url=report_url,
                status=5,
                error="Trade offer declined",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer declined"}
        elif tradeoffer_state == 8:
            celery_bot.cancel_tradeoffer(tradeoffer_id)
            report(
                service_url=service_url,
                report_url=report_url,
                status=5,
                error="Trade offer declined",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer declined"}
        elif tradeoffer_state == 9:
            if not is_deposit:
                checking_time -= 9
                confirmation_result = celery_bot.confirm_tradeoffer(tradeoffer_id)
                print "Tradeoffer confirmation: %s" % confirmation_result
        elif tradeoffer_state == 10:
            celery_bot.cancel_tradeoffer(tradeoffer_id)
            report(
                service_url=service_url,
                report_url=report_url,
                status=5,
                error="Trade offer declined",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer declined"}
        elif tradeoffer_state == 11:
            celery_bot.cancel_tradeoffer(tradeoffer_id)
            report(
                service_url=service_url,
                report_url=report_url,
                status=4,
                error="Trade offer cancelled (trade hold)",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer cancelled (trade hold)"}

    if checking_time < checking_time_limit:
        checking_time += 10

        check_tradeoffer_task.apply_async(
            args=[bot, steam_id, report_url, additional, is_deposit, checking_time],
            countdown=10,
            queue="check_tradeoffer_task"
        )
        return {"status": "Check task queued"}
    else:
        try:
            result = celery_bot.cancel_tradeoffer(tradeoffer_id)
            report(
                service_url=service_url,
                report_url=report_url,
                status=4,
                error="Trade offer expired",
                token=access_token,
                data=data
            )
            return {"status": "Trade offer checking time expired"}
        except:
            pass

        check_tradeoffer_task.apply_async(
            args=[bot, steam_id, report_url, additional, is_deposit, checking_time],
            countdown=10,
            queue="check_tradeoffer_task"
        )
        return {"status": "Check task queued (cannot cancel tradeoffer)"}


@celery.task(bind=True, name="deposit_task")
def deposit_task(self, bot, steam_id, trade_token, assets, report_url, additional):
    access_token = str(CONFIG["ACCESS_TOKEN"])
    service_url = "http://%s/trade/deposits/%s/report" % (CONFIG["SERVICE_HOST"], steam_id)
    try:
        self.update_state(state='PROGRESS', meta={'status': "Establishing bot"})
        celery_bot = CelerySteamBot(
            str(bot["username"]),
            str(bot["password"]),
            str(bot["device_id"]),
            str(bot["shared_secret"]),
            str(bot["identity_secret"])
        )

        self.update_state(state="PROGRESS", meta={'status': "Logging in"})
        celery_bot.authorize()

        self.update_state(state="PROGRESS", meta={'status': "Sending trade offer"})
        if "message" in additional:
            message = "%s (code: %s)" % (additional["message"], additional["security_code"])
        else:
            message = "Deposit (code: %s)" % additional["security_code"]

        result = celery_bot.send_deposit_offer(steam_id, trade_token, assets, message)
        if result.get("success", False):
            message = "Trade offer sent %s" % result["tradeoffer_id"]
            report(
                service_url=service_url,
                report_url=report_url,
                status=2,
                error=message,
                token=access_token,
                data={
                    "steam_id": steam_id,
                    "security_code": additional["security_code"],
                    "celery_task_id": "-",
                    "tradeoffer_id": result["tradeoffer_id"]
                }
            )

            additional["tradeoffer_id"] = str(result["tradeoffer_id"])
            check_tradeoffer_task.apply_async(
                args=[bot, steam_id, report_url, additional, True, 0],
                countdown=10,
                queue="check_tradeoffer_task"
            )
            return {"status": message}
        raise Exception(result["error"])
    except Exception as e:
        message = "Internal server error"
        try:
            if e.message.find("Trade Offer Error") != -1:
                if e.message.find("is not available to trade. More information will be shown to") != -1:
                    message = "You are not available to trade"
                elif e.message.find("This Trade URL is no longer valid for sending a trade offer to") != -1:
                    message = "Your trade offer link is invalid"
                elif e.message.find('inventory privacy is set to "Private"') != -1:
                    message = "Your inventory privacy is private, change to public"
            elif e.message.find("Request Error") != -1:
                status_code = int(e.message.split(", ")[1])
                if status_code == 500:
                    message = "Steam trading error"
                else:
                    message = "Trade error, status %s" % status_code
        except:
            pass
        report(
            service_url=service_url,
            report_url=report_url,
            status=6,
            error=message,
            token=access_token,
            data={"steam_id": steam_id, "security_code": additional["security_code"]}
        )


@celery.task(bind=True, name="withdraw_task")
def withdraw_task(self, bot, steam_id, trade_token, assets, report_url, additional):
    access_token = str(CONFIG["ACCESS_TOKEN"])
    service_url = "http://%s/trade/withdrawals/%s/report" % (CONFIG["SERVICE_HOST"], steam_id)

    time.sleep(random.randint(0, 3))
    try:
        self.update_state(state='PROGRESS', meta={'status': "Establishing bot"})
        celery_bot = CelerySteamBot(
            str(bot["username"]),
            str(bot["password"]),
            str(bot["device_id"]),
            str(bot["shared_secret"]),
            str(bot["identity_secret"])
        )

        self.update_state(state="PROGRESS", meta={'status': "Logging in"})
        celery_bot.authorize()

        self.update_state(state="PROGRESS", meta={'status': "Sending trade offer"})
        if "message" in additional:
            message = "%s (code: %s)" % (additional["message"], additional["security_code"])
        else:
            message = "Withdraw (code: %s)" % additional["security_code"]

        result = celery_bot.send_withdraw_offer(steam_id, trade_token, assets, message)
        if result.get("success", False):
            message = "Trade offer sent %s" % result["tradeoffer_id"]
            report(
                service_url=service_url,
                report_url=report_url,
                status=1,
                error=message,
                token=access_token,
                data={
                    "steam_id": steam_id,
                    "bot": str(bot["username"]),
                    "security_code": additional["security_code"],
                    "celery_task_id": "-",
                    "tradeoffer_id": result["tradeoffer_id"],
                    "points": additional["points"]
                }
            )

            additional["tradeoffer_id"] = str(result["tradeoffer_id"])
            check_tradeoffer_task.apply_async(
                args=[bot, steam_id, report_url, additional, False, 0],
                countdown=10,
                queue="check_tradeoffer_task"
            )
            return {"status": message}
        raise Exception(result["error"])
    except Exception as e:
        message = "Internal server error"
        try:
            if e.message.find("Trade Offer Error") != -1:
                if e.message.find("is not available to trade. More information will be shown to") != -1:
                    message = "You are not available to trade"
                elif e.message.find("This Trade URL is no longer valid for sending a trade offer to") != -1:
                    message = "Your trade offer link is invalid"
                elif e.message.find('inventory privacy is set to "Private"') != -1:
                    message = "Your inventory privacy is private, change to public"
            elif e.message.find("Request Error") != -1:
                status_code = int(e.message.split(", ")[1])
                if status_code == 500:
                    message = "Steam trading error"
                else:
                    message = "Trade error, status %s" % status_code
        except:
            pass
        report(
            service_url=service_url,
            report_url=report_url,
            status=6,
            error=message,
            token=access_token,
            data={
                "steam_id": steam_id,
                "security_code": additional["security_code"],
                "bot": str(bot["username"]),
                "points": additional["points"]
            }
        )


def logged_in():
    return session.get("authorized", False)


def in_allowed_ips(ip_address):
    if ip_address in CONFIG.get("ALLOW_IPS", []):
        return True
    return False


@app.before_request
def before_request():
    if not in_allowed_ips(request.remote_addr):
        return abort(404)

    if not logged_in():
        access_token = request.args.get("token", False) or request.form.get("token", False)
        if access_token == CONFIG["ACCESS_TOKEN"]:
            session["authorized"] = True


@app.route("/ping", methods=["GET"])
def ping():
    if logged_in():
        if not CONFIG.get("SERVICE_HOST", False):
            CONFIG.set("SERVICE_HOST", "%s:8000" % request.remote_addr)
        return "OK", 200
    return abort(401)


@app.route("/stats", methods=["GET"])
def stats():
    if logged_in():

        try:
            deposit_tasks_count = redis.llen("deposit_task")
            withdrawal_tasks_count = redis.llen("withdrawal_task")
            check_tradeoffer_tasks_count = redis.llen("check_tradeoffer_task")
        except:
            deposit_tasks_count = 0
            withdrawal_tasks_count = 0
            check_tradeoffer_tasks_count = 0

        deposit_tasks_limit = 50
        withdrawal_tasks_limit = 50
        check_tradeoffer_tasks_limit = 100

        load = (float(deposit_tasks_count) / float(deposit_tasks_limit) +
                float(withdrawal_tasks_count) / float(withdrawal_tasks_limit) +
                float(check_tradeoffer_tasks_count) / float(check_tradeoffer_tasks_limit)) / 3.0

        data = {
            "load": load,
            "bots": db_bots.get_all()
        }
        return jsonify(data), 200
    return abort(401)


@app.route("/bots/add", methods=["POST"])
def bots_add():
    if logged_in():
        nickname = request.form.get("nickname")
        username = request.form.get("username")
        password = request.form.get("password")
        shared_secret = request.form.get("shared_secret")
        identity_secret = request.form.get("identity_secret")
        device_id = request.form.get("device_id")

        if username and password and shared_secret and identity_secret and device_id:
            bot = CelerySteamBot(username, password, device_id, shared_secret, identity_secret)
            if bot.try_login():
                db_bots.add(str(nickname), str(username), simple_encode(CONFIG["CRYPTO_SALT"], str(password)),
                            simple_encode(CONFIG["CRYPTO_SALT"], str(shared_secret)),
                            simple_encode(CONFIG["CRYPTO_SALT"], str(identity_secret)), str(device_id))
                return "OK", 200
            return "Invalid bot credentials or login error", 500
    return abort(401)


@app.route("/bots/toggle", methods=["POST"])
def bots_toggle():
    if logged_in():
        username = request.form.get("username")

        if username:
            db_bots.toggle_active(str(username))
            return "OK", 200
    return abort(401)


@app.route("/bots/remove", methods=["POST"])
def bots_remove():
    if logged_in():
        username = request.form.get("username")

        if username:
            db_bots.remove(str(username))
            return "OK", 200
    return abort(401)


@app.route("/bots/<string:username>/inventory/<int:app_id>", methods=["GET"])
def bots_inventory(username, app_id):
    if logged_in():
        inventory_key = "bot_%s_invnetory_%s" % (str(username), int(app_id))
        if redis.exists(inventory_key):
            inventory = cPickle.loads(redis.get(inventory_key))
            return jsonify(inventory), 200
        return abort(404)
    return abort(401)


@app.route("/<string:bot_username>/withdraw", methods=["POST"])
def withdraw(bot_username):
    if logged_in():
        steam_id = request.form.get("steam_id")
        trade_token = request.form.get("trade_token")
        report_url = request.form.get("report_url")

        assets = json.loads(request.form.get("assets"))
        additional = json.loads(request.form.get("data"))

        current_bot = db_bots.get_username(bot_username)
        if not current_bot.get("active", False):
            report(
                service_url="http://%s/trade/withdrawals/%s/report" % (CONFIG["SERVICE_HOST"], steam_id),
                report_url=report_url,
                status=6,
                error="The bot you are trying to withdraw is offline",
                token=CONFIG["ACCESS_TOKEN"],
                data={"bot": bot_username, "points": additional["points"]}
            )
            return abort(500)

        if len(assets) == 0:
            report(
                service_url="http://%s/trade/withdrawals/%s/report" % (CONFIG["SERVICE_HOST"], steam_id),
                report_url=report_url,
                status=6,
                error="0 Items to withdraw",
                token=CONFIG["ACCESS_TOKEN"],
                data={"bot": bot_username, "points": additional["points"]}
            )
            return abort(500)

        if len(assets) > 50:
            report(
                service_url="http://%s/trade/withdrawals/%s/report" % (CONFIG["SERVICE_HOST"], steam_id),
                report_url=report_url,
                status=6,
                error="50 Items max to withdraw",
                token=CONFIG["ACCESS_TOKEN"],
                data={"bot": bot_username, "points": additional["points"]}
            )
            return abort(500)

        current_bot["password"] = simple_decode(CONFIG["CRYPTO_SALT"], current_bot["password"])
        current_bot["shared_secret"] = simple_decode(CONFIG["CRYPTO_SALT"], current_bot["shared_secret"])
        current_bot["identity_secret"] = simple_decode(CONFIG["CRYPTO_SALT"], current_bot["identity_secret"])
        bot_json = {
            "username": str(current_bot["username"]),
            "password": str(current_bot["password"]),
            "shared_secret": str(current_bot["shared_secret"]),
            "identity_secret": str(current_bot["identity_secret"]),
            "device_id": str(current_bot["device_id"])
        }
        security_code = generate_code()
        additional["security_code"] = security_code
        task = withdraw_task.apply_async(
            args=[bot_json, steam_id, trade_token, assets, report_url, additional],
            queue="withdraw_task"
        )
        return jsonify({"security_code": security_code, "bot": current_bot["nickname"], "task_id": task.id}), 200
    return abort(401)


@app.route("/deposit", methods=["POST"])
def deposit():
    if logged_in():
        steam_id = request.form.get("steam_id")
        trade_token = request.form.get("trade_token")
        report_url = request.form.get("report_url")

        assets = json.loads(request.form.get("assets"))
        additional = json.loads(request.form.get("data"))

        active_bots = db_bots.get_all_active()
        if len(active_bots) == 0:
            report(
                service_url="http://%s/trade/deposits/%s/report" % (CONFIG["SERVICE_HOST"], steam_id),
                report_url=report_url,
                status=6,
                error="All bots are offline",
                token=CONFIG["ACCESS_TOKEN"],
                data={"steam_id": steam_id}
            )
            return abort(500)

        if len(assets) == 0:
            report(
                service_url="http://%s/trade/deposits/%s/report" % (CONFIG["SERVICE_HOST"], steam_id),
                report_url=report_url,
                status=6,
                error="0 Items offered",
                token=CONFIG["ACCESS_TOKEN"],
                data={"steam_id": steam_id}
            )
            return abort(500)

        if len(assets) > 100:
            report(
                service_url="http://%s/trade/deposits/%s/report" % (CONFIG["SERVICE_HOST"], steam_id),
                report_url=report_url,
                status=6,
                error="100 Items max to deposit",
                token=CONFIG["ACCESS_TOKEN"],
                data={"steam_id": steam_id}
            )
            return abort(500)

        selected_bot = None
        biggest_inventory = 0
        for bot in active_bots:
            try:
                inventory_len = int(redis.get("bot_%s_invnetory_%s_length" % (str(bot["username"]), 730)))
                if inventory_len + len(assets) + 5 < 950 and inventory_len > biggest_inventory:
                    selected_bot = bot
                    biggest_inventory = inventory_len
            except:
                pass
        if not selected_bot:
            report(
                service_url="http://%s/trade/deposits/%s/report" % (CONFIG["SERVICE_HOST"], steam_id),
                report_url=report_url,
                status=6,
                error="Cannot find proper bot to handle request",
                token=CONFIG["ACCESS_TOKEN"],
                data={"steam_id": steam_id}
            )
            return abort(500)

        selected_bot["password"] = simple_decode(CONFIG["CRYPTO_SALT"], selected_bot["password"])
        selected_bot["shared_secret"] = simple_decode(CONFIG["CRYPTO_SALT"], selected_bot["shared_secret"])
        selected_bot["identity_secret"] = simple_decode(CONFIG["CRYPTO_SALT"], selected_bot["identity_secret"])
        bot_json = {
            "username": str(selected_bot["username"]),
            "password": str(selected_bot["password"]),
            "shared_secret": str(selected_bot["shared_secret"]),
            "identity_secret": str(selected_bot["identity_secret"]),
            "device_id": str(selected_bot["device_id"])
        }
        security_code = generate_code()
        additional["security_code"] = security_code
        task = deposit_task.apply_async(
            args=[bot_json, steam_id, trade_token, assets, report_url, additional],
            queue="deposit_task"
        )
        return jsonify({"security_code": security_code, "bot": selected_bot["nickname"], "task_id": task.id}), 200
    return abort(401)


@app.route('/deposit/<task_id>')
def deposit_task_id(task_id):
    if logged_in():
        task = deposit_task.AsyncResult(task_id)
        if task.state == 'PENDING':
            response = {
                'state': task.state,
                'status': 'Pending...'
            }
        elif task.state != 'FAILURE':
            response = {
                'state': task.state,
                'status': task.info.get('status', '')
            }
            if 'result' in task.info:
                response['result'] = task.info['result']
        else:
            response = {
                'state': task.state,
                'status': str(task.info)
            }
        return jsonify(response)
    return abort(401)