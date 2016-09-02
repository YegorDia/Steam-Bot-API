import time
from steam_bot.steam_bot import SteamBot


class CelerySteamBot():
    def __init__(self, username, password, device_id, shared_secret, identity_secret):
        self.username = username
        self.password = password
        self.device_id = device_id
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        self.bot = SteamBot(username)
        self.bot._cache_param("shared_secret", self.shared_secret)
        self.bot._cache_param("identity_secret", self.identity_secret)
        self.bot._cache_param("device_id", self.device_id)

    def try_login(self):
        return self.bot.mobile_login(self.password)

    def authorize(self):
        while not self.bot.check_logon():
            self.bot.mobile_login(self.password)
            time.sleep(2)
        return True

    def load_inventory(self, app_id):
        return self.bot.inventory(app_id)

    def send_deposit_offer(self, receiver_id, receiver_token, assets, message):
        try:
            return {
                "success": True,
                "tradeoffer_id": self.bot.send_tradeoffer(receiver_id, receiver_token, [{"id": a["assetid"], "appid": a["app_id"]} for a in assets], [], message)
            }
        except Exception as e:
            return {
                "success": False,
                "error": e.message
            }

    def send_withdraw_offer(self, receiver_id, receiver_token, assets, message):
        try:
            return {
                "success": True,
                "tradeoffer_id": self.bot.send_tradeoffer(receiver_id, receiver_token, [], [{"id": a["assetid"], "appid": a["app_id"]} for a in assets], message)
            }
        except Exception as e:
            return {
                "success": False,
                "error": e.message
            }

    def confirm_tradeoffer(self, tradeoffer_id):
        try:
            confirmations = self.bot.fetch_confirmations()
            for confirmation in confirmations:
                self.bot.accept_confirmation(confirmation)
            return "OK"
        except Exception as e:
            return e.message

    def cancel_tradeoffer(self, tradeoffer_id):
        try:
            return {
                "success": self.bot.cancel_tradeoffer(tradeoffer_id)
            }
        except Exception as e:
            return {
                "success": False,
                "error": e.message
            }

    def get_tradeoffer(self, tradeoffer_id):
        try:
            self.bot._logged_in = True
            tradeoffer = self.bot.get_tradeoffer(tradeoffer_id)
            if tradeoffer:
                return {
                    "success": True,
                    "tradeoffer": tradeoffer
                }
            return {
                "success": False,
                "error": "Cannot check trade offer"
            }
        except Exception as e:
            return {
                "success": False,
                "error": e.message
            }
