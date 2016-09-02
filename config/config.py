import json


class Configurator(object):
    def __init__(self, path='default.json'):
        self.path = path
        with open(path) as json_file:
            json_data = json.load(json_file)
            self.config = json_data

    def __getitem__(self, key):
        return self.config.get(key)

    def set(self, key, value):
        self.config[key] = value
        with open(self.path, 'w') as outfile:
            json.dump(self.config, outfile)

    def get(self, key, default):
        return self.config.get(key, default)

    def __setitem__(self, key, value):
        self.config[key] = value