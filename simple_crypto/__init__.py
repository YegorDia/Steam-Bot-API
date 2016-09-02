from Crypto.Cipher import AES
import base64

BLOCK_SIZE = 16

PADDING = '{'

pad = lambda s: s + (BLOCK_SIZE - len(s) % BLOCK_SIZE) * PADDING

EncodeAES = lambda c, s: base64.b64encode(c.encrypt(pad(s)))
DecodeAES = lambda c, e: c.decrypt(base64.b64decode(e)).rstrip(PADDING)


def simple_encode(key, text):
    cipher = AES.new(key)
    encoded = EncodeAES(cipher, text)
    return encoded


def simple_decode(key, text):
    cipher = AES.new(key)
    decoded = DecodeAES(cipher, text)
    return decoded