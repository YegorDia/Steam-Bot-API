from bson.objectid import ObjectId


class DatabaseBots():
    def __init__(self, db):
        self.collection = db["bots"]

    def get_all(self):
        db_bots = list(self.collection.find({}))
        for server in db_bots:
            server["_id"] = str(server["_id"])
        return db_bots

    def get_all_active(self):
        db_bots = list(self.collection.find({"active": True}))
        for server in db_bots:
            server["_id"] = str(server["_id"])
        return db_bots

    def get(self, bot_id):
        return self.collection.find_one({"_id": ObjectId(bot_id)}, {"_id": 0})

    def get_username(self, username):
        return self.collection.find_one({"username": username}, {"_id": 0})

    def add(self, nickname, username, password, shared_secret, identity_secret, device_id):
        new_bot = {
            "nickname": nickname,
            "username": username,
            "password": password,
            "shared_secret": shared_secret,
            "identity_secret": identity_secret,
            "device_id": device_id,
            "task": "idle",
            "active": False
        }
        result = self.collection.insert(new_bot)
        return result is not None

    def toggle_active(self, username):
        bot = self.get_username(username)
        if bot:
            result = self.collection.update({"username": username}, {"$set": {"active": not bot["active"]}}, upsert=False)
            return True
        return False

    def remove(self, username):
        bot = self.get_username(username)
        if bot:
            result = self.collection.remove({"username": username})
            return True
        return False